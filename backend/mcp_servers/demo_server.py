from __future__ import annotations

import json
import sys
from typing import Any


def _send(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _ok(req_id: Any, result: Any) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _err(req_id: Any, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"message": message}})


TOOLS = [
    {
        "name": "echo",
        "description": "Echo text back to the caller (demo tool).",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "sql_query",
        "description": "Run a read-only demo SQL query against a stub dataset (simulates enterprise DB).",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


def _handle_tools_call(params: dict[str, Any]) -> Any:
    name = str(params.get("name") or "")
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        args = {}

    if name == "echo":
        return {"text": str(args.get("text") or "")}

    if name == "sql_query":
        q = str(args.get("query") or "")
        rows = [
            {"table": "papers", "count": 42, "note": "stub"},
            {"table": "reports", "count": 7, "note": "stub"},
            {"table": "sources", "count": 128, "note": "stub"},
        ]
        return {"query": q, "rows": rows}

    raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") if isinstance(req.get("params"), dict) else {}

        try:
            if method == "initialize":
                _ok(req_id, {"server": "demo", "capabilities": {"tools": True}})
            elif method == "tools/list":
                _ok(req_id, TOOLS)
            elif method == "tools/call":
                _ok(req_id, _handle_tools_call(params))
            else:
                _err(req_id, f"Unknown method: {method}")
        except Exception as e:
            _err(req_id, str(e))


if __name__ == "__main__":
    main()

