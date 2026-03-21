from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.storage import JobStore

router = APIRouter()


@router.get("/jobs/{job_id}/events/stream")
async def stream_events(job_id: str, cursor: int = 0) -> StreamingResponse:
    store = JobStore.default()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def generator():
        last = max(0, int(cursor))
        while True:
            try:
                job_now = store.get_job(job_id)
                if job_now is None:
                    return
                events = job_now.events
                while last < len(events):
                    data = json.dumps(events[last], ensure_ascii=False)
                    yield f"id: {last}\n"
                    yield f"data: {data}\n\n"
                    last += 1
                yield ":keepalive\n\n"
                await asyncio.sleep(0.6)
            except asyncio.CancelledError:
                return

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(generator(), media_type="text/event-stream", headers=headers)

