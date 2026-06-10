#!/usr/bin/env python3
"""Online spreadsheet backend for lx-biaogetongbu.

FOG online writes use Feishu ordinary Sheets only.
"""

from __future__ import annotations

import sys
from csv import writer
from io import StringIO
from pathlib import Path
from typing import Any


class OnlineBackendError(RuntimeError):
    """Base error for online spreadsheet backends."""


class OnlineBackendUnavailable(OnlineBackendError):
    """Backend credentials, config, or network are unavailable."""


class OnlineBackendUnsupported(OnlineBackendError):
    """Backend does not support this operation."""


def _skills_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent.parent
        if (candidate / "lx-feishudocs" / "scripts" / "feishu_sheets.py").exists():
            return candidate
    return Path(__file__).resolve().parents[1]


def _col_to_a1(column: int) -> str:
    result = ""
    current = column
    while current:
        current, rem = divmod(current - 1, 26)
        result = chr(65 + rem) + result
    return result


def _csv_text(rows: list[list[Any]]) -> str:
    buffer = StringIO()
    csv_writer = writer(buffer)
    csv_writer.writerows(rows)
    return buffer.getvalue()


def _cell_to_value(cell: Any) -> Any:
    if not isinstance(cell, dict):
        return cell
    cell_value = cell.get("cell_value")
    if not isinstance(cell_value, dict):
        return ""
    for key in ("text", "number", "time"):
        if key in cell_value:
            return cell_value.get(key)
    link = cell_value.get("link")
    if isinstance(link, dict):
        return link.get("text") or link.get("url") or ""
    selected = cell_value.get("select")
    if isinstance(selected, dict):
        value = selected.get("value")
        return ",".join(str(item) for item in value) if isinstance(value, list) else value
    return ""


def _value_to_cell(value: Any) -> dict[str, Any]:
    if value is None:
        return {"cell_value": {"text": ""}}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"cell_value": {"number": value}}
    return {"cell_value": {"text": str(value)}}


class FeishuSheetsBackend:
    """Adapter around lx-feishudocs for ordinary Feishu Sheets."""

    backend_label = "lx-feishudocs-sheets"

    def __init__(self, cli_path: str | Path | None = None, config_path: str | Path | None = None, timeout: int = 120) -> None:
        scripts_dir = _skills_root() / "lx-feishudocs" / "scripts"
        if not scripts_dir.exists():
            raise OnlineBackendUnavailable(f"缺少 lx-feishudocs 脚本目录: {scripts_dir}")
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        try:
            from feishu_sheets import FeishuSheetsClient, FeishuSheetsError  # noqa: WPS433
        except ImportError as exc:
            raise OnlineBackendUnavailable(f"无法导入 lx-feishudocs: {exc}") from exc

        self._error_type = FeishuSheetsError
        try:
            self.client = FeishuSheetsClient(cli_path=cli_path, config_path=config_path, timeout=timeout)
        except FeishuSheetsError as exc:
            raise OnlineBackendUnavailable(f"lx-feishudocs 配置不可用: {exc}") from exc

    def _call(self, name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            result = getattr(self.client, name)(*args, **kwargs)
        except self._error_type as exc:
            raise OnlineBackendError(f"lx-feishudocs 调用失败: {exc}") from exc
        if not isinstance(result, dict):
            raise OnlineBackendError(f"lx-feishudocs {name} 返回顶层不是对象")
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
        raise OnlineBackendUnsupported(f"lx-feishudocs 不支持工具名: {name}")

    def query_file_info(self, file_id: str) -> dict[str, Any]:
        return {"file_id": file_id, "spreadsheet_token": file_id}

    def sheet_get_info(self, file_id: str, concise: bool = False) -> dict[str, Any]:
        result = self._call("workbook_info", spreadsheet_token=file_id)
        return {"properties": self.client.sheet_properties(result), "raw": result if not concise else {}}

    def sheet_get_range(self, file_id: str, sheet_id: str, range_text: str) -> dict[str, Any]:
        result = self._call(
            "csv_get",
            spreadsheet_token=file_id,
            sheet_id=sheet_id,
            range_text=range_text,
        )
        rows = self.client.csv_rows(result)
        return {
            "grid_data": {
                "rows": [
                    {"values": [_value_to_cell(value) for value in row]}
                    for row in rows
                ]
            }
        }

    def sheet_batch_update(self, file_id: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for request in requests:
            update = request.get("update_range") if isinstance(request, dict) else None
            if not isinstance(update, dict):
                raise OnlineBackendUnsupported("lx-feishudocs 仅支持 update_range 写入普通表格")
            sheet_id = str(update.get("sheet_id") or "")
            grid = update.get("grid_data")
            if not sheet_id or not isinstance(grid, dict):
                raise OnlineBackendError("update_range 缺少 sheet_id 或 grid_data")
            start_row = int(grid.get("start_row") or 0) + 1
            start_col = int(grid.get("start_column") or 0) + 1
            rows_raw = grid.get("rows", [])
            if not isinstance(rows_raw, list):
                raise OnlineBackendError("grid_data.rows 不是列表")
            rows: list[list[Any]] = []
            for row in rows_raw:
                values = row.get("values", []) if isinstance(row, dict) else []
                rows.append([_cell_to_value(cell) for cell in values])
            start_cell = f"{_col_to_a1(start_col)}{start_row}"
            results.append(
                self._call(
                    "csv_put",
                    spreadsheet_token=file_id,
                    sheet_id=sheet_id,
                    start_cell=start_cell,
                    csv_text=_csv_text(rows),
                )
            )
        return {"ok": True, "results": results}


def build_online_backend(args: Any) -> Any:
    mode = str(getattr(args, "online_backend", "") or "feishu")
    timeout = int(getattr(args, "timeout", 60) or 60)
    if mode != "feishu":
        raise OnlineBackendError(f"不支持的 online backend: {mode}；当前只支持 feishu")
    return FeishuSheetsBackend(
        cli_path=getattr(args, "lark_cli", None),
        config_path=getattr(args, "feishu_config_path", None),
        timeout=max(timeout, 120),
    )
