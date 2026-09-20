"""Supervised fine-tuning of a LoRA adapter over the base extraction model
(spec.md §7.5 step 3, brief §4).

Trains an adapter only — the base model is never modified and a prior
adapter is never overwritten in place (spec.md: "Never mutate the production
adapter in place"). Each run writes to its own output directory and records
a provenance sidecar (dataset hash, base model, hyperparameters, code
version) so step 5's promotion decision has something to record.

NOT VALIDATED: unlike the inference path (benchmark_base_model.py, confirmed
working on MPS against real documents), this training path has not been
executed. Remaining risk before trusting it:

  * MPS is a poor fit for training. bitsandbytes 4-bit/QLoRA has no MPS
    support, so `--load-in-4bit` is CUDA-only, and backward passes through a
    4B vision-language model on unified memory are slow and memory-hungry.
    Budget for a CUDA machine; measured MPS *inference* alone was ~197s/page
    before optimization, ~29s after.

`target_modules` WAS a risk and is now resolved: the names were verified
against the real model, which turned out to be a hybrid architecture whose
linear-attention layers the obvious target list would have skipped. See the
comment on DEFAULT_TARGET_MODULES.

Usage:
    python scripts/train_lora.py train.jsonl --out adapters/invoice-v1 --epochs 2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

MODEL_ID = "numind/NuExtract3"

# Verified against model.named_modules() on numind/NuExtract3 (2026-09-20).
#
# The language model is a HYBRID: of its 32 decoder layers, only 8 use standard
# attention (`self_attn.q_proj/k_proj/v_proj/o_proj`); the other 24 use gated
# linear attention (`linear_attn.in_proj_*`) — the same mechanism behind the
# `chunk_gated_delta_rule` / `causal_conv1d` kernel warnings at load time.
#
# Targeting only the q/k/v/o names would adapt all 32 MLP blocks but just 8 of
# 32 attention blocks, skipping 24 of them, while training completed normally
# and the loss fell. That is the "trains almost nothing and still looks fine"
# failure this list has to avoid.
#
# Vision tower modules (model.visual.*: `qkv`, `proj`, `out_proj`,
# `linear_fc1/2`) are deliberately excluded — these documents are digital-native
# text where the language side does the work, and freezing the encoder keeps the
# adapter small. Note `proj`/`qkv` are vision-only names, so adding them would
# silently pull in the encoder.
DEFAULT_TARGET_MODULES = [
    # standard attention (8 layers)
    "q_proj", "k_proj", "v_proj", "o_proj",
    # gated linear attention (24 layers)
    "in_proj_qkv", "in_proj_z", "in_proj_a", "in_proj_b",
    # MLP (all 32 layers)
    "gate_proj", "up_proj", "down_proj",
]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_version() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def build_dataset(records_path: Path):
    """Each row becomes a chat example: the page image plus the requested
    template in, the verified JSON out."""
    from datasets import Dataset
    import pymupdf

    rows = []
    for line in records_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)

        doc = pymupdf.open(record["document_path"])
        png_path = Path("/tmp/extraction-train-pages") / f"{Path(record['document_path']).stem}_p{record['page']}.png"
        png_path.parent.mkdir(parents=True, exist_ok=True)
        doc[record["page"] - 1].get_pixmap(dpi=150).save(str(png_path))

        rows.append(
            {
                "images": [str(png_path)],
                "template": json.dumps(record["template"]),
                "completion": json.dumps(record["target"]),
                "split_key": record["split_key"],
            }
        )
    return Dataset.from_list(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("train_jsonl")
    parser.add_argument("--out", required=True, help="Adapter output dir. Must not already exist.")
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--device", default="cuda", help="cuda strongly recommended; see docstring")
    parser.add_argument("--load-in-4bit", action="store_true", help="CUDA only (bitsandbytes).")
    args = parser.parse_args()

    out_dir = Path(args.out)
    if out_dir.exists():
        raise SystemExit(f"{out_dir} already exists — never overwrite an adapter in place (spec.md §7.5).")

    import torch
    from peft import LoraConfig
    from transformers import AutoModelForImageTextToText, AutoProcessor
    from trl import SFTConfig, SFTTrainer

    load_kwargs: dict = {"dtype": torch.bfloat16, "device_map": args.device, "trust_remote_code": True}
    if args.load_in_4bit:
        from transformers import BitsAndBytesConfig

        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
        )

    model = AutoModelForImageTextToText.from_pretrained(MODEL_ID, **load_kwargs)
    processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)

    dataset = build_dataset(Path(args.train_jsonl))
    print(f"training rows: {len(dataset)} | split_keys: {len(set(dataset['split_key']))}")

    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=DEFAULT_TARGET_MODULES,
    )

    sft_config = SFTConfig(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        gradient_checkpointing=True,
        logging_steps=1,
        save_strategy="epoch",
        bf16=True,
        report_to=[],
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=dataset,
        peft_config=peft_config,
        processing_class=processor,
    )

    started = time.time()
    trainer.train()
    trainer.save_model(str(out_dir))

    provenance = {
        "base_model": MODEL_ID,
        "dataset_file": str(args.train_jsonl),
        "dataset_sha256": file_sha256(Path(args.train_jsonl)),
        "code_version": code_version(),
        "train_rows": len(dataset),
        "split_keys": sorted(set(dataset["split_key"])),
        "hyperparameters": {
            "epochs": args.epochs,
            "lr": args.lr,
            "batch_size": args.batch_size,
            "grad_accum": args.grad_accum,
            "lora_r": args.lora_r,
            "lora_alpha": args.lora_alpha,
            "lora_dropout": args.lora_dropout,
            "load_in_4bit": args.load_in_4bit,
            "target_modules": DEFAULT_TARGET_MODULES,
        },
        "wall_clock_s": round(time.time() - started, 1),
        "promoted": False,  # only a human flips this, after evaluate.py (spec.md §7.5 step 5)
    }
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(f"\nadapter + provenance -> {out_dir}")
    print("NOT promoted. Run scripts/benchmark_base_model.py against held-out data and compare to base first.")


if __name__ == "__main__":
    main()
