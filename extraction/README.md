# Document Extraction Model

Trains and evaluates the local document-extraction model spec.md §5/§7.5
describes: turns documents into structured, source-backed facts for all five
financial agents. It is not the CFO or Internal Auditor, and it must never
calculate financial results, approve changes, or convert an extraction into
an audit conclusion (spec.md §5) — that stays deterministic backend code and
human review, same as everywhere else in this project.

## Status

The model has been run, benchmarked, and wired into the running application.
`serve.py` holds it behind the loopback HTTP contract `api/app/extraction.py`
calls, so uploading a PDF in the Document lab fills the review form instead of
leaving it blank.

### Measured results

Base model, no fine-tuning. Scored by `scripts/evaluate.py` with the current
normalizers; re-derivable for free from the saved predictions, because the
benchmark writes raw model output to `--out` and scoring is pure Python.

| Set | Docs | Precision | Recall | F1 |
|---|---|---|---|---|
| Northwind invoices (invoice-sandbox-benchmark) | 70 | 1.0 | 1.0 | 1.0 |
| APEX contract attorneys (hand-labeled) | 21 | 1.0 | 0.889 | 0.941 |
| Synthetic grant agreements | 9 | 1.0 | 1.0 | 1.0 |
| Synthetic service records | 8 | 1.0 | 1.0 | 1.0 |
| **Combined** | **108** | **1.0** | **0.970** | **0.985** |

Across all 108 documents: `citation_accuracy` 1.0, `unsupported_extraction_rate`
0.0, `abstention_quality` 1.0 — it never returned a value it could not cite,
and never invented one for an absent field. Latency 30–40s per document on
Apple M5 / MPS.

The APEX recall gap is a labeling convention, not a model error. All 21 misses
are `purchase_order_reference` on documents that print a matter number and no
PO. Scored against `manifest_apex_po_absent` (a matter number is not a PO) the
same predictions give F1 1.0 with 63 correct abstentions; against
`manifest_apex_po_matter` they give 0.941. The model abstained either way.
Refusing to promote a matter number into a purchase-order reference is the
answer an AP reviewer wants.

These numbers were measured on the **image** pipeline (`benchmark_base_model.py`
renders pages to PNG). `serve.py` runs the model on **text**, because the API's
payload carries page text only. That path is verified to work and to cite
correctly, but it has not been benchmarked at this scale — do not quote the
table above as evidence for it.

### Environment

Everything is declared in `pyproject.toml`; no git dependency is needed any
more. `transformers` 5.17 was the first stable release carrying NuExtract3's
`qwen3_5` architecture — an older one fails at load with `KeyError: 'qwen3_5'`,
which is why the floor is pinned. `torchvision` is required even though nothing
here touches video: loading the processor imports a video processor that needs
it, and the failure appears only when the model loads, not at install.

Model weights are ~9.3GB, Apache 2.0, not gated, and are downloaded on first
run into the Hugging Face cache — they are not in this repository.

    python3 -m venv .venv          # 3.10+; developed on 3.14
    .venv/bin/pip install -e .
    .venv/bin/python serve.py --port 8765

First start downloads the weights and hashes them (a few minutes); later starts
load in about seven seconds and the hash is cached beside the weights. The
service binds loopback only and refuses anything else.

### Registering it with the API

The API reaches the service through `SCHOOLTRACE_EXTRACTORS`, a JSON map its
`model_config` validates strictly — loopback endpoint, 64-hex artifact hash,
and an immutable training manifest. Read `artifact_sha256` off the running
service so the two agree; `infer()` rejects the response if they ever diverge.

    curl -s http://127.0.0.1:8765/health        # -> artifact_sha256

    export SCHOOLTRACE_EXTRACTORS='{"nuextract3-local": {
      "endpoint": "http://127.0.0.1:8765/",
      "artifact_sha256": "<from /health>",
      "base_revision": "<the model snapshot revision>",
      "training_document_hashes": [],
      "training_manifest_sha256": "<sha256 of an empty training manifest>",
      "training_groups": [],
      "supported_roles": ["invoice", "service", "grants", "policy", "document"]
    }}'

