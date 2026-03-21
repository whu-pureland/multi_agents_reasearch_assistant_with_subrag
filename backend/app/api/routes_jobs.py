from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException

from app.core.storage import JobStore
from app.research.models import JobCreateRequest, JobResponse
from app.research.runner import run_job

router = APIRouter()


@router.post("/jobs", response_model=JobResponse)
def create_job(request: JobCreateRequest) -> JobResponse:
    store = JobStore.default()
    job = store.create_job(request)
    return JobResponse.from_job(job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    store = JobStore.default()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.from_job(job)


@router.post("/jobs/{job_id}/start", response_model=JobResponse)
def start_job(job_id: str) -> JobResponse:
    store = JobStore.default()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "running":
        return JobResponse.from_job(job)

    store.update_job(job_id, {"status": "running"})
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.from_job(job)
