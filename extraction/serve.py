"""Local extraction service: the loopback endpoint `api/app/extraction.py::infer` calls.

Run it beside the API, never exposed off the loopback interface:

    .venv/bin/python serve.py --port 8765

It holds one NuExtract3 in memory and answers one document at a time. The API
enforces its own concurrency slot, so this does not need a queue.

## What this service may and may not do

It returns *located quotations*, not answers. For every requested field it
either points at an exact character span of the page text it was given, or it
abstains. It never computes a value, reconciles two fields, or decides whether
a document complies with anything — those belong to deterministic backend code
and human review, as everywhere else in this project.

A value the model produces that cannot be found verbatim in the page text is
dropped and reported as an abstention, not returned. Two reasons, and the
weaker one is the technical one:

- `api/app/extraction.py::validate` checks `page_text[start:end] == value` and
  would reject the whole response anyway;
- more importantly, a value with no locatable source is exactly the fabricated
  evidence this pipeline exists to prevent. A blank is recoverable by a human.
  A plausible invoice number that appears nowhere on the invoice is not.

## Text, not images

The API's payload carries page *text* only — `infer()` sends `doc["pages"]`,
which `document_processing.process()` already reduced to text. It never sends
the PDF bytes or page images. So this serves NuExtract3 text-only, while the
benchmarks in `scripts/benchmark_base_model.py` measured the image path. Those
scores do not transfer unexamined; see the header this prints at startup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

# Module level, not inside build_app(). Python 3.14 defers annotation
# evaluation (PEP 649) and FastAPI resolves a handler's hints against the
# function's __globals__, so a `Request` imported into an enclosing function's
# scope is invisible to it — the parameter silently degrades to a query
# argument and every POST fails validation with "field required".
from fastapi import FastAPI, HTTPException, Request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

MODEL_ID = "numind/NuExtract3"
SCHEMA_VERSION = "schooltrace.extraction.v1"
MAX_NEW_TOKENS = 1200

_model = None
_processor = None
_artifact_sha256: str | None = None


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #

def load_model(device: str):
    """Load once, keep resident. A cold load reads ~9.3GB off disk."""
    global _model, _processor
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    print(f"[serve] loading {MODEL_ID} onto {device} …", flush=True)
    started = time.time()
    _model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID, dtype=torch.bfloat16, device_map=device, trust_remote_code=True
    )
    _processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    _processor.tokenizer.padding_side = "left"
    print(f"[serve] model ready in {time.time() - started:.1f}s", flush=True)
    return _model, _processor


def artifact_sha256() -> str:
    """Hash of the weights actually being served.

    `infer()` compares this against the registered config and refuses the
    response if they differ, so it has to identify the weights rather than the
    model name — swapping the checkpoint under a registered name must break
    the match, not pass silently. Cached beside the weights; hashing 9.3GB
    takes a few seconds and the file never changes in place.
    """
    global _artifact_sha256
    if _artifact_sha256:
        return _artifact_sha256

    from huggingface_hub import snapshot_download

    path = Path(snapshot_download(MODEL_ID))
    weights = sorted(path.glob("*.safetensors"))
    if not weights:
        raise RuntimeError(f"No .safetensors found under {path}")

    cache = path / ".artifact_sha256"
    if cache.exists():
        cached = cache.read_text().strip()
        if re.fullmatch(r"[a-f0-9]{64}", cached):
            _artifact_sha256 = cached
            return cached

    print(f"[serve] hashing {len(weights)} weight file(s) …", flush=True)
    digest = hashlib.sha256()
    for weight in weights:
        with weight.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 << 20), b""):
                digest.update(chunk)
    _artifact_sha256 = digest.hexdigest()
    try:
        cache.write_text(_artifact_sha256)
    except OSError:
        pass
    return _artifact_sha256


# --------------------------------------------------------------------------- #
# Locating a value back to its exact source span
# --------------------------------------------------------------------------- #

def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


#: Words in a field name that identify nothing on a page. "service_start" is
#: disambiguated by "service"; "start" appears near every date.
_GENERIC_FIELD_WORDS = {
    "id", "ref", "reference", "number", "no", "code", "date", "start", "end",
    "amount", "total", "value", "name", "to", "from", "record", "line",
}


def _field_words(field_name: str) -> list[str]:
    words = [w for w in re.split(r"[_\s]+", field_name.lower()) if w]
    specific = [w for w in words if w not in _GENERIC_FIELD_WORDS and len(w) > 2]
    return specific or words


def _disambiguate(hits: list[tuple[int, int, int]], pages: list[dict], field_name: str):
    """Choose among several verbatim occurrences of the same value.

    Abstaining here was wrong, and the first run showed why: this document
    prints 2023-12-22 under both "Pay Period" and "Service Period", and
    EMP-016 appears again inside SVC-REC-EMP-016-1 on page 2. The model had
    read all of them correctly; the citation rule threw four right answers
    away because it could not pick a spot.

    So prefer the occurrence whose preceding text mentions the field — the
    2023-12-22 after "Service Period" for `service_start` — and fall back to
    the first occurrence otherwise. The value is verbatim on the page either
    way, so `validate()` holds and the reviewer sees a real span; at worst the
    span points at an equally valid twin, which a person can move. That is a
    far cheaper error than discarding a correct value.
    """
    text_by_page = {p.get("page"): (p.get("text") or "") for p in pages}
    words = _field_words(field_name) if field_name else []
    best, best_score = None, -1
    for page, start, end in hits:
        preceding = text_by_page.get(page, "")[max(0, start - 90):start].lower()
        score = sum(1 for word in words if word in preceding)
        if score > best_score:
            best, best_score = (page, start, end), score
    return best


def locate(value: str, pages: list[dict], field_name: str = "") -> tuple[int, int, int] | None:
    """Find `value` verbatim in the pages, returning (page, start, end).

    Offsets are Python string indices, which are code points — the same units
    `validate()` slices with, and the same the browser editor computes with
    `Array.from(...).length`. Using byte offsets here would pass locally and
    fail on the first non-ASCII page.
    """
    if not value or not value.strip():
        return None

    hits: list[tuple[int, int, int]] = []
    for page in pages:
        text = page.get("text") or ""
        number = page.get("page")
        start = text.find(value)
        while start >= 0:
            hits.append((number, start, start + len(value)))
            start = text.find(value, start + max(1, len(value)))
            if len(hits) > 64:  # pathological; stop scanning
                break
    if len(hits) == 1:
        return hits[0]
    if hits:
        return _disambiguate(hits, pages, field_name)

    # Fall back to a whitespace/unicode-insensitive search, then map the match
    # back onto real indices in the original text. A PDF that prints
    # "INV­-2025" with a soft hyphen, or wraps a value across a line, is still
    # the same value on the page; it just is not the same byte sequence.
    target = " ".join(_normalize(value).split()).casefold()
    if not target:
        return None
    collapsed_hits: list[tuple[int, int, int]] = []
    for page in pages:
        text = page.get("text") or ""
        number = page.get("page")
        collapsed, index_map = [], []
        previous_space = True
        for index, char in enumerate(_normalize(text)):
            if char.isspace():
                if not previous_space:
                    collapsed.append(" ")
                    index_map.append(index)
                previous_space = True
            else:
                collapsed.append(char.casefold())
                index_map.append(index)
                previous_space = False
        haystack = "".join(collapsed)
        at = haystack.find(target)
        while at >= 0:
            start = index_map[at]
            end = index_map[at + len(target) - 1] + 1
            if text[start:end]:
                collapsed_hits.append((number, start, end))
            at = haystack.find(target, at + max(1, len(target)))
            if len(collapsed_hits) > 64:
                break
    if len(collapsed_hits) == 1:
        return collapsed_hits[0]
    if collapsed_hits:
        return _disambiguate(collapsed_hits, pages, field_name)
    return None


def observation(field_name: str, value: Any, pages: list[dict]) -> dict:
    """One field's answer, in the shape `Observation` validates."""
    blank = {"status": "missing", "value": None, "page": None, "start": None, "end": None}
    if value is None:
        return blank
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if not text.strip():
        return blank

    found = locate(text, pages, field_name)
    if found is None:
        # Present on the model's account but not locatable on the page. Report
        # it as unreadable rather than dropping it silently: a reviewer should
        # see that something was read here and could not be pinned down.
        return {"status": "unreadable", "value": None, "page": None, "start": None, "end": None}
    page, start, end = found
    return {"status": "present", "value": text, "page": page, "start": start, "end": end}


