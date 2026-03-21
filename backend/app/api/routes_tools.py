from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.tools.registry import ToolRegistry

router = APIRouter()


class ToolCallRequest(BaseModel):
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/tools")
def list_tools() -> dict[str, Any]:
    registry = ToolRegistry.default()
    return {"tools": registry.list_tools()}


@router.post("/tools/reload")
def reload_tools() -> dict[str, Any]:
    registry = ToolRegistry.default()
    registry.reload()
    return {"tools": registry.list_tools()}


@router.post("/tools/call")
def call_tool(request: ToolCallRequest) -> dict[str, Any]:
    registry = ToolRegistry.default()
    result = registry.call(request.name, request.arguments)
    return {"result": result}

