from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class McpRpcError(RuntimeError):
    pass


@dataclass(frozen=True)
class McpTool:
    name: str
    description: str
    input_schema: dict[str, Any]


class McpClient:
    def __init__(self, server_name: str, command: list[str], cwd: Path) -> None:
        self.server_name = server_name
        self.command = command
        self.cwd = cwd
        self._lock = threading.Lock()
        self._next_id = 1

        self._proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.request("initialize", {"client": "multi-agent-research-assistant"})

    def close(self) -> None:
        with self._lock:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
            except Exception:
                pass
            try:
                self._proc.terminate()
            except Exception:
                pass

    def list_tools(self) -> list[McpTool]:
        res = self.request("tools/list")
        tools: list[McpTool] = []
        for item in res or []:
            tools.append(
                McpTool(
                    name=str(item.get("name") or ""),
                    description=str(item.get("description") or ""),
                    input_schema=dict(item.get("inputSchema") or {}),
                )
            )
        return [t for t in tools if t.name]

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        return self.request("tools/call", {"name": tool_name, "arguments": arguments})

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            message: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
            if params is not None:
                message["params"] = params
            self._write(message)
            return self._read_response(req_id)

    def _write(self, message: dict[str, Any]) -> None:
        if not self._proc.stdin:
            raise McpRpcError("MCP stdin is closed")
        self._proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

    def _read_response(self, req_id: int) -> Any:
        if not self._proc.stdout:
            raise McpRpcError("MCP stdout is closed")
        while True:
            line = self._proc.stdout.readline()
            if line == "":
                raise McpRpcError("MCP server closed stdout")
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if msg.get("id") != req_id:
                continue
            if "error" in msg and msg["error"] is not None:
                raise McpRpcError(str(msg["error"]))
            return msg.get("result")