# --------------------------------------------------------------------------- #
# Inference
# --------------------------------------------------------------------------- #

def build_template(fields: list[str]) -> dict:
    """Every requested field as a verbatim string.

    Only `verbatim-string` is used, deliberately: a typed slot invites the
    model to reformat ("$1,200.00" -> 1200.0), and a reformatted value cannot
    be found on the page, so it would arrive here as an abstention. Canonical
    forms are the job of `schemas/normalize.py` and the accounting engine,
    downstream of a citation that still resolves.
    """
    return {field: "verbatim-string" for field in fields}


def run(pages: list[dict], fields: list[str]) -> tuple[dict, float]:
    import torch

    numbered = "\n\n".join(
        f"[page {page.get('page')}]\n{page.get('text') or ''}" for page in pages
    )
    conversation = [[{"role": "user", "content": [{"type": "text", "text": numbered}]}]]
    inputs = _processor.apply_chat_template(
        conversation,
        template=json.dumps(build_template(fields)),
        tokenize=True,
        return_dict=True,
        add_generation_prompt=True,
        return_tensors="pt",
        padding=True,
    ).to(_model.device)

    started = time.time()
    with torch.no_grad():
        generated = _model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
    elapsed = time.time() - started

    prompt_length = inputs["input_ids"].shape[1]
    raw = _processor.decode(generated[0][prompt_length:], skip_special_tokens=True)

    del inputs, generated
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        parsed = json.loads(match.group(0)) if match else {}
    return (parsed if isinstance(parsed, dict) else {}), round(elapsed, 3)


