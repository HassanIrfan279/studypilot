"""Tutor tool: download a lecture file from Drive in a form Gemini can read.

PDF -> raw bytes. Google Slides/Docs -> exported to PDF. PPTX/DOCX -> text extracted locally.
Images -> raw bytes (Gemini can read photos/handwriting).
"""
import io
import re
import zipfile
from pathlib import Path

import google_clients as g
from config import DATA_DIR

CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
GOOGLE_EXPORTABLE = ("application/vnd.google-apps.presentation",
                     "application/vnd.google-apps.document")


class UnsupportedFile(Exception):
    pass


def file_info(file_id):
    svc = g.drive()
    return g.with_retry(lambda: svc.files().get(
        fileId=file_id, fields="id,name,mimeType,modifiedTime,webViewLink",
        supportsAllDrives=True).execute())


def _download(file_id, mime):
    svc = g.drive()
    if mime in GOOGLE_EXPORTABLE:
        return g.with_retry(lambda: svc.files().export(fileId=file_id,
                                                       mimeType="application/pdf").execute())
    return g.with_retry(lambda: svc.files().get_media(fileId=file_id,
                                                      supportsAllDrives=True).execute())


def _pptx_text(data: bytes) -> str:
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    parts = []
    for i, slide in enumerate(prs.slides, 1):
        lines = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for p in shape.text_frame.paragraphs:
                    t = "".join(r.text for r in p.runs).strip()
                    if t:
                        lines.append(t)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    lines.append(" | ".join(c.text for c in row.cells))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                lines.append(f"(Speaker notes: {notes})")
        parts.append(f"--- Slide {i} ---\n" + "\n".join(lines))
    return "\n\n".join(parts)


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def fetch_lecture(file_id):
    """Returns {"name", "mime", "kind": "pdf"|"image"|"text", "data": bytes|None, "text": str|None}."""
    info = file_info(file_id)
    mime, name = info["mimeType"], info["name"]
    cache_file = CACHE_DIR / f"{file_id}.bin"
    if cache_file.exists():
        data = cache_file.read_bytes()
    else:
        data = _download(file_id, mime)
        cache_file.write_bytes(data)

    if mime == "application/pdf" or mime in GOOGLE_EXPORTABLE:
        return {"name": name, "mime": "application/pdf", "kind": "pdf", "data": data, "text": None}
    if mime == PPTX:
        return {"name": name, "mime": mime, "kind": "text", "data": None, "text": _pptx_text(data)}
    if mime == DOCX:
        return {"name": name, "mime": mime, "kind": "text", "data": None, "text": _docx_text(data)}
    if mime.startswith("image/"):
        return {"name": name, "mime": mime, "kind": "image", "data": data, "text": None}
    if mime.startswith("text/"):
        return {"name": name, "mime": mime, "kind": "text", "data": None,
                "text": data.decode("utf8", "ignore")}
    raise UnsupportedFile(f"Can't read '{name}' ({mime}) yet.")


def is_supported(mime: str) -> bool:
    return (mime in ("application/pdf", PPTX, DOCX) or mime in GOOGLE_EXPORTABLE
            or mime.startswith("image/") or mime.startswith("text/"))
