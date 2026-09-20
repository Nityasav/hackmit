"""Optional local Transformers/PEFT runner. Never downloads or trains weights.

Set EXTRACTOR_MODEL_DIR (and optional EXTRACTOR_ADAPTER_DIR), fingerprint the
bundle with `python -m app.extractor_server`, then set EXTRACTOR_ARTIFACT_SHA256.
Run on loopback: uvicorn app.extractor_server:app --host 127.0.0.1 --port 8901.

## Citations are computed here, not asked for

This used to put the extraction schema in a prose prompt and ask the model for
"exact zero-based Unicode source spans". Measured against NuExtract3 on a real
two-page document, that produced zero usable fields in 117 seconds: the reply
was well-formed JSON in the wrong shape, and character offsets are not
something a language model can count reliably anyway. `validate()` compares
`page_text[start:end]` to the value, so a miscounted offset is not a slightly
wrong citation — it fails the whole response.

So the model is now asked only for values, through the template interface it
was actually trained for, and the span is found here by searching the page
text. Same document, same weights: seven fields with exact spans in 21
seconds. A value that cannot be found verbatim is reported as an abstention
rather than returned, because a value with no locatable source is the
fabricated evidence this pipeline exists to prevent.
"""
import hashlib
import json
import os
import re
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from .extraction import Strict, SCHEMA_VERSION, validate, digest, schema, Role

_generation = Lock()

#: Words in a field name that identify nothing on a page. "service_start" is
#: disambiguated by "service"; "start" sits near every date on the document.
_GENERIC_FIELD_WORDS = {
    "id", "ref", "reference", "number", "no", "code", "date", "start", "end",
    "amount", "total", "value", "name", "to", "from", "record", "line",
}


def _field_words(field_name: str) -> list[str]:
    words = [w for w in re.split(r"[_\s]+", field_name.lower()) if w]
    specific = [w for w in words if w not in _GENERIC_FIELD_WORDS and len(w) > 2]
    return specific or words


def _disambiguate(hits: list[tuple[int, int, int]], pages: list[dict], field_name: str):
    """Choose among several verbatim occurrences of one value.

    Abstaining on any repeated value threw away correct extractions: a payroll
    record prints the same date under both "Pay Period" and "Service Period",
    and an employee id recurs inside a longer reference on a later page. Prefer
    the occurrence whose preceding text mentions the field, and fall back to
    the first. The value is verbatim either way, so at worst the citation
    points at an equally valid twin, which a reviewer can move.
    """
    text_by_page = {p["page"]: p["text"] for p in pages}
    words = _field_words(field_name) if field_name else []
    best, best_score = None, -1
    for page, start, end in hits:
        preceding = text_by_page.get(page, "")[max(0, start - 90):start].lower()
        score = sum(1 for word in words if word in preceding)
        if score > best_score:
            best, best_score = (page, start, end), score
    return best


def locate(value: str, pages: list[dict], field_name: str = "") -> tuple[int, int, int] | None:
    """Find `value` in the pages, returning (page, start, end).

    Offsets are Python string indices, which are code points — the units
    `validate()` slices with and the browser editor computes with
    `Array.from(...).length`. Byte offsets would pass here and fail on the
    first non-ASCII page.
    """
    if not value or not value.strip():
        return None

    hits: list[tuple[int, int, int]] = []
    for page in pages:
        text, number = page["text"], page["page"]
        start = text.find(value)
        while start >= 0:
            hits.append((number, start, start + len(value)))
            start = text.find(value, start + max(1, len(value)))
            if len(hits) > 64:
                break
    if len(hits) == 1:
        return hits[0]
    if hits:
        return _disambiguate(hits, pages, field_name)

    # A whitespace- and case-insensitive pass, mapped back onto real indices.
    # A PDF that wraps a value across a line, or prints a soft hyphen inside
    # it, still shows the same value; it just is not the same byte sequence.
    target = " ".join(unicodedata.normalize("NFKC", value).split()).casefold()
    if not target:
        return None
    collapsed_hits: list[tuple[int, int, int]] = []
    for page in pages:
        text, number = page["text"], page["page"]
        collapsed, index_map = [], []
        previous_space = True
        for index, char in enumerate(unicodedata.normalize("NFKC", text)):
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
        # Read by the model but not locatable on the page. `unreadable` rather
        # than dropped, so a reviewer sees that something was here and could
        # not be pinned down.
        return {"status": "unreadable", "value": None, "page": None, "start": None, "end": None}
    page, start, end = found
    return {"status": "present", "value": text, "page": page, "start": start, "end": end}


def build_template(fields: list[str]) -> dict:
    """Every requested field as a verbatim string.

    Only `verbatim-string`, deliberately: a typed slot invites the model to
    reformat ("$1,200.00" -> 1200.0), and a reformatted value cannot be found
    on the page, so it would arrive as an abstention. Canonical forms are the
    job of the normalizers and the accounting engine, downstream of a citation
    that still resolves.
    """
    return {field: "verbatim-string" for field in fields}


