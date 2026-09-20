# Document Extraction Model

Trains and evaluates the local document-extraction model spec.md §5/§7.5
describes: turns documents into structured, source-backed facts for all five
financial agents. It is not the CFO or Internal Auditor, and it must never
calculate financial results, approve changes, or convert an extraction into
an audit conclusion (spec.md §5) — that stays deterministic backend code and
human review, same as everywhere else in this project.

**Nothing in this directory has been executed against the real model.** Every
other agent in this repo was proven against a live API call before being
called done; this one couldn't be, for a concrete, verified reason below —
not a guess. Treat this as scaffolding to pick up on a machine that clears
the hardware/software bar, not as tested code.

## What was actually verified, and where it stopped

Checked live, on an Apple M5 / 24GB / macOS sandbox, 2026-09-19:

- `torch` 2.8.0 with the MPS backend works (`torch.backends.mps.is_available() == True`).
- `numind/NuExtract3` (the base model — see "Model" below) is **not gated**, Apache 2.0,
  ~9.34GB total (mostly one 9.08GB `model.safetensors`). Downloads fine.
- **Blocker:** its architecture (`qwen3_5`) is not recognized by any stable
  `transformers` release — 4.57.6 (latest on PyPI) fails with
  `KeyError: 'qwen3_5'`, and there is no newer pre-release wheel either.
- The only place `qwen3_5` support exists is the `transformers` GitHub main
  branch — which now requires **Python >=3.10**. The sandbox this was
  attempted in only had system Python 3.9.6 available, with no Homebrew,
  pyenv, or `uv` to install a newer one, so loading the model itself could not
  be attempted.

**Concrete requirement for whoever runs this next: Python 3.10+ (3.11/3.12
recommended), then `pip install git+https://github.com/huggingface/transformers.git`**
— a stable-release install will not recognize the architecture. Re-check this
before assuming it's still true; `transformers` ships fast and `qwen3_5`
support may land in a stable release by the time you read this.

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
