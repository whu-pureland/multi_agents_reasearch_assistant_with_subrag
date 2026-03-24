from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.storage import JobStore
from app.research.interactions import handle_user_interaction
from app.research.models import JobResponse
from app.research.runner import run_job

router = APIRouter()


class InteractionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/jobs/{job_id}/interact", response_model=JobResponse)
def interact(job_id: str, request: InteractionRequest) -> JobResponse:
    store = JobStore.default()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty interaction")

    result = handle_user_interaction(store=store, job_id=job_id, text=text)

    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if result.added_todos and job.status in {"succeeded", "failed"}:
        store.update_job(job_id, {"status": "running", "error": None})
        store.append_event(job_id, {"type": "job_restarted", "reason": "interaction_added_todo"})
        threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.from_job(job)