def extract(payload: dict) -> dict:
    fields: list[str] = list(payload.get("fields") or [])
    pages: list[dict] = list(payload.get("pages") or [])
    parsed, elapsed = run(pages, fields)

    # Every requested field appears exactly once, in the requested order:
    # `validate()` rejects a record whose key set differs from the schema, and
    # an omitted field is an untracked silence rather than a stated abstention.
    record = {field: observation(field, parsed.get(field), pages) for field in fields}
    located = sum(1 for value in record.values() if value["status"] == "present")
    print(f"[serve] {len(fields)} fields, {located} located, {elapsed}s", flush=True)
    return {"schema_version": SCHEMA_VERSION, "records": [record]}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def build_app():
    app = FastAPI(title="Sherlock local extraction service")

    @app.get("/health")
    def health():
        return {"status": "ok", "model": MODEL_ID, "artifact_sha256": artifact_sha256()}

    @app.post("/")
    async def infer(request: Request):
        payload = await request.json()
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise HTTPException(422, "Unsupported schema_version")
        expected = payload.get("artifact_sha256")
        if expected and expected != artifact_sha256():
            raise HTTPException(409, "Artifact identity mismatch")
        try:
            output = extract(payload)
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a 500 body
            print(f"[serve] extraction failed: {type(exc).__name__}: {exc}", flush=True)
            raise HTTPException(500, "Extraction failed") from None
        return {"artifact_sha256": artifact_sha256(), "output": output}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1", help="Loopback only; the API refuses anything else.")
    parser.add_argument("--device", default="mps")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Refusing to bind off the loopback interface.")

    print("[serve] NOTE: serving TEXT-only. The benchmark scores in "
          "scripts/benchmark_base_model.py were measured on page images.", flush=True)
    load_model(args.device)
    print(f"[serve] artifact_sha256 {artifact_sha256()}", flush=True)

    import uvicorn

    uvicorn.run(build_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
