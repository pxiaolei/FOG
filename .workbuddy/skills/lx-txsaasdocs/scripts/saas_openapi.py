#!/usr/bin/env python3
"""Tencent Docs SaaS OpenAPI client.

This client intentionally avoids MCP. It only wraps endpoints that are
confirmed in Tencent's SaaS OpenAPI docs.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import yaml


class TxSaasDocsError(RuntimeError):
    """Tencent Docs SaaS OpenAPI failed."""


def _project_config_path(start: Path) -> Path:
    for parent in start.resolve().parents:
        candidate = parent / "config" / "fog_config.yaml"
        if candidate.exists() or (parent / ".workbuddy").exists():
            return candidate
    return Path("config/fog_config.yaml")


SCRIPT_PATH = Path(__file__)
DEFAULT_PROJECT_CONFIG = _project_config_path(SCRIPT_PATH)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise TxSaasDocsError(f"配置顶层不是对象: {path}")
    return data


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _api_config_from_file(path: Path) -> tuple[dict[str, Any], dict[str, Any], bool]:
    data = _read_yaml(path)
    if "lx_txsaasdocs" in data:
        section = data.setdefault("lx_txsaasdocs", {})
        if not isinstance(section, dict):
            raise TxSaasDocsError(f"lx_txsaasdocs 配置不是对象: {path}")
        api = section.setdefault("api", {})
        if not isinstance(api, dict):
            raise TxSaasDocsError(f"lx_txsaasdocs.api 配置不是对象: {path}")
        return data, api, True

    api = data.setdefault("api", {})
    if not isinstance(api, dict):
        raise TxSaasDocsError(f"api 配置不是对象: {path}")
    return data, api, False


def _resolve_config_path(value: str | None) -> Path:
    if value:
        return Path(value).expanduser()
    return DEFAULT_PROJECT_CONFIG


class TxSaasDocsClient:
    def __init__(self, config_path: str | Path | None = None, timeout: int = 60):
        self.config_path = _resolve_config_path(str(config_path) if config_path else None)
        self.config_data, self.api_config, self.uses_project_section = _api_config_from_file(self.config_path)
        self.timeout = timeout
        self.base_url = str(self.api_config.get("base_url", "")).rstrip("/")
        self.token_endpoint = str(self.api_config.get("token_endpoint", "")).strip()
        self.client_id = str(self.api_config.get("client_id", "")).strip()
        self.client_secret = str(self.api_config.get("client_secret", "")).strip()
        if not self.base_url:
            raise TxSaasDocsError("未配置 lx_txsaasdocs.api.base_url")
        if not self.client_id:
            raise TxSaasDocsError("未配置 lx_txsaasdocs.api.client_id")

    def _cached_token(self) -> str:
        token = str(self.api_config.get("access_token", "")).strip()
        expires_at = int(self.api_config.get("token_expires_at") or 0)
        if token and expires_at > int(time.time()) + 120:
            return token
        return ""

    def access_token(self, save: bool = True) -> str:
        import requests  # noqa: WPS433

        cached = self._cached_token()
        if cached:
            return cached
        if not self.token_endpoint or not self.client_secret:
            raise TxSaasDocsError("未配置 token_endpoint 或 client_secret，无法获取企业内部应用 access_token")

        resp = requests.post(
            self.token_endpoint,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        data = _parse_response(resp)
        token = str(data.get("access_token", "")).strip()
        if not token:
            raise TxSaasDocsError(f"Token 响应缺少 access_token: {_safe_json(data)}")

        expires_in = int(data.get("expires_in") or 0)
        self.api_config["access_token"] = token
        self.api_config["token_type"] = data.get("token_type", "")
        self.api_config["token_expires_at"] = int(time.time()) + max(expires_in, 0)
        if save:
            _write_yaml(self.config_path, self.config_data)
        return token

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        import requests  # noqa: WPS433

        url = urljoin(self.base_url + "/", path.lstrip("/"))
        headers = {
            "Access-Token": self.access_token(),
            "Client-Id": self.client_id,
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        resp = requests.request(method, url, headers=headers, json=body, timeout=self.timeout)
        return _parse_response(resp)

    def get_file(self, file_id: str) -> dict[str, Any]:
        return self.request("GET", f"/openapi/drive/v3/files/{file_id}")

    def list_smartsheets(self, file_id: str) -> dict[str, Any]:
        return self.request("GET", f"/openapi/smartsheet/v2/files/{file_id}/sheets")

    def add_smartsheet(self, file_id: str, title: str, index: int | None = None) -> dict[str, Any]:
        properties: dict[str, Any] = {"title": title}
        if index is not None:
            properties["index"] = index
        return self.request(
            "POST",
            f"/openapi/smartsheet/v2/files/{file_id}/sheets",
            {"addSheet": {"properties": properties}},
        )

    def add_records(self, file_id: str, sheet_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        payload_records = [
            record if "values" in record else {"values": record}
            for record in records
        ]
        return self.request(
            "POST",
            f"/openapi/smartsheet/v2/files/{file_id}/sheets/{sheet_id}/records",
            {"addRecords": {"records": payload_records}},
        )


def _parse_response(resp: Any) -> dict[str, Any]:
    trace_id = resp.headers.get("X-Trace-Id", "")
    try:
        data = resp.json()
    except ValueError as exc:
        raise TxSaasDocsError(f"HTTP {resp.status_code} 返回非 JSON，Trace-Id={trace_id}") from exc
    if resp.status_code >= 400:
        raise TxSaasDocsError(f"HTTP {resp.status_code}: {_safe_json(data)} Trace-Id={trace_id}")
    if isinstance(data, dict):
        code = data.get("code")
        ret = data.get("ret")
        if code not in (None, 0, "0") or ret not in (None, 0, "0"):
            raise TxSaasDocsError(f"API 返回错误: {_safe_json(data)} Trace-Id={trace_id}")
        return data
    raise TxSaasDocsError(f"响应顶层不是对象: {_safe_json(data)} Trace-Id={trace_id}")


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)[:1000]


def _load_records(path: str) -> list[dict[str, Any]]:
    with Path(path).expanduser().open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, dict) and "addRecords" in payload:
        records = payload.get("addRecords", {}).get("records", [])
    elif isinstance(payload, dict) and "records" in payload:
        records = payload["records"]
    else:
        records = payload
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise TxSaasDocsError("records-json 必须是记录对象列表，或包含 addRecords.records")
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="lx-txsaasdocs 腾讯文档企业版 OpenAPI 工具")
    parser.add_argument("--config-path", help="配置文件路径，默认优先 config/fog_config.yaml")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP 超时秒数")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("verify-auth", help="获取或验证企业内部应用 access_token")

    get_file = subparsers.add_parser("get-file", help="查询文件信息")
    get_file.add_argument("file_id")

    list_sheets = subparsers.add_parser("list-smartsheets", help="查询在线智能表子表")
    list_sheets.add_argument("file_id")

    add_sheet = subparsers.add_parser("add-smartsheet", help="新增在线智能表子表")
    add_sheet.add_argument("file_id")
    add_sheet.add_argument("--title", required=True)
    add_sheet.add_argument("--index", type=int)

    add_records = subparsers.add_parser("add-records", help="追加在线智能表记录")
    add_records.add_argument("file_id")
    add_records.add_argument("sheet_id")
    add_records.add_argument("--records-json", required=True)
    add_records.add_argument("--dry-run", action="store_true")
    add_records.add_argument("--confirmed", action="store_true")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = TxSaasDocsClient(config_path=args.config_path, timeout=args.timeout)

    if args.command == "verify-auth":
        token = client.access_token(save=True)
        print(json.dumps({"ok": True, "access_token": "[已隐藏]", "length": len(token)}, ensure_ascii=False, indent=2))
        return

    if args.command == "get-file":
        result = client.get_file(args.file_id)
    elif args.command == "list-smartsheets":
        result = client.list_smartsheets(args.file_id)
    elif args.command == "add-smartsheet":
        result = client.add_smartsheet(args.file_id, args.title, args.index)
    elif args.command == "add-records":
        records = _load_records(args.records_json)
        if args.dry_run:
            print(json.dumps({"dry_run": True, "records": records}, ensure_ascii=False, indent=2))
            return
        if not args.confirmed:
            raise TxSaasDocsError("写入企业版腾讯文档必须先 dry-run，并在正式执行时传 --confirmed")
        result = client.add_records(args.file_id, args.sheet_id, records)
    else:
        raise TxSaasDocsError(f"未知命令: {args.command}")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