def bundle_fingerprint():
    """Hash actual model/tokenizer/adapter bytes, not a claimed version string."""
    manifest = []
    for label, env in (("base", "EXTRACTOR_MODEL_DIR"), ("adapter", "EXTRACTOR_ADAPTER_DIR")):
        raw = os.getenv(env)
        if not raw and label == "adapter":
            continue
        if not raw or not Path(raw).is_absolute() or not Path(raw).is_dir():
            raise ValueError(f"{env} must name an existing absolute directory")
        root = Path(raw)
        if root.is_symlink():
            raise ValueError("Use a materialized model bundle, not a symlink")
        files = sorted(root.rglob("*"))
        if any(p.is_symlink() for p in files):
            raise ValueError("Model bundle must not contain symlinks")
        if not any(p.suffix == ".safetensors" for p in files):
            raise ValueError("Only safetensors model/adapter bundles are supported")
        for path in files:
            if not path.is_file():
                continue
            if path.suffix in {".bin", ".pt", ".pth", ".pkl", ".py"}:
                raise ValueError("Executable/pickle weight formats are not permitted")
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(chunk)
            manifest.append({"bundle": label, "file": path.relative_to(root).as_posix(), "sha256": hasher.hexdigest()})
    return digest(manifest)


@asynccontextmanager
async def lifespan(app):
    fingerprint = bundle_fingerprint()
    if fingerprint != os.getenv("EXTRACTOR_ARTIFACT_SHA256"):
        raise RuntimeError("Model bundle fingerprint does not match EXTRACTOR_ARTIFACT_SHA256")
    # Optional dependencies are only imported when this separate runner starts.
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText
    root = os.environ["EXTRACTOR_MODEL_DIR"]
    processor = AutoProcessor.from_pretrained(root, local_files_only=True, trust_remote_code=False)
    model = AutoModelForImageTextToText.from_pretrained(root, local_files_only=True, trust_remote_code=False,
                                                       use_safetensors=True, dtype="auto", device_map="auto")
    if adapter := os.getenv("EXTRACTOR_ADAPTER_DIR"):
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter, local_files_only=True, is_trainable=False)
    app.state.processor = processor
    app.state.model = model.eval()
    app.state.torch = torch
    app.state.artifact = fingerprint
    yield


app = FastAPI(title="Sherlock local extractor", lifespan=lifespan)


@app.middleware("http")
async def local_only(request: Request, call_next):
    peer = request.client.host if request.client else ""
    testing = request.url.hostname == "testserver" and peer == "testclient"
    if (not testing and (request.url.hostname not in {"127.0.0.1", "localhost", "::1"} or peer not in {"127.0.0.1", "::1"})) or request.headers.get("origin"):
        return JSONResponse({"detail": "Backend-only loopback inference service"}, status_code=403)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 1_000_000:
            return JSONResponse({"detail": "Inference request too large"}, status_code=413)
    request._body = bytes(content)
    return await call_next(request)


class Page(Strict):
    page: int = Field(ge=1, le=20)
    text: str = Field(max_length=200000)
    method: str
    warnings: list[str]


class Input(Strict):
    schema_version: str
    artifact_sha256: str
    document_type: Role
    fields: list[str]
    pages: list[Page] = Field(min_length=1, max_length=20)
    output_schema: dict
    instruction: str = Field(max_length=2000)


@app.post("/extract")
def extract(body: Input, request: Request):
    if body.schema_version != SCHEMA_VERSION or body.fields != schema(body.document_type):
        raise HTTPException(422, "Unsupported schema or document fields")
    if body.artifact_sha256 != request.app.state.artifact:
        raise HTTPException(409, "Requested model artifact is not loaded")
    if sum(len(p.text) for p in body.pages) > 200000 or len({p.page for p in body.pages}) != len(body.pages):
        raise HTTPException(422, "Page limits exceeded or duplicated")
    if not _generation.acquire(blocking=False):
        raise HTTPException(429, "Local model is already generating")
    try:
        pages = [p.model_dump() for p in body.pages]
        # The server owns the request shape; caller and source content cannot
        # grant tools or change what is asked for. The page text is passed as
        # data under an explicit page marker, and the fields are requested
        # through the model's template interface rather than described in
        # prose — the same interface the published benchmark scores used.
        numbered = "\n\n".join(f"[page {p['page']}]\n{p['text']}" for p in pages)
        processor, model = request.app.state.processor, request.app.state.model
        messages = [{"role": "user", "content": [{"type": "text", "text": numbered}]}]
        inputs = processor.apply_chat_template(
            messages, template=json.dumps(build_template(body.fields)),
            add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt")
        if inputs["input_ids"].shape[1] > 24000:
            raise HTTPException(422, "Document exceeds local model token budget; split or reduce pages")
        inputs = inputs.to(model.device)
        with request.app.state.torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=2048, do_sample=False, max_time=180)
        text = processor.batch_decode(generated[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True,
                                      clean_up_tokenization_spaces=False)[0].strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else {}
        if not isinstance(parsed, dict):
            parsed = {}
        # Every requested field appears exactly once: `validate()` rejects a
        # record whose key set differs from the schema, and an omitted field
        # is an untracked silence rather than a stated abstention.
        record = {field: observation(field, parsed.get(field), pages) for field in body.fields}
        output = validate({"schema_version": SCHEMA_VERSION, "records": [record]},
                          {"role": body.document_type, "pages": pages})
        return {"artifact_sha256": request.app.state.artifact, "output": output}
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, "Model output did not satisfy the extraction contract") from None
    finally:
        _generation.release()


if __name__ == "__main__":
    print(bundle_fingerprint())
