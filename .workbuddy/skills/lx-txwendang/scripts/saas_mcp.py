#!/usr/bin/env python3
"""Tencent Docs SaaS MCP client for enterprise document operations.

This module intentionally does not print credentials. It reads the
Authorization token from WorkBuddy MCP config by default and calls the
`tencent-docs` MCP server over HTTP.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_MCP_CONFIG = Path.home() / ".workbuddy" / "mcp.json"
DEFAULT_SERVER_NAME = "tencent-docs"
DEFAULT_MCP_URL = "https://saas.docs.qq.com/openapi/mcp"
RATE_LIMIT_CODE = 400007


class SaasDocsError(RuntimeError):
    """Base error for SaaS Tencent Docs operations."""


class SaasDocsRateLimitError(SaasDocsError):
    """Raised when Tencent Docs SaaS MCP reports access limit."""


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SaasDocsError(f"MCP 配置顶层不是对象: {path}")
    return data


def _parse_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured

    content = result.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and first.get("type") == "text":
            text = first.get("text") or ""
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}

    return result


def _parse_mcp_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        events = []
        current: list[str] = []
        for line in text.splitlines():
            if not line.strip():
                if current:
                    events.append("\n".join(current))
                    current = []
                continue
            if line.startswith("data:"):
                value = line[5:].strip()
                if value and value != "[DONE]":
                    current.append(value)
        if current:
            events.append("\n".join(current))

        for event in reversed(events):
            try:
                parsed = json.loads(event)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise SaasDocsError(f"MCP 返回非 JSON: {raw[:500]}") from exc

    if not isinstance(data, dict):
        raise SaasDocsError("MCP 返回顶层不是对象")
    return data


class SaasDocsClient:
    """Small JSON-RPC HTTP client for the Tencent Docs SaaS MCP server."""

    def __init__(
        self,
        mcp_config_path: str | Path | None = None,
        server_name: str = DEFAULT_SERVER_NAME,
        timeout: int = 60,
        min_interval: float = 0.0,
        retries: int = 0,
        rate_limit_sleep: int = 300,
    ) -> None:
        self.server_name = server_name
        self.timeout = timeout
        self.min_interval = max(min_interval, 0.0)
        self.retries = max(retries, 0)
        self.rate_limit_sleep = max(rate_limit_sleep, 0)
        self._request_id = 0
        self._last_call_at = 0.0

        self.url, self.authorization = self._load_endpoint(mcp_config_path)
        if not self.authorization:
            raise SaasDocsError(
                "未找到腾讯文档 SaaS MCP Authorization。请检查 "
                "~/.workbuddy/mcp.json 或 TENCENT_DOCS_TOKEN。"
            )

    def _load_endpoint(self, mcp_config_path: str | Path | None) -> tuple[str, str]:
        env_token = os.environ.get("TENCENT_DOCS_TOKEN", "").strip()
        env_url = os.environ.get("TENCENT_DOCS_MCP_URL", "").strip()
        if env_token:
            return env_url or DEFAULT_MCP_URL, env_token

        path = Path(mcp_config_path).expanduser() if mcp_config_path else DEFAULT_MCP_CONFIG
        if not path.exists():
            raise SaasDocsError(f"MCP 配置文件不存在: {path}")

        data = _load_json(path)
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            raise SaasDocsError(f"MCP 配置缺少 mcpServers: {path}")
        server = servers.get(self.server_name)
        if not isinstance(server, dict):
            raise SaasDocsError(f"MCP 配置中未找到 server: {self.server_name}")

        headers = server.get("headers")
        if not isinstance(headers, dict):
            headers = {}
        auth = str(headers.get("Authorization", "")).strip()
        url = str(server.get("url", "")).strip() or DEFAULT_MCP_URL
        return url, auth

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.authorization,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise SaasDocsError(f"MCP HTTP {exc.code}: {raw[:500]}") from exc
        except urllib.error.URLError as exc:
            raise SaasDocsError(f"MCP 请求失败: {exc}") from exc

        return _parse_mcp_response(raw)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_call_at
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        retries: int | None = None,
    ) -> dict[str, Any]:
        """Call one MCP tool and return structured content."""
        attempts = self.retries if retries is None else max(retries, 0)
        for attempt in range(attempts + 1):
            self._throttle()
            payload = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {
                    "name": name,
                    "arguments": arguments,
                },
            }
            data = self._post_json(payload)
            self._last_call_at = time.monotonic()

            error = data.get("error")
            if isinstance(error, dict):
                code = error.get("code")
                message = error.get("message", "")
                if code == RATE_LIMIT_CODE:
                    if attempt < attempts and self.rate_limit_sleep > 0:
                        time.sleep(self.rate_limit_sleep)
                        continue
                    raise SaasDocsRateLimitError(
                        f"{RATE_LIMIT_CODE}: {message or 'You have reached access limit'}"
                    )
                raise SaasDocsError(f"{name} 失败: {error}")

            result = data.get("result")
            if not isinstance(result, dict):
                raise SaasDocsError(f"{name} 返回缺少 result")
            return _parse_tool_result(result)

        raise SaasDocsRateLimitError(f"{RATE_LIMIT_CODE}: You have reached access limit")

    def query_file_info(self, file_id: str) -> dict[str, Any]:
        return self.call_tool("query_file_info", {"file_id": file_id})

    def search_file(self, search_key: str) -> list[dict[str, Any]]:
        result = self.call_tool("search_file", {"search_key": search_key})
        items = result.get("list", [])
        return items if isinstance(items, list) else []

    def create_file(self, title: str, file_type: str, parent_id: str = "") -> dict[str, Any]:
        args: dict[str, Any] = {
            "title": title,
            "file_type": file_type,
        }
        if parent_id:
            args["parent_id"] = parent_id
        return self.call_tool("create_file", args)

    def sheet_get_info(self, file_id: str, concise: bool = False) -> dict[str, Any]:
        return self.call_tool("sheet.get_info", {"file_id": file_id, "concise": concise})

    def sheet_batch_update(
        self,
        file_id: str,
        requests: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self.call_tool("sheet.batch_update", {"file_id": file_id, "requests": requests})
