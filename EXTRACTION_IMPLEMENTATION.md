# Document extraction and benchmark-gated improvement

Branch: max. Scope: local laptop workflow; training weights supplied by partner.

## Build checklist

- [x] Bounded PDF/image/text preprocessing with immutable originals and page views.
- [x] Versioned schema, local model adapter, citations, abstention, correction review.
- [x] Human-approved intake staging; never automatic ledger posting.
- [x] Consent-gated, frozen training and evaluation sets with group separation.
- [x] Server-run paired benchmarks, regression gates, promotion and rollback.
- [x] Workspace UI, partner contract, adversarial/lifecycle tests and build checks.

## Boundaries

The local model extracts observations, not audit conclusions. Source bytes, page
text and human corrections remain distinct. OCR is fallible. Training and private
model weights are not implemented here: partner-produced candidates must satisfy
the inference contract and pass frozen benchmarks before human promotion.
Benchmark numbers must come from actual runs, never manually submitted scores.
An authorized reviewer must approve dataset use. No self-training on predictions.

## User journey and ongoing file updates

1. Select an existing institution. Records & overview has **Keep this institution
   up to date**, a snapshot change summary and a scan action. No new institution
   is needed to add files.
2. Add CSV/TXT/Markdown in the existing intake or open `/documents` (also `/learning`
   for intake workspaces) for PDF/PNG/JPEG/TXT/Markdown. Limits: 10 MB, 20 pages,
   12 megapixels/page, 200,000 extracted characters. Originals remain immutable.
3. For revised PDFs/images, choose the document the new upload replaces. For CSV
   revisions, retain source system and record IDs and increment source version.
   Imports are incremental upserts, not whole-file replacement: omitted records
   are not silently deleted. Historical documents and snapshots remain available.
4. Compare page text with original rendered pages. OCR corrections create new text
   revisions, invalidating affected labels, future dataset use and staged imports.
5. Extract using a configured local model or label manually while the partner trains.
   Approve fields with exact source spans, template/institution grouping and explicit
   data-use authorization. Model predictions alone never become training examples.
6. Stage approved extractions as corroborating evidence by default. Opt into financial
   records only when those events are not already imported. Then review and explicitly
   commit the generated intake batch. Accounting validation remains mandatory.
7. Use **Scan updates**: deterministic rules are local. The separate live checkbox
   explicitly authorizes hosted-model calls and API charges for all five agents.
   Repeated live-scan clicks reuse the nonfailed update run for the same snapshot.
   Related unchanged records are still reviewed; this is not unsafe delta-only reasoning.
8. Freeze authorized corrections into training or held-out evaluation datasets.
   Original hashes and normalized groups cannot overlap between splits. Withdrawing
   authorization invalidates future exports/promotions, but cannot recall downloads.
9. Register candidate versions, run paired benchmark jobs, inspect failures/metrics,
   explicitly promote a passing candidate, or roll back to an earlier approved release.

## Partner inference contract: schooltrace.extraction.v1

Configure `SCHOOLTRACE_EXTRACTORS` as JSON in ignored `api/.env`:

```json
{
  "extractor-baseline-v1": {
    "endpoint": "http://127.0.0.1:8901/extract",
    "artifact_sha256": "<64 lowercase hex characters>",
    "base_revision": "<immutable base revision>",
    "training_manifest_sha256": "<64 lowercase hex characters>",
    "training_document_hashes": [],
    "training_groups": [],
    "supported_roles": ["invoice"]
  }
}
```

Populate hashes/groups with actual training provenance, including known external
overlap. Register base and candidate separately; artifact/quantization/config changes
require new registrations. Provenance is operator-attested, not cryptographic proof
of what an arbitrary model server executed. Partner must version/hash actual weights.

The app POSTs `schema_version`, `artifact_sha256`, `document_type`, `fields`, `pages`,
`output_schema` and `instruction` to the fixed loopback endpoint. Never send evaluation
gold to the model. V1 supplies **page text**, not images: PDFium/RapidOCR preprocess
locally, retaining original images for human inspection. Train to this text contract,
not an image-only API. Training JSONL has matching inputs and human-approved outputs.

### Included local inference server

`api/app/extractor_server.py` is the optional Transformers/PEFT serving wrapper, so
your partner can supply weights rather than build a new API. It does not download
models or run training. Install the optional runtime with `uv sync --extra extractor`.
Set `EXTRACTOR_MODEL_DIR` to an absolute, materialized local model directory and,
for LoRA, `EXTRACTOR_ADAPTER_DIR` to the local adapter directory. Only safetensors
bundles are supported; symlinks, pickle weights and Python model code are rejected.
The selected model architecture must be supported natively by Transformers; remote
code is not trusted. The serving wrapper uses AutoModelForImageTextToText/AutoProcessor
for the NuExtract-class candidate and optionally wraps the model with PEFT.

