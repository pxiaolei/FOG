#!/usr/bin/env python3
"""Tencent Docs online backends for lx-biaogetongbu.

The orchestrator prefers the Tencent Docs SaaS MCP backend and can fall back to
lx-txsaasdocs before any write starts. Once a write request is sent, fallback is
disabled to avoid duplicate or partial writes.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


DEFAULT_MCP_CONFIG = Path.home() / ".workbuddy" / "mcp.json"
DEFAULT_MCP_SERVER_NAME = "tencent-docs"
DEFAULT_MCP_URL = "https://saas.docs.qq.com/openapi/mcp"
RATE_LIMIT_CODE = 400007


class OnlineBackendError(RuntimeError):
    """Base error for online Tencent Docs backends."""


class OnlineBackendUnavailable(OnlineBackendError):
    """Backend credentials, config, or network are unavailable."""


class OnlineBackendRateLimited(OnlineBackendError):
    """Backend reported access limit."""


class OnlineBackendUnsupported(OnlineBackendError):
    """Backend does not support this operation."""


class OnlineBackendWriteBoundary(OnlineBackendError):
    """Write failed after the write boundary, so fallback is blocked."""


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise OnlineBackendUnavailable(f"MCP 配置顶层不是对象: {path}")
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
        events: list[str] = []
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
        raise OnlineBackendError(f"MCP 返回非 JSON: {raw[:500]}") from exc

    if not isinstance(data, dict):
        raise OnlineBackendError("MCP 返回顶层不是对象")
    return data


class TencentDocsMcpBackend:
    """JSON-RPC HTTP client for the Tencent Docs SaaS MCP server."""

    backend_label = "tencent-docs-saas-mcp"

    def __init__(
        self,
        mcp_config_path: str | Path | None = None,
        server_name: str = DEFAULT_MCP_SERVER_NAME,
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
            raise OnlineBackendUnavailable(
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
            raise OnlineBackendUnavailable(f"MCP 配置文件不存在: {path}")

        data = _load_json(path)
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            raise OnlineBackendUnavailable(f"MCP 配置缺少 mcpServers: {path}")
        server = servers.get(self.server_name)
        if not isinstance(server, dict):
            raise OnlineBackendUnavailable(f"MCP 配置中未找到 server: {self.server_name}")

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
            if exc.code in {429, 503}:
                raise OnlineBackendRateLimited(f"MCP HTTP {exc.code}: {raw[:500]}") from exc
            raise OnlineBackendError(f"MCP HTTP {exc.code}: {raw[:500]}") from exc
        except urllib.error.URLError as exc:
            raise OnlineBackendUnavailable(f"MCP 请求失败: {exc}") from exc

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
                    raise OnlineBackendRateLimited(
                        f"{RATE_LIMIT_CODE}: {message or 'You have reached access limit'}"
                    )
                raise OnlineBackendError(f"{name} 失败: {error}")

            result = data.get("result")
            if not isinstance(result, dict):
                raise OnlineBackendError(f"{name} 返回缺少 result")
            return _parse_tool_result(result)

        raise OnlineBackendRateLimited(f"{RATE_LIMIT_CODE}: You have reached access limit")

    def query_file_info(self, file_id: str) -> dict[str, Any]:
        return self.call_tool("query_file_info", {"file_id": file_id})

    def sheet_get_info(self, file_id: str, concise: bool = False) -> dict[str, Any]:
        return self.call_tool("sheet.get_info", {"file_id": file_id, "concise": concise})

    def sheet_batch_update(
        self,
        file_id: str,
        requests: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self.call_tool("sheet.batch_update", {"file_id": file_id, "requests": requests})


def _skills_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent.parent
        if (candidate / "lx-txsaasdocs" / "scripts" / "saas_openapi.py").exists():
            return candidate
    return Path(__file__).resolve().parents[1]


class TxSaasDocsApiBackend:
    """Adapter around lx-txsaasdocs.

    It currently supports file lookup. Ordinary online spreadsheet range
    operations intentionally report unsupported until lx-txsaasdocs implements
    the verified SaaS OpenAPI endpoints for those operations.
    """

    backend_label = "lx-txsaasdocs-api"

    def __init__(self, config_path: str | Path | None = None, timeout: int = 60) -> None:
        scripts_dir = _skills_root() / "lx-txsaasdocs" / "scripts"
        if not scripts_dir.exists():
            raise OnlineBackendUnavailable(f"缺少 lx-txsaasdocs API 脚本目录: {scripts_dir}")
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        try:
            from saas_openapi import TxSaasDocsClient, TxSaasDocsError  # noqa: WPS433
        except ImportError as exc:
            raise OnlineBackendUnavailable(f"无法导入 lx-txsaasdocs: {exc}") from exc

        self._error_type = TxSaasDocsError
        try:
            self.client = TxSaasDocsClient(config_path=config_path, timeout=timeout)
        except TxSaasDocsError as exc:
            raise OnlineBackendUnavailable(f"lx-txsaasdocs 配置不可用: {exc}") from exc

    def _call_client_method(self, name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        method = getattr(self.client, name, None)
        if not callable(method):
            raise OnlineBackendUnsupported(f"lx-txsaasdocs 尚未实现普通在线表格接口: {name}")
        try:
            result = method(*args, **kwargs)
        except self._error_type as exc:
            raise OnlineBackendError(f"lx-txsaasdocs 调用失败: {exc}") from exc
        if not isinstance(result, dict):
            raise OnlineBackendError(f"lx-txsaasdocs {name} 返回顶层不是对象")
        return result

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "query_file_info":
            return self.query_file_info(str(arguments.get("file_id", "")))
        if name == "sheet.get_info":
            return self.sheet_get_info(str(arguments.get("file_id", "")), bool(arguments.get("concise", False)))
        if name == "sheet.get_range":
            return self.sheet_get_range(
                str(arguments.get("file_id", "")),
                str(arguments.get("sheet_id", "")),
                str(arguments.get("range", "")),
            )
        if name == "sheet.batch_update":
            requests = arguments.get("requests")
            return self.sheet_batch_update(
                str(arguments.get("file_id", "")),
                requests if isinstance(requests, list) else [],
            )
        raise OnlineBackendUnsupported(f"lx-txsaasdocs 不支持 MCP 工具名: {name}")

    def query_file_info(self, file_id: str) -> dict[str, Any]:
        return self._call_client_method("get_file", file_id)

    def sheet_get_info(self, file_id: str, concise: bool = False) -> dict[str, Any]:
        return self._call_client_method("sheet_get_info", file_id, concise=concise)

    def sheet_get_range(self, file_id: str, sheet_id: str, range_text: str) -> dict[str, Any]:
        return self._call_client_method("sheet_get_range", file_id, sheet_id, range_text)

    def sheet_batch_update(self, file_id: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
        return self._call_client_method("sheet_batch_update", file_id, requests)


class AutoOnlineBackend:
    """MCP-first backend that can fall back before write starts."""

    def __init__(
        self,
        primary: Any,
        fallback_factory: Callable[[], Any],
    ) -> None:
        self.active = primary
        self.fallback_factory = fallback_factory
        self.fallback: Any | None = None
        self.fallback_reason = ""
        self.write_started = False

    @property
    def backend_label(self) -> str:
        label = getattr(self.active, "backend_label", self.active.__class__.__name__)
        if self.fallback_reason:
            return f"{label} (fallback: {self.fallback_reason})"
        return label

    def _switch_to_fallback(self, exc: OnlineBackendError) -> Any:
        if self.write_started:
            raise exc
        if self.fallback is None:
            self.fallback = self.fallback_factory()
        self.fallback_reason = f"{getattr(self.active, 'backend_label', 'primary')} -> {exc}"
        self.active = self.fallback
        return self.active

    def _call(self, method_name: str, *args: Any, write: bool = False, **kwargs: Any) -> Any:
        if write:
            self.write_started = True
            try:
                return getattr(self.active, method_name)(*args, **kwargs)
            except OnlineBackendError as exc:
                raise OnlineBackendWriteBoundary(
                    f"写入阶段 {getattr(self.active, 'backend_label', 'backend')} 失败，"
                    f"为避免重复或部分写入，不自动 fallback: {exc}"
                ) from exc

        try:
            return getattr(self.active, method_name)(*args, **kwargs)
        except (OnlineBackendRateLimited, OnlineBackendUnavailable) as exc:
            fallback = self._switch_to_fallback(exc)
            try:
                return getattr(fallback, method_name)(*args, **kwargs)
            except OnlineBackendError as fallback_exc:
                raise OnlineBackendError(
                    f"主后端失败后 fallback 也失败: {fallback_exc}; 主后端原因: {exc}"
                ) from fallback_exc

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._call("call_tool", name, arguments)

    def query_file_info(self, file_id: str) -> dict[str, Any]:
        return self._call("query_file_info", file_id)

    def sheet_get_info(self, file_id: str, concise: bool = False) -> dict[str, Any]:
        return self._call("sheet_get_info", file_id, concise=concise)

    def sheet_batch_update(self, file_id: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
        return self._call("sheet_batch_update", file_id, requests, write=True)


def build_online_backend(args: Any) -> Any:
    mode = str(getattr(args, "online_backend", "") or "auto")
    timeout = int(getattr(args, "timeout", 60) or 60)

    def mcp_backend() -> TencentDocsMcpBackend:
        return TencentDocsMcpBackend(
            mcp_config_path=getattr(args, "mcp_config", None),
            server_name=str(getattr(args, "mcp_server_name", "") or DEFAULT_MCP_SERVER_NAME),
            timeout=timeout,
            min_interval=float(getattr(args, "min_interval", 0.0) or 0.0),
            retries=int(getattr(args, "retries", 0) or 0),
            rate_limit_sleep=int(getattr(args, "rate_limit_sleep", 300) or 300),
        )

    def api_backend() -> TxSaasDocsApiBackend:
        return TxSaasDocsApiBackend(
            config_path=getattr(args, "saas_config_path", None),
            timeout=timeout,
        )

    if mode == "mcp":
        return mcp_backend()
    if mode == "saas-api":
        return api_backend()
    if mode != "auto":
        raise OnlineBackendError(f"不支持的 online backend: {mode}")

    try:
        return AutoOnlineBackend(mcp_backend(), api_backend)
    except OnlineBackendUnavailable as exc:
        backend = api_backend()
        backend.backend_label = f"{backend.backend_label} (fallback: mcp unavailable: {exc})"
        return backend
