from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.storage import JobStore
from app.research.ingest import ingest_uploaded_file
from app.research.models import JobResponse

router = APIRouter()


@router.post("/jobs/{job_id}/uploads", response_model=JobResponse)
async def upload_file(job_id: str, file: UploadFile = File(...)) -> JobResponse:
    store = JobStore.default()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    await ingest_uploaded_file(job_id=job_id, upload=file, store=store)
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.from_job(job)

