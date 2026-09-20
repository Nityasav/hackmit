"""Bounded, subprocess-isolated document decoding. No document code is executed."""
import io
import multiprocessing
import threading

MAX_PAGES = 20
MAX_PIXELS = 12_000_000
MAX_TEXT = 200_000
_slots = threading.BoundedSemaphore(2)


def _image(data):
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    image = Image.open(io.BytesIO(data))
    if image.width * image.height > MAX_PIXELS or getattr(image, "n_frames", 1) != 1:
        raise ValueError("Image must be single-frame and at most 12 megapixels")
    return ImageOps.exif_transpose(image).convert("RGB")


def _pdf(data):
    import pypdfium2 as pdfium
    return pdfium.PdfDocument(data)


def _render(pdf, index):
    page = pdf[index]
    try:
        w, h = page.get_size()
        if w <= 0 or h <= 0 or w * h * 4 > MAX_PIXELS:
            raise ValueError("PDF page exceeds render pixel limit")
        bitmap = page.render(scale=2)
        try:
            return bitmap.to_pil().convert("RGB")
        finally:
            bitmap.close()
    finally:
        page.close()


def _process(data, suffix, page_number=None):
    pages = []
    if suffix in {".txt", ".md"}:
        if page_number:
            raise ValueError("Text documents have no page image")
        text = data.decode("utf-8-sig")
        if any(ord(c) < 32 and c not in "\t\n\r" for c in text):
            raise ValueError("Text contains binary control characters")
        pages = [{"page": 1, "text": text, "method": "native", "warnings": []}]
    else:
        pdf = _pdf(data) if suffix == ".pdf" else None
        try:
            count = len(pdf) if pdf else 1
            if not 1 <= count <= MAX_PAGES:
                raise ValueError("Document must contain 1–20 pages")
            if page_number:
                if not 1 <= page_number <= count:
                    raise ValueError("Page does not exist")
                im = _render(pdf, page_number - 1) if pdf else _image(data)
                out = io.BytesIO(); im.save(out, format="PNG")
                return out.getvalue()
            ocr = None
            for index in range(count):
                text = ""
                if pdf:
                    page = pdf[index]
                    try:
                        textpage = page.get_textpage()
                        try:
                            text = textpage.get_text_range()
                        finally:
                            textpage.close()
                    finally:
                        page.close()
                method, warnings = "native", []
                if len(text.strip()) < 20:
                    from rapidocr_onnxruntime import RapidOCR
                    import numpy as np
                    if ocr is None:
                        ocr = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)
                    im = _render(pdf, index) if pdf else _image(data)
                    result, _ = ocr(np.asarray(im)[:, :, ::-1])
                    text = "\n".join(row[1] for row in result or [])
                    method = "ocr"
                    warnings = ["OCR transcription requires comparison with the original page."]
                if not text.strip():
                    warnings.append("No readable text; manual transcription required.")
                pages.append({"page": index + 1, "text": text, "method": method, "warnings": warnings})
                if sum(len(p["text"]) for p in pages) > MAX_TEXT:
                    raise ValueError("Document exceeds 200,000 extracted characters")
        finally:
            if pdf:
                pdf.close()
    if not pages or sum(len(p["text"]) for p in pages) > MAX_TEXT:
        raise ValueError("Document exceeds text limit")
    return pages


def _worker(pipe, data, suffix, page_number):
    try:
        pipe.send((True, _process(data, suffix, page_number)))
    except Exception:
        pipe.send((False, "Unable to decode document within supported limits; check format, encryption and page size."))
    finally:
        pipe.close()


def process(data, suffix, page_number=None):
    if not _slots.acquire(blocking=False):
        raise ValueError("Document processing busy; retry shortly")
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    worker = ctx.Process(target=_worker, args=(child, data, suffix, page_number), daemon=True)
    try:
        worker.start(); child.close()
        if not parent.poll(90):
            raise ValueError("Document processing timed out; split the document into smaller files")
        ok, value = parent.recv()
        if not ok:
            raise ValueError(value)
        return value
    except EOFError:
        raise ValueError("Document decoder stopped unexpectedly") from None
    finally:
        if worker.pid:
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=5)
        parent.close(); child.close(); _slots.release()
