#!/usr/bin/env python3
"""Execute lx-dapanribao publish plans with lx-feishudocs.

The report generator writes a JSON plan. This script turns that plan into
ordinary Feishu Sheets writes and updates the local dailyreport cache.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _SCRIPTS_DIR.parent.parent
_FEISHU_SCRIPTS_DIR = _SKILLS_DIR / "lx-feishudocs" / "scripts"
for _path in (str(_SCRIPTS_DIR), str(_SKILLS_DIR), str(_FEISHU_SCRIPTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from config import load_dailyreport_cache, save_dailyreport_cache
from feishu_sheets import FeishuSheetsClient, FeishuSheetsError


class PublishPlanError(RuntimeError):
    """Plan execution failed."""


@dataclass
class SpreadsheetTarget:
    token: str
    url: str
    title: str
    folder_id: str
    source: str


def _rows_to_csv(rows: list[list[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    return buffer.getvalue()


def _find_nested(value: Any, names: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in names and item not in (None, ""):
                return item
        for item in value.values():
            found = _find_nested(item, names)
            if found not in (None, ""):
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_nested(item, names)
            if found not in (None, ""):
                return found
    return None


def _extract_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("items", "files", "docs", "documents", "results"):
            item = value.get(key)
            if isinstance(item, list) and all(isinstance(row, dict) for row in item):
                return item
        for item in value.values():
            found = _extract_items(item)
            if found:
                return found
    if isinstance(value, list):
        if all(isinstance(row, dict) for row in value):
            return value
        for item in value:
            found = _extract_items(item)
            if found:
                return found
    return []


def _extract_token(value: dict[str, Any]) -> str:
    token = _find_nested(
        value,
        {
            "spreadsheet_token",
            "spreadsheetToken",
            "file_token",
            "fileToken",
            "token",
            "obj_token",
            "objToken",
        },
    )
    return str(token or "")


def _extract_url(value: dict[str, Any]) -> str:
    url = _find_nested(value, {"url", "link", "share_url", "shareUrl"})
    return str(url or "")


def _title_of(item: dict[str, Any]) -> str:
    title = str(
        item.get("title")
        or item.get("name")
        or item.get("file_name")
        or item.get("fileName")
        or item.get("title_highlighted")
        or ""
    )
    return re.sub(r"<[^>]+>", "", title).strip()


def _type_of(item: dict[str, Any]) -> str:
    return str(
        item.get("type")
        or item.get("doc_type")
        or item.get("docType")
        or item.get("file_type")
        or item.get("fileType")
        or ""
    ).strip()


def _sanitize_error(exc: BaseException) -> str:
    text = str(exc)
    text = re.sub(r"(--spreadsheet-token\s+)\S+", r"\1[hidden]", text)
    text = re.sub(r"(--folder-token\s+)\S+", r"\1[hidden]", text)
    text = re.sub(r"([?&](?:token|access_token|refresh_token)=)[^&\s]+", r"\1[hidden]", text)
    return text[:1200]


def _load_plan(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PublishPlanError(f"发布计划不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PublishPlanError(f"发布计划顶层不是对象: {path}")
    reports = data.get("reports")
    if not isinstance(reports, list):
        raise PublishPlanError(f"发布计划缺少 reports 数组: {path}")
    return data


def _col_name(index: int) -> str:
    if index < 1:
        raise ValueError("column index must be >= 1")
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def _sheet_by_title(sheets: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    for sheet in sheets:
        if str(sheet.get("title") or "") == title:
            return sheet
    return None


def _drive_search(
    client: FeishuSheetsClient,
    *,
    query: str,
    doc_types: str,
    folder_token: str = "",
) -> list[dict[str, Any]]:
    args = [
        "drive",
        "+search",
        "--as",
        client.identity,
        "--json",
        "--query",
        query,
        "--doc-types",
        doc_types,
        "--only-title",
        "--page-size",
        "10",
    ]
    if folder_token:
        args.extend(["--folder-tokens", folder_token])
    return _extract_items(client.run(args))


def _find_exact_drive_item(
    client: FeishuSheetsClient,
    *,
    title: str,
    doc_types: str,
    folder_token: str = "",
) -> dict[str, Any] | None:
    for item in _drive_search(
        client,
        query=title,
        doc_types=doc_types,
        folder_token=folder_token,
    ):
        if _title_of(item) == title:
            return item
    return None


def _create_folder(
    client: FeishuSheetsClient,
    *,
    name: str,
    parent_folder_token: str,
    dry_run: bool,
) -> dict[str, Any]:
    args = [
        "drive",
        "+create-folder",
        "--as",
        client.identity,
        "--json",
        "--name",
        name,
    ]
    if parent_folder_token:
        args.extend(["--folder-token", parent_folder_token])
    if dry_run:
        args.append("--dry-run")
    return client.run(args)


def _ensure_operator_folder(
    client: FeishuSheetsClient,
    *,
    root_folder_token: str,
    folder_name: str,
    cached_folder_id: str,
    search_drive: bool,
    create_folders: bool,
    allow_root_folder_fallback: bool,
) -> tuple[str, str]:
    if cached_folder_id:
        return cached_folder_id, "cache"
    if not root_folder_token or not folder_name:
        return root_folder_token, "root"
    if search_drive:
        item = _find_exact_drive_item(
            client,
            title=folder_name,
            doc_types="folder",
            folder_token=root_folder_token,
        )
        if item:
            token = _extract_token(item)
            if token:
                return token, "drive-search"
    if create_folders:
        created = _create_folder(
            client,
            name=folder_name,
            parent_folder_token=root_folder_token,
            dry_run=False,
        )
        token = _extract_token(created)
        if not token:
            raise PublishPlanError(f"创建运营主体文件夹后没有返回 token: {folder_name}")
        return token, "created"
    if not allow_root_folder_fallback:
        raise PublishPlanError(
            f"未找到运营主体文件夹: {folder_name}。可先确认飞书目录，"
            "或加 --create-folders / --allow-root-folder-fallback。"
        )
    return root_folder_token, "root"


def _candidate_tokens(report: dict[str, Any], cache_entry: dict[str, Any]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for key in ("spreadsheet_token", "file_id"):
        value = str(report.get(key) or "").strip()
        if value:
            candidates.append((value, f"plan.{key}"))
    if not _is_legacy_cache_entry(cache_entry):
        for key in ("spreadsheet_token", "file_id"):
            value = str(cache_entry.get(key) or "").strip()
            if value:
                candidates.append((value, f"cache.{key}"))

    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for token, source in candidates:
        if token in seen:
            continue
        seen.add(token)
        unique.append((token, source))
    return unique


def _is_legacy_cache_entry(cache_entry: dict[str, Any]) -> bool:
    url = str(cache_entry.get("url") or "").lower()
    token = str(cache_entry.get("file_id") or "")
    return "docs.qq.com" in url or token.startswith("300000000$")


def _resolve_spreadsheet(
    client: FeishuSheetsClient,
    *,
    report: dict[str, Any],
    cache_entry: dict[str, Any],
    folder_id: str,
    search_drive: bool,
    create_missing: bool,
) -> SpreadsheetTarget:
    title = str(report.get("spreadsheet_title") or report.get("operator") or "").strip()
    cached_url = str(cache_entry.get("url") or "").strip()

    for token, source in _candidate_tokens(report, cache_entry):
        try:
            info = client.workbook_info(spreadsheet_token=token)
            return SpreadsheetTarget(
                token=token,
                url=cached_url or _extract_url(info),
                title=title,
                folder_id=folder_id,
                source=source,
            )
        except Exception:
            continue

    if search_drive and title:
        item = _find_exact_drive_item(
            client,
            title=title,
            doc_types="sheet",
            folder_token=folder_id,
        )
        if item:
            token = _extract_token(item)
            if token:
                info = client.workbook_info(spreadsheet_token=token)
                return SpreadsheetTarget(
                    token=token,
                    url=_extract_url(item) or _extract_url(info),
                    title=title,
                    folder_id=folder_id,
                    source="drive-search",
                )

    if create_missing:
        created = client.workbook_create(title, folder_token=folder_id)
        token = client.spreadsheet_token(created)
        if not token:
            raise PublishPlanError(f"创建普通表格后没有返回 spreadsheet_token: {title}")
        return SpreadsheetTarget(
            token=token,
            url=_extract_url(created),
            title=title,
            folder_id=folder_id,
            source="created",
        )

    raise PublishPlanError(
        f"未找到可用普通表格: {title}。可先写入 dailyreport_cache.json，"
        "或加 --search-drive / --create-missing。"
    )


def _ensure_sheet(
    client: FeishuSheetsClient,
    *,
    target: SpreadsheetTarget,
    sheet_name: str,
    rows: list[list[Any]],
    column_count: int,
    replace_sheet: bool,
) -> dict[str, Any]:
    info = client.workbook_info(spreadsheet_token=target.token)
    sheets = client.sheet_properties(info)
    existing = _sheet_by_title(sheets, sheet_name)

    if existing and not replace_sheet:
        raise PublishPlanError(
            f"{target.title} 已存在 Sheet {sheet_name}，如需覆盖请加 --replace-sheet。"
        )

    if existing:
        clear_cols = max(int(existing.get("column_count") or 0), column_count, 1)
        clear_rows = max(int(existing.get("row_count") or 0), len(rows), 1)
        clear_range = f"A1:{_col_name(clear_cols)}{clear_rows}"
        client.run(
            [
                "sheets",
                "+cells-clear",
                "--as",
                client.identity,
                "--json",
                "--spreadsheet-token",
                target.token,
                "--sheet-name",
                sheet_name,
                "--range",
                clear_range,
                "--scope",
                "all",
                "--yes",
            ]
        )
        return existing

    client.run(
        [
            "sheets",
            "+sheet-create",
            "--as",
            client.identity,
            "--json",
            "--spreadsheet-token",
            target.token,
            "--title",
            sheet_name,
            "--row-count",
            str(max(len(rows), 200)),
            "--col-count",
            str(min(max(column_count, 20), 200)),
        ]
    )
    info = client.workbook_info(spreadsheet_token=target.token)
    created = _sheet_by_title(client.sheet_properties(info), sheet_name)
    if not created:
        raise PublishPlanError(f"创建 Sheet 后未能在工作簿中找到: {sheet_name}")
    return created


def _verify_write(
    client: FeishuSheetsClient,
    *,
    target: SpreadsheetTarget,
    sheet_name: str,
    rows: list[list[Any]],
    column_count: int,
) -> dict[str, Any]:
    if not rows:
        raise PublishPlanError("data_rows 为空，无法验收")

    header_range = f"A1:{_col_name(column_count)}1"
    header_result = client.csv_get(
        spreadsheet_token=target.token,
        sheet_name=sheet_name,
        range_text=header_range,
    )
    header_rows = client.csv_rows(header_result)
    expected_header = [str(value) for value in rows[0]]
    actual_header = header_rows[0][: len(expected_header)] if header_rows else []
    if actual_header != expected_header:
        raise PublishPlanError(f"写后表头不匹配: {target.title} / {sheet_name}")

    first_col_result = client.csv_get(
        spreadsheet_token=target.token,
        sheet_name=sheet_name,
        range_text=f"A1:A{len(rows)}",
    )
    first_col_rows = client.csv_rows(first_col_result)
    non_empty = [row for row in first_col_rows if row and str(row[0]).strip()]
    if len(non_empty) < len(rows):
        raise PublishPlanError(
            f"写后行数不足: 期望至少 {len(rows)} 行，读回 {len(non_empty)} 行"
        )
    return {"header_ok": True, "first_col_rows": len(non_empty)}


def _update_cache(
    cache: dict[str, dict[str, Any]],
    *,
    operator: str,
    target: SpreadsheetTarget,
    sheet: dict[str, Any],
    sheet_name: str,
) -> None:
    entry = dict(cache.get(operator) or {})
    entry.update(
        {
            "file_id": target.token,
            "folder_id": target.folder_id,
            "url": target.url or entry.get("url", ""),
            "title": target.title,
            "last_sheet_id": str(sheet.get("sheet_id") or ""),
            "last_sheet_name": sheet_name,
        }
    )
    cache[operator] = entry


def _parse_operators(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def _summarize_plan(plan: dict[str, Any], reports: list[dict[str, Any]]) -> None:
    print(f"发布计划: contact_person={plan.get('contact_person') or '-'}")
    print(f"目标日期 Sheet: {plan.get('target_rules', {}).get('sheet_name') or '-'}")
    print(f"待发布主体: {len(reports)}")
    for report in reports:
        print(
            f"  - {report.get('operator')}: "
            f"{report.get('spreadsheet_title')} / "
            f"sheet={report.get('sheet_name')}, "
            f"rows={len(report.get('data_rows') or [])}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="执行 lx-dapanribao 飞书普通表格发布计划")
    parser.add_argument("--plan", required=True, help="dapanribao_publish_plan_*.json")
    parser.add_argument("--operators", default="", help="只发布指定运营主体，多个用英文逗号分隔")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不调用飞书写接口")
    parser.add_argument("--confirmed", action="store_true", help="确认执行真实飞书写入")
    parser.add_argument("--replace-sheet", action="store_true", help="同名日期 Sheet 已存在时清空并覆盖")
    parser.add_argument("--search-drive", action="store_true", help="用飞书 Drive 搜索运营主体文件夹和表格")
    parser.add_argument("--create-missing", action="store_true", help="找不到表格时创建普通表格")
    parser.add_argument("--create-folders", action="store_true", help="找不到运营主体文件夹时创建文件夹")
    parser.add_argument("--allow-root-folder-fallback", action="store_true", help="找不到运营主体文件夹时允许直接使用根目录")
    parser.add_argument("--no-cache-update", action="store_true", help="真实写入后不更新 dailyreport_cache.json")
    parser.add_argument("--summary-file", default="", help="写入执行摘要 JSON")
    parser.add_argument("--config-path", default="", help="config/fog_config.yaml 路径")
    parser.add_argument("--cli-path", default="", help="lark-cli 路径")
    parser.add_argument("--identity", choices=["user", "bot"], default="", help="飞书身份")
    parser.add_argument("--timeout", type=int, default=180, help="单次 lark-cli 超时秒数")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    plan_path = Path(args.plan).expanduser()
    plan = _load_plan(plan_path)
    reports = [row for row in plan["reports"] if isinstance(row, dict)]
    selected = _parse_operators(args.operators)
    if selected:
        reports = [row for row in reports if str(row.get("operator") or "") in selected]
    if not reports:
        raise PublishPlanError("没有可发布的 reports")

    _summarize_plan(plan, reports)
    if args.dry_run:
        print("\n[DRY RUN] 未执行飞书写入。")
        return 0
    if not args.confirmed:
        raise PublishPlanError("真实写入必须显式传 --confirmed。")

    client = FeishuSheetsClient(
        cli_path=args.cli_path or None,
        config_path=args.config_path or None,
        identity=args.identity or None,
        timeout=args.timeout,
    )
    cache = load_dailyreport_cache()
    root_folder_token = str(
        plan.get("feishu_root_folder_token")
        or plan.get("root_folder_id")
        or ""
    ).strip()
    summary: list[dict[str, Any]] = []

    for report in reports:
        operator = str(report.get("operator") or "").strip()
        title = str(report.get("spreadsheet_title") or operator).strip()
        sheet_name = str(report.get("sheet_name") or "").strip()
        rows = report.get("data_rows")
        if not operator or not sheet_name or not isinstance(rows, list) or not rows:
            summary.append({"operator": operator or "-", "ok": False, "error": "report 字段不完整"})
            print(f"  ❌ {operator or '-'}: report 字段不完整")
            continue

        row_count = len(rows)
        column_count = int(report.get("column_count") or max(len(row) for row in rows))
        cache_entry = cache.get(operator) or {}
        folder_name = str(report.get("operator_folder_name") or "").strip()
        cached_folder_id = "" if _is_legacy_cache_entry(cache_entry) else str(
            cache_entry.get("folder_id") or ""
        ).strip()

        try:
            folder_id, folder_source = _ensure_operator_folder(
                client,
                root_folder_token=root_folder_token,
                folder_name=folder_name,
                cached_folder_id=cached_folder_id,
                search_drive=args.search_drive,
                create_folders=args.create_folders,
                allow_root_folder_fallback=args.allow_root_folder_fallback,
            )
            target = _resolve_spreadsheet(
                client,
                report=report,
                cache_entry=cache_entry,
                folder_id=folder_id,
                search_drive=args.search_drive,
                create_missing=args.create_missing,
            )
            sheet = _ensure_sheet(
                client,
                target=target,
                sheet_name=sheet_name,
                rows=rows,
                column_count=column_count,
                replace_sheet=args.replace_sheet,
            )
            client.csv_put(
                spreadsheet_token=target.token,
                sheet_name=sheet_name,
                start_cell="A1",
                csv_text=_rows_to_csv(rows),
            )
            verify = _verify_write(
                client,
                target=target,
                sheet_name=sheet_name,
                rows=rows,
                column_count=column_count,
            )
            if not args.no_cache_update:
                _update_cache(
                    cache,
                    operator=operator,
                    target=target,
                    sheet=sheet,
                    sheet_name=sheet_name,
                )
            summary.append(
                {
                    "operator": operator,
                    "ok": True,
                    "spreadsheet_title": title,
                    "sheet_name": sheet_name,
                    "row_count": row_count,
                    "folder_source": folder_source,
                    "spreadsheet_source": target.source,
                    "verification": verify,
                }
            )
            print(
                f"  ✅ {operator}: {title} / sheet={sheet_name}, "
                f"{row_count} 行，已读回验收"
            )
        except Exception as exc:
            error = _sanitize_error(exc)
            summary.append({"operator": operator, "ok": False, "error": error})
            print(f"  ❌ {operator}: {error}")

    if not args.no_cache_update:
        save_dailyreport_cache(cache)

    if args.summary_file:
        summary_path = Path(args.summary_file).expanduser()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps({"plan": str(plan_path), "results": summary}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\n执行摘要: {summary_path}")

    failed = [row for row in summary if not row.get("ok")]
    if failed:
        raise PublishPlanError(f"{len(failed)} 个运营主体发布失败")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PublishPlanError, FeishuSheetsError) as exc:
        raise SystemExit(f"ERROR: {_sanitize_error(exc)}") from exc
