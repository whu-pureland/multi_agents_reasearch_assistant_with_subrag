from __future__ import annotations

import re
from pathlib import Path

from fastapi import UploadFile
from pypdf import PdfReader

from app.core.config import get_settings
from app.core.storage import JobStore
from app.research.local_knowledge import LocalKnowledgeBase
from app.research.vector_knowledge import VectorKnowledgeBase


def _safe_filename(name: str) -> str:
    name = name.strip().replace("\\", "_").replace("/", "_")
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
    return name[:120] or "upload"


def _extract_text_from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def _extract_text_from_image(path: Path) -> str:
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
    except Exception:
        return ""
    try:
        image = Image.open(path)
        return (pytesseract.image_to_string(image) or "").strip()
    except Exception:
        return ""


async def ingest_uploaded_file(job_id: str, upload: UploadFile, store: JobStore) -> None:
    settings = get_settings()
    upload_dir = settings.data_dir / "uploads" / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(upload.filename or "upload")
    stored_path = upload_dir / safe_name

    content = await upload.read()
    stored_path.write_bytes(content)

    job = store.get_job(job_id)
    if job is None:
        return
    uploads = [
        *[u.model_dump() for u in job.uploads],
        {"filename": safe_name, "stored_path": str(stored_path), "ingested": False},
    ]
    store.update_job(job_id, {"uploads": uploads})
    store.append_event(job_id, {"type": "upload_saved", "filename": safe_name})

    text = ""
    if safe_name.lower().endswith(".pdf"):
        text = _extract_text_from_pdf(stored_path)
    elif safe_name.lower().endswith((".png", ".jpg", ".jpeg")):
        text = _extract_text_from_image(stored_path)
    else:
        try:
            text = stored_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = stored_path.read_text(encoding="latin-1")

    if text.strip():
        kb = LocalKnowledgeBase.for_job(job_id)
        kb.ingest_document(filename=safe_name, text=text)
        VectorKnowledgeBase.for_job(job_id).ingest_document(filename=safe_name, text=text)
        store.append_event(job_id, {"type": "upload_ingested", "filename": safe_name})

        job = store.get_job(job_id)
        if job is not None:
            updated_uploads = []
            for item in job.uploads:
                if item.filename == safe_name and item.stored_path == str(stored_path):
                    updated_uploads.append({**item.model_dump(), "ingested": True})
                else:
                    updated_uploads.append(item.model_dump())
            store.update_job(job_id, {"uploads": updated_uploads})