Training provenance is empty because the base model is served untouched.
Claiming otherwise would put a false statement into an audit trail.

Then `POST /api/workspaces/{ws}/extraction/models` with `{"name":
"nuextract3-local", "note": "..."}`. **Registration is per workspace** — a new
institution starts with an empty model list and needs its own registration.

Registering makes the model selectable per document; it does **not** make it
the active default, which requires passing the promotion gate in `POLICY`
(≥20 documents, ≥3 groups, ≥100 labeled fields, paired against a baseline).

## Model

Base: `numind/NuExtract3`, fine-tuned from Qwen3.5-4B, 4B parameters, BF16,
Apache 2.0, image-text-to-text (supports text, image, and multi-page PDF via
PyMuPDF page-to-PNG conversion). Template-guided extraction: you supply a
JSON template describing the fields you want (`"verbatim-string"`,
`"date-time"`, `"number"`, nested objects/arrays), the model returns JSON in
that shape.

spec.md and the brief both name NuExtract-class models as a starting
candidate, not a fixed requirement — benchmark the untouched base model
first (`scripts/benchmark_base_model.py`) and only fine-tune if it actually
improves results on your held-out set.

## Pipeline (mirrors spec.md §7.5's slow learning loop)

1. **Capture** — `data/manifest_schema.py` defines one training/eval example:
   the immutable source snapshot, schema version, requested template, and
   human-verified corrected output. Never a model's own unverified answer.
2. **Qualify** — an example is only admitted once its exact quotations
   resolve to the original source text and a human has approved the
   corrected labels (see `data/README.md`).
3. **Benchmark the base model** — `scripts/benchmark_base_model.py` runs the
   untouched model against held-out examples and reports the metrics in
   `scripts/evaluate.py`. Do this before writing any training code path that
   assumes fine-tuning is necessary.
4. **Train a candidate** — `scripts/train_lora.py`: supervised fine-tuning
   through a separate LoRA adapter (PEFT + TRL). Never mutates the base
   model or overwrites a prior adapter in place.
5. **Replay a frozen evaluation** — `scripts/evaluate.py`, splitting held-out
   data by institution/vendor/template (never randomly — near-duplicate
   templates must not leak across the split). Compares base vs. candidate.
6. **Promote explicitly** — only a human, after reviewing the evaluation
   report, moves a candidate adapter into use. Record dataset hash, code
   version, hyperparameters, base-model hash, adapter hash, and the
   evaluation result alongside the approval (spec.md §7.5 step 5).
7. **Monitor and retire** — out of scope for this first scaffold; route
   low-confidence extractions to human review once this is wired into intake.

## What this does NOT include yet (spec.md's own stated boundary)

Intake currently handles structured CSV and UTF-8 text. A trained extraction
model alone does not add PDF/scanned-document support to the running system —
PDF/image preprocessing, validated extraction staging, original-page
citations, and human acceptance before an extracted record enters accounting
all still need building on the `api/` side. This directory only trains and
evaluates the model; wiring its output into `api/app/ingestion.py` is a
separate, later integration task.

## Directory layout

```
extraction/
  schemas/
    evidence.py           # ExtractedField: value, original text, locator, status, quotation
    invoice.py             # target schema, invoices
    grant_agreement.py     # target schema, grant agreements
    service_record.py      # target schema, payroll/service records
    template.py             # Pydantic schema <-> NuExtract3 template-JSON conversion
  data/
    manifest_schema.py      # one training/eval example's required shape
    README.md               # labeling guidelines, required difficulty categories, split rule
  scripts/
    benchmark_base_model.py # step 3 above
    prepare_dataset.py      # manifest -> TRL SFT-ready examples
    train_lora.py           # step 4 above
    evaluate.py             # step 5 above; also used by step 3
```
