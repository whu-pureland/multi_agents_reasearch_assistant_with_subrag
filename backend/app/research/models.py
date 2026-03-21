from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal["created", "running", "succeeded", "failed"]
TodoStatus = Literal["pending", "in_progress", "done"]


class JobSettings(BaseModel):
    max_todos: int = 8
    web_results_per_todo: int = 5
    include_private_knowledge: bool = True
    private_semantic_top_k: int = 5
    enable_fact_check: bool = True
    enable_mcp_tools: bool = False


class JobCreateRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    settings: JobSettings = Field(default_factory=JobSettings)


class Source(BaseModel):
    id: str
    title: str
    url: str
    snippet: str | None = None
    provider: str = "web"
    quality_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Note(BaseModel):
    todo_id: str
    title: str
    content_md: str
    source_ids: list[str] = Field(default_factory=list)


class TodoItem(BaseModel):
    id: str
    title: str
    status: TodoStatus = "pending"
    note_id: str | None = None


class UploadItem(BaseModel):
    filename: str
    stored_path: str
    ingested: bool = False


class Job(BaseModel):
    id: str
    query: str
    status: JobStatus
    created_at: str
    updated_at: str
    settings: JobSettings
    todos: list[TodoItem]
    notes: list[Note]
    sources: list[Source]
    report: str | None
    error: str | None
    uploads: list[UploadItem]
    events: list[dict[str, Any]]


class JobResponse(BaseModel):
    id: str
    query: str
    status: JobStatus
    created_at: str
    updated_at: str
    settings: JobSettings
    todos: list[TodoItem]
    notes: list[Note]
    sources: list[Source]
    report: str | None
    error: str | None
    uploads: list[UploadItem]
    events: list[dict[str, Any]]

    @staticmethod
    def from_job(job: Job) -> "JobResponse":
        return JobResponse(**job.model_dump())
