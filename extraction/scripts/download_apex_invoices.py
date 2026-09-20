"""Download the APEX-Accounting contract-attorney invoices and emit a
pre-filled labeling worksheet.

Source: https://huggingface.co/datasets/mercor/apex-accounting (CC BY 4.0,
arXiv 2607.27189, Mercor + Ramp). Only the public dev world is downloadable;
the 160-task private eval set is not. These 21 PDFs are supporting documents
inside that world (a synthetic law firm's accounts-payable file), not tasks,
so they ship with no extraction labels — hence the worksheet.

Why bother when we already have 112 labeled invoices: those are all one
issuer on one template, and they're accounts *receivable*. These are three
different issuers on three different layouts, and they're accounts payable —
the direction the AP agent actually works in, which makes `vendor_name`
testable for the first time.

The PDFs are not committed to this repo. They belong to someone else's
dataset and are re-fetchable in seconds; --out defaults to a gitignored
directory.

Usage:
    python scripts/download_apex_invoices.py --out data/apex_invoices
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from pathlib import Path

REPO = "mercor/apex-accounting"
SUBDIR = "world/filesystem/contract_attorney_invoices"

# Fields a regex can lift unambiguously from the page text. Pre-filling these
# is NOT the same as labeling them with a model: it's deterministic text
# extraction, so it stays admissible once a human verifies it
# (label_source=human_verified). Never pre-fill with the model under
# evaluation — that is circular, and model_proposed labels are inadmissible
# for training anyway (spec.md §7.5 step 2).
AUTO_FIELDS = {
    "invoice_number": r"Invoice No\.\s*\n?\s*(\S+)",
    "invoice_date": r"Invoice Date:\s*([^\n]+)",
    "payment_due_date": r"Due Date:\s*([^\n]+)",
    "subtotal": r"Subtotal:\s*\n?\s*\$?([\d,\.]+)",
    "total": r"Total Due:\s*\n?\s*\$?([\d,\.]+)",
}

# Fields that need a human decision, with the reason spelled out in the
# worksheet header so the labeler isn't guessing at intent.
JUDGMENT_FIELDS = {
    "vendor_name": "Issuer as you want it recorded — 'Marcus Avila, Esq.' or 'Marcus Avila'? Be consistent.",
    "currency": "Shown only as '$', never 'USD'. Decide: $ / USD / leave blank for absent.",
    "service_date": "Line item is dated, prose may name a different period. Which is the service date? Blank = absent.",
    "tax": "No tax line appears on these. Confirm, then leave blank for absent.",
    "purchase_order_reference": "Each has 'Matter Reference: M-...'. Is a matter a PO? Blank = absent (an abstention test).",
    "receipt_reference": "None seen. Confirm, then leave blank for absent.",
}


def page_text(pdf_path: Path) -> str:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        return doc[0].get_text()
    finally:
        doc.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/apex_invoices")
    parser.add_argument("--worksheet", default="data/apex_labeling_worksheet.csv")
    args = parser.parse_args()

    from huggingface_hub import HfApi, hf_hub_download

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = [s.rfilename for s in HfApi().dataset_info(REPO).siblings if s.rfilename.startswith(SUBDIR)]
    for remote in sorted(files):
        cached = hf_hub_download(REPO, remote, repo_type="dataset")
        shutil.copy(cached, out_dir / Path(remote).name)
    print(f"downloaded {len(files)} invoices -> {out_dir}")

    rows = []
    for pdf in sorted(out_dir.glob("*.pdf")):
        text = page_text(pdf)
        row = {"file": pdf.name}
        for field, pattern in AUTO_FIELDS.items():
            match = re.search(pattern, text)
            row[field] = match.group(1).strip().replace(",", "") if match else ""
        for field in JUDGMENT_FIELDS:
            row[field] = ""
        matter = re.search(r"Matter Reference:\s*([^\n]+)", text)
        row["_hint_matter_reference"] = matter.group(1).strip() if matter else ""
        row["_hint_first_line"] = text.split("\n")[0].strip()
        rows.append(row)

    worksheet = Path(args.worksheet)
    worksheet.parent.mkdir(parents=True, exist_ok=True)
    with worksheet.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote worksheet -> {worksheet}")
    print(f"\n  pre-filled (verify these):  {', '.join(AUTO_FIELDS)}")
    print(f"  needs your judgment:        {', '.join(JUDGMENT_FIELDS)}")
    print("\n  Columns starting with _hint are context for you; they are ignored on import.")
    print("  A blank cell means the field is genuinely ABSENT — that is a real label,")
    print("  scored as correct_abstention, not a gap.")
    print(f"\nNext: fill it in, then run\n  python scripts/worksheet_to_manifest.py {worksheet} --pdf-dir {out_dir} --out manifest_apex.json")


if __name__ == "__main__":
    main()
