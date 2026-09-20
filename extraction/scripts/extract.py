"""Extract structured, evidence-backed fields from one document.

This is the inference entry point — the thing that actually *uses* the model,
as opposed to benchmark_base_model.py, which evaluates it. Everything else in
this directory measures; this is what a caller invokes.

    from scripts.extract import Extractor
    extractor = Extractor(device="mps")                     # loads once, reuse it
    result = extractor.extract("invoice.pdf", "invoice")
    for name, field in result.fields.items():
        print(name, field.raw.value, field.raw.status, field.raw.quotation)

CLI:
    python scripts/extract.py invoice.pdf --type invoice
    python scripts/extract.py award.pdf --type grant_agreement --json

Returns ExtractedField objects, not bare values: every field carries its
status, the verbatim source text, and document attribution the *application*
supplies (id, version, hash, model version) rather than the model. A bare
value with no provenance is not something this project lets into accounting —
see schemas/evidence.py.

Loading the model costs ~9s from cache and ~9.3GB; construct one Extractor and
reuse it rather than calling a module-level helper per document.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import grant_agreement, invoice, service_record  # noqa: E402
from schemas.evidence import ExtractedField, RawExtraction  # noqa: E402

SCHEMA_MODULES = {
    "invoice": invoice,
    "grant_agreement": grant_agreement,
    "service_record": service_record,
}

MODEL_ID = "numind/NuExtract3"
DEFAULT_MAX_NEW_TOKENS = 1024


@dataclass
class ExtractionResult:
    document_id: str
    document_type: str
    schema_version: str
    fields: dict[str, ExtractedField]
    list_fields: dict[str, list[dict[str, RawExtraction]]] = dataclass_field(default_factory=dict)
    raw_output: str = ""
    valid_json: bool = True
    latency_s: float = 0.0
    page_text: str = ""

    def unsupported(self) -> list[str]:
        """Fields claiming a value with no quotation to back it. spec.md §7.5
        tracks this as its own metric because an unsupported extraction is
        the one that looks like evidence without being any."""
        return [name for name, f in self.fields.items() if not f.raw.is_supported()]

    def uncited(self) -> list[str]:
        """Fields whose quotation does not actually occur in the page text.
        Checked here, not trusted from the model."""
        from scripts.evaluate import citation_resolves

        return [
            name
            for name, f in self.fields.items()
            if citation_resolves(f.raw.quotation, self.page_text) is False
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_type": self.document_type,
            "schema_version": self.schema_version,
            "valid_json": self.valid_json,
            "latency_s": round(self.latency_s, 2),
            "fields": {
                name: {
                    "value": f.raw.value,
                    "status": f.raw.status.value,
                    "quotation": f.raw.quotation,
                    "document_hash": f.document_hash,
                    "extraction_method": f.extraction_method,
                }
                for name, f in self.fields.items()
            },
            "list_fields": {
                name: [{k: v.value for k, v in row.items()} for row in rows]
                for name, rows in self.list_fields.items()
            },
            "unsupported_fields": self.unsupported(),
            "uncited_fields": self.uncited(),
        }


class Extractor:
    def __init__(self, device: str = "mps", model_id: str = MODEL_ID, dpi: int = 150):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self.model_id = model_id
        self.dpi = dpi
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_id, dtype=torch.bfloat16, device_map=device, trust_remote_code=True
        )
        self.processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        self.processor.tokenizer.padding_side = "left"

    def extract(
        self,
        document_path: str,
        document_type: str,
        *,
        page: int = 1,
        include_list_fields: bool = True,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        document_version: str = "1",
    ) -> ExtractionResult:
        if document_type not in SCHEMA_MODULES:
            raise ValueError(f"unknown document_type {document_type!r}; expected one of {sorted(SCHEMA_MODULES)}")

        module = SCHEMA_MODULES[document_type]
        path = Path(document_path)
        doc_hash = hashlib.sha256(path.read_bytes()).hexdigest()

        png_path, page_text = self._render(path, page)
        template = module.template() if include_list_fields else self._scalar_template(module)

        raw_text, elapsed = self._generate(png_path, template, max_new_tokens)

        try:
            parsed = json.loads(raw_text)
            valid_json = True
        except json.JSONDecodeError:
            parsed, valid_json = {}, False

        parsed_result = module.parse(parsed)
        fields = {
            name: ExtractedField.attach(
                raw,
                document_id=path.name,
                document_version=document_version,
                document_hash=doc_hash,
                extraction_method=f"{self.model_id}-base",
                schema_version=module.SCHEMA_VERSION,
            )
            for name, raw in parsed_result["fields"].items()
        }
        list_fields = {k: v for k, v in parsed_result.items() if k != "fields"}

        return ExtractionResult(
            document_id=path.name,
            document_type=document_type,
            schema_version=module.SCHEMA_VERSION,
            fields=fields,
            list_fields=list_fields,
            raw_output=raw_text,
            valid_json=valid_json,
            latency_s=elapsed,
            page_text=page_text,
        )

    @staticmethod
    def _scalar_template(module) -> dict:
        from schemas.template import build_template

        return build_template(module.SCALAR_FIELDS)

    def _render(self, path: Path, page: int) -> tuple[str, str]:
        import pymupdf

        doc = pymupdf.open(path)
        try:
            page_obj = doc[page - 1]
            png_path = Path("/tmp/extraction-inference") / f"{path.stem}_p{page}.png"
            png_path.parent.mkdir(parents=True, exist_ok=True)
            pixmap = page_obj.get_pixmap(dpi=self.dpi)
            pixmap.save(str(png_path))
            text = page_obj.get_text()
            del pixmap
            return str(png_path), text
        finally:
            doc.close()  # leaking these exhausted unified memory in a long run

    def _generate(self, png_path: str, template: dict, max_new_tokens: int) -> tuple[str, float]:
        import torch

        messages = [[{"role": "user", "content": [{"type": "image", "path": png_path}]}]]
        inputs = self.processor.apply_chat_template(
            messages,
            template=json.dumps(template),
            tokenize=True,
            return_dict=True,
            add_generation_prompt=True,
            return_tensors="pt",
            padding=True,
        ).to(self.model.device)

        started = time.time()
        with torch.no_grad():
            output = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        elapsed = time.time() - started

        text = self.processor.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        del inputs, output
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        return text, elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document")
    parser.add_argument("--type", required=True, choices=sorted(SCHEMA_MODULES))
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--device", default="mps")
    parser.add_argument("--no-list-fields", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table.")
    args = parser.parse_args()

    result = Extractor(device=args.device).extract(
        args.document, args.type, page=args.page, include_list_fields=not args.no_list_fields
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        return

    print(f"{result.document_id}  [{result.document_type} / {result.schema_version}]")
    print(f"valid_json={result.valid_json}  latency={result.latency_s:.1f}s\n")
    for name, f in result.fields.items():
        value = f.raw.value if f.raw.value is not None else "—"
        print(f"  {name:28} {f.raw.status.value:10} {value}")
    for list_name, rows in result.list_fields.items():
        print(f"\n  {list_name}: {len(rows)} row(s)")
        for row in rows:
            print("    " + ", ".join(f"{k}={v.value}" for k, v in row.items() if v.value))

    if result.unsupported():
        print(f"\n  UNSUPPORTED (value with no quotation): {result.unsupported()}")
    if result.uncited():
        print(f"  UNCITED (quotation not found in page text): {result.uncited()}")


if __name__ == "__main__":
    main()
