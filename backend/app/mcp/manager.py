from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT, get_settings
from app.mcp.client import McpClient, McpRpcError, McpTool


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    command: list[str]


class McpManager:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self._clients: dict[str, McpClient] = {}
        self.reload()

    @staticmethod
    def default() -> "McpManager":
        settings = get_settings()
        return McpManager(config_path=settings.mcp_config_path)

    def reload(self) -> None:
        configs = self._load_config()
        keep = {c.name for c in configs}

        for name in list(self._clients.keys()):
            if name not in keep:
                self._clients[name].close()
                self._clients.pop(name, None)

        for cfg in configs:
            if cfg.name in self._clients:
                continue
            try:
                self._clients[cfg.name] = McpClient(server_name=cfg.name, command=cfg.command, cwd=REPO_ROOT)
            except Exception:
                continue

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for server_name, client in self._clients.items():
            try:
                for t in client.list_tools():
                    tools.append(
                        {
                            "name": f"{server_name}.{t.name}",
                            "description": t.description,
                            "input_schema": t.input_schema,
                            "origin": "mcp",
                            "server": server_name,
                        }
                    )
            except McpRpcError:
                continue
        return tools

    def call(self, full_tool_name: str, arguments: dict[str, Any]) -> Any:
        if "." not in full_tool_name:
            raise McpRpcError("Invalid MCP tool name")
        server, tool = full_tool_name.split(".", 1)
        client = self._clients.get(server)
        if client is None:
            raise McpRpcError(f"MCP server not loaded: {server}")
        return client.call_tool(tool_name=tool, arguments=arguments)

    def _load_config(self) -> list[McpServerConfig]:
        path = self.config_path
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.exists():
            return []

        raw = json.loads(path.read_text(encoding="utf-8"))
        servers = raw.get("servers") if isinstance(raw, dict) else None
        if not isinstance(servers, list):
            return []

        configs: list[McpServerConfig] = []
        for item in servers:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            command = item.get("command")
            if not name or not isinstance(command, list) or not command:
                continue
            cmd: list[str] = []
            for part in command:
                p = str(part)
                if p.endswith(".py") and not Path(p).is_absolute():
                    cmd.append(str(REPO_ROOT / p))
                else:
                    cmd.append(p)
            configs.append(McpServerConfig(name=name, command=cmd))
        return configs

