"""Run the untouched base model over a manifest and report the metrics
(spec.md §7.5 step 3 — benchmark before fine-tuning anything).

Usage:
    python scripts/benchmark_base_model.py manifest.json --limit 5 --out predictions.json
    python scripts/benchmark_base_model.py manifest.json --predictions predictions.json  # re-score, no inference

Measured on Apple M5 / MPS, 2026-09-19: ~197s per invoice page, because the
optimized `causal_conv1d` / `flash-linear-attention` kernels are CUDA-only
and MPS falls back to reference PyTorch implementations. Budget accordingly —
a full 112-document pass is roughly 6 hours on that hardware. Predictions are
written to --out so scoring can be re-run offline for free after a parser or
metric change, which is why inference and scoring are separate steps here.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.manifest_schema import ManifestEntry, load_manifest  # noqa: E402
from schemas import grant_agreement, invoice, service_record  # noqa: E402
from scripts.evaluate import ExampleResult, aggregate, format_report, score_fields  # noqa: E402

SCHEMA_MODULES = {
    "invoice": invoice,
    "grant_agreement": grant_agreement,
    "service_record": service_record,
}

MODEL_ID = "numind/NuExtract3"


def render_page_png(pdf_path: str, page: int, out_dir: Path) -> tuple[str, str]:
    """Render one page to PNG and also return its embedded text (used for
    citation checking — the quotation has to resolve against something).

    The document is closed explicitly. Leaving it open leaked one handle plus
    its pixmap per document; across 112 multi-page packets that was enough to
    exhaust unified memory and push the machine into swap, which took
    per-document time from 28s to 615s mid-run.
    """
    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        page_obj = doc[page - 1]
        png_path = out_dir / f"{Path(pdf_path).stem}_p{page}.png"
        pixmap = page_obj.get_pixmap(dpi=150)
        pixmap.save(str(png_path))
        text = page_obj.get_text()
        del pixmap
        return str(png_path), text
    finally:
        doc.close()


def load_model(device: str):
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID, dtype=torch.bfloat16, device_map=device, trust_remote_code=True
    )
    processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    # Decoder-only batched generation needs left padding, or short prompts
    # get their completions read from the wrong offset.
    processor.tokenizer.padding_side = "left"
    return model, processor


def extract_batch(
    model, processor, png_paths: list[str], template: dict, max_new_tokens: int
) -> tuple[list[str], float]:
    """Batched generation. Measured on Apple M5 / MPS (header-only invoice
    template, greedy):

        batch 1 -> 54.3s/doc    batch 2 -> 38.2s/doc
        batch 4 -> 30.1s/doc    batch 8 -> 29.9s/doc

    Autoregressive decode is memory-bandwidth bound, so batching amortizes
    per-step cost until it plateaus — which it does at 4 here. Going to 8
    bought nothing and only raises the out-of-memory risk on 24GB unified
    memory, so 4 is the default.
    """
    import torch

    batch = [[{"role": "user", "content": [{"type": "image", "path": path}]}] for path in png_paths]
    inputs = processor.apply_chat_template(
        batch,
        template=json.dumps(template),
        tokenize=True,
        return_dict=True,
        add_generation_prompt=True,
        return_tensors="pt",
        padding=True,
    ).to(model.device)

    started = time.time()
    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    elapsed = time.time() - started

    # Left padding (set in load_model) makes the prompt length uniform, so
    # every row's completion starts at the same offset.
    prompt_len = inputs["input_ids"].shape[1]
    texts = [processor.decode(row[prompt_len:], skip_special_tokens=True) for row in output]

    # Release the batch's tensors and hand the allocator's cache back. Without
    # this the MPS allocator grew across batches until the machine swapped;
    # measured degradation was 28s -> 615s per document by batch five.
    del inputs, output
    _empty_device_cache()
    return texts, elapsed


def _empty_device_cache() -> None:
    import torch

    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
    elif torch.cuda.is_available():
        torch.cuda.empty_cache()


def _peak_memory_gb() -> float | None:
    from scripts.evaluate import current_peak_memory_gb

    return current_peak_memory_gb()


def build_template_for(module, skip_list_fields: bool) -> dict:
    """skip_list_fields drops repeating structures (invoice line items, grant
    amendments) from the request.

    This is an EVALUATION-ONLY shortcut, not a schema change. It is correct
    only when the manifest carries no labels for those fields — then every
    line-item token generated is unscored cost. Measured: dropping line items
    took an invoice from 92.5s to 54.3s per document for identical scores on
    the eight fields that are actually labeled. If your manifest does label
    list fields, leave this off or you will score them all as missed.
    """
    if not skip_list_fields:
        return module.template()
    from schemas.template import build_template

    return build_template(module.SCALAR_FIELDS)


def run_inference(
    entries: list[ManifestEntry],
    device: str,
    max_new_tokens: int,
    work_dir: Path,
    batch_size: int,
    skip_list_fields: bool,
    out_path: Path | None = None,
    resume: bool = True,
) -> list[dict]:
    """Writes each batch's predictions to out_path as it goes. A long run on
    unreliable hardware should never lose an hour of completed inference to a
    kill or an OOM — and with resume=True a rerun picks up where it stopped."""
    records: list[dict] = []
    if resume and out_path and out_path.exists():
        records = json.loads(out_path.read_text(encoding="utf-8"))
        completed = {r["example_id"] for r in records}
        entries = [e for e in entries if e.example_id not in completed]
        print(f"resuming: {len(completed)} already done, {len(entries)} remaining", flush=True)
        if not entries:
            return records

    model, processor = load_model(device)
    work_dir.mkdir(parents=True, exist_ok=True)

    done = len(records)
    total = done + len(entries)
    for start in range(0, len(entries), batch_size):
        chunk = entries[start : start + batch_size]
        # One template per batch, so a batch must be homogeneous by doc type.
        chunk_by_type: dict[str, list[ManifestEntry]] = {}
        for entry in chunk:
            chunk_by_type.setdefault(entry.document_type, []).append(entry)

        for doc_type, group in chunk_by_type.items():
            template = build_template_for(SCHEMA_MODULES[doc_type], skip_list_fields)
            rendered = [render_page_png(e.document_path, e.page, work_dir) for e in group]
            texts, elapsed = extract_batch(
                model, processor, [png for png, _ in rendered], template, max_new_tokens
            )
            per_doc = elapsed / len(group)
            peak_gb = _peak_memory_gb()
            for entry, (_, page_text), text in zip(group, rendered, texts):
                done += 1
                print(f"[{done}/{total}] {entry.example_id}: {per_doc:.1f}s (batched)", flush=True)
                records.append(
                    {
                        "example_id": entry.example_id,
                        "raw_output": text,
                        "page_text": page_text,
                        "latency_s": per_doc,
                        "peak_memory_gb": peak_gb,
                    }
                )
            if out_path:  # checkpoint after every batch, not just at the end
                out_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return records


def score(entries: list[ManifestEntry], records: list[dict]) -> list[ExampleResult]:
    by_id = {record["example_id"]: record for record in records}
    results: list[ExampleResult] = []

    for entry in entries:
        record = by_id.get(entry.example_id)
        if record is None:
            continue
        module = SCHEMA_MODULES[entry.document_type]

        try:
            parsed_json = json.loads(record["raw_output"])
            valid_json = True
        except json.JSONDecodeError:
            parsed_json, valid_json = {}, False

        predicted = module.parse(parsed_json)["fields"] if valid_json else {}

        results.append(
            ExampleResult(
                example_id=entry.example_id,
                split_key=entry.split_key,
                valid_json=valid_json,
                fields=score_fields(entry.expected_fields, predicted, record.get("page_text")),
                latency_s=record.get("latency_s"),
                peak_memory_gb=record.get("peak_memory_gb"),
            )
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--limit", type=int, default=None, help="Score only the first N entries.")
    parser.add_argument("--device", default="mps", help="mps | cuda | cpu")
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=4, help="Throughput plateaus at 4 on MPS.")
    parser.add_argument(
        "--skip-list-fields",
        action="store_true",
        help="Omit line items/amendments from the request. Only valid when the manifest "
        "carries no labels for them — see build_template_for().",
    )
    parser.add_argument("--out", default=None, help="Write predictions JSON here.")
    parser.add_argument("--predictions", default=None, help="Re-score saved predictions; skips inference.")
    parser.add_argument("--work-dir", default="/tmp/extraction-pages")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing --out and start over.")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    entries = manifest.entries[: args.limit] if args.limit else manifest.entries

    if args.predictions:
        records = json.loads(Path(args.predictions).read_text(encoding="utf-8"))
    else:
        records = run_inference(
            entries,
            args.device,
            args.max_new_tokens,
            Path(args.work_dir),
            batch_size=args.batch_size,
            skip_list_fields=args.skip_list_fields,
            out_path=Path(args.out) if args.out else None,
            resume=not args.no_resume,
        )
        if args.out:
            print(f"wrote predictions -> {args.out}")

    results = score(entries, records)
    summary = aggregate(results)
    print()
    print(format_report(summary, title=f"{MODEL_ID} (base) on {args.manifest}"))

    failures = [
        (r.example_id, f.field_name, f.expected, f.predicted, f.outcome.value)
        for r in results
        for f in r.fields
        if f.outcome.value in ("wrong_value", "missed", "over_extracted")
    ]
    if failures:
        print("\nfailures (example, field, expected, predicted, outcome):")
        for row in failures[:40]:
            print(f"  {row}")


if __name__ == "__main__":
    main()