From `api/`, run `uv run --extra extractor python -m app.extractor_server` to hash
the actual bundle. Set `EXTRACTOR_ARTIFACT_SHA256` to that fingerprint, and use the
same hash in the main API's model registry configuration. Then launch:

```sh
uv run --extra extractor uvicorn app.extractor_server:app --host 127.0.0.1 --port 8901
```

Start a second port/process with the baseline bundle to run paired comparisons.
The service validates schema/artifact IDs, rejects browser-origin requests, uses
offline local model loading, serializes generation and validates source spans.
Input/output limits are 24k/8k tokens; generation has a 90-second soft limit.
Actual hardware capacity, latency and model compatibility cannot be verified until
the partner supplies weights. Fingerprinting/route guards are regression tested;
no synthetic stub is represented as a trained model.

Response (abbreviated; include EVERY requested field in each record):

```json
{
  "artifact_sha256": "<configured hash>",
  "output": {
    "schema_version": "schooltrace.extraction.v1",
    "records": [{
      "invoice_number": {
        "status": "present", "value": "A-101", "page": 1, "start": 8, "end": 13
      }
    }]
  }
}
```

Each requested field must appear once. Present values must exactly equal the cited
page text[start:end]. Offsets are zero-based Unicode code points, end-exclusive,
not UTF-8 bytes. `missing`, `ambiguous`, `unreadable` require null value/page/start/end.
Unknown fields are rejected. Preserve source record order. No invented IDs, arithmetic,
fraud labels or audit conclusions. Amounts are literal strings, never JSON floats.
Backend normalization permits only unambiguous comma grouping, currency-qualified
dollar prefixes and English named-month dates; ambiguous numeric dates stay blocked.

V1 supports invoice headers, payroll rows, grant registers, budget rows and cited
service/policy statements. Full invoice-line/PO/receipt accounting and legal-policy
interpretation are not claimed; richer schemas require versioning and new corpora.

## Benchmark gates and operations

Engineering thresholds, NOT measured model performance: >=20 held-out documents,
>=3 groups, >=100 present fields; schema validity 100%, precision 99%, recall 95%,
exact citation accuracy 98%, abstention-status accuracy 95%, critical money/date/ID
exact match 99%, unsupported extraction <=1%. No aggregate metric may regress versus
baseline. Empty metric denominators score zero rather than vacuous success. All
candidate-supported document types must be represented. Failed model calls, malformed
output and wrong artifact identities count as failures. These hackathon minimums do
not establish production safety or statistical confidence.

`POST /api/workspaces/{ws}/extraction/benchmark-jobs` takes `dataset_id`, `baseline_id`,
`candidate_id`. Poll the workspace extraction overview for job/evaluation status.
Job state survives refresh; queued/running jobs become interrupted on server restart
and require explicit rerun. One background benchmark job per API process, two local
inference slots, bounded responses/timeouts, five-minute batch budget (an in-flight
call may finish after that deadline). Run one API worker for this laptop architecture.

Promotion requires admin authority, current dataset authorization, unchanged model
manifest, passing current gates, and an evaluation against the current active model.
Rollback targets previously approved, available, nonretired releases. Retirement is
explicit. Counts of failed predictions/reviewer corrections and per-example evaluation
metrics are visible; they are not automatic drift detection or automatic retraining.
Partner trains candidates offline, then repeats this promotion cycle. No weights are
mutated in place and no private chain-of-thought is exported.

## Verification and boundaries

Final suite: **357 passed, 10 skipped**, clean frontend lint/TypeScript/build. New
tests use synthetic inputs and deterministic inference doubles for release gates;
these scores are NOT real trained-model benchmarks. Actual PNG OCR and PDF rendering
are exercised. No partner weights have yet been supplied or evaluated.

API remains loopback-only, with optional workspace roles. Supabase web login is
separate from local API accounts; this is not hosted tenant authorization. Documents
live in the existing permission-restricted SQLite DB. Logical workspace deletion
includes extraction data and refuses active jobs, but cannot erase external exports
or backups. Parser subprocess limits are not a hardened OS sandbox. Use synthetic or
authorized public documents, not confidential school/student/payroll records.
Dependencies are locked in `api/uv.lock`; OCR weights ship with the installed package.

Browser verification used a fresh synthetic workspace: uploaded invoice, human
correction approval, frozen training export/download, validated intake commit,
incremental scan (14 → 16 active records) and changed Findings. Existing institution
data was left untouched. Partner weights and live model accuracy remain unverified.
