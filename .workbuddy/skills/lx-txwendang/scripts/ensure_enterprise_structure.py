#!/usr/bin/env python3
"""Ensure enterprise Tencent Docs folders and spreadsheets exist.

Default structure:
  root_folder / {operator}-运营主体 / {operator}-{suffix}

The script is resumable. Successful IDs are persisted to
assets/enterprise_entity_cache.json after each create/find operation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ASSETS_DIR = SKILL_DIR / "assets"
DEFAULT_CACHE_PATH = ASSETS_DIR / "enterprise_entity_cache.json"
DEFAULT_SUFFIXES = ["大盘数据日报", "日常信息", "背审申诉", "静默乘客"]


def _find_skills_dir() -> Path:
    for p in Path(__file__).resolve().parents:
        if (p / "lxx_share").is_dir():
            return p
    return Path(__file__).resolve().parents[2]


SKILLS_DIR = _find_skills_dir()
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from saas_mcp import SaasDocsClient, SaasDocsRateLimitError  # noqa: E402


def _project_root() -> Path:
    for candidate in [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents]:
        if (candidate / "config" / "fog_config.yaml").exists():
            return candidate
    return SKILLS_DIR.parents[1]


PROJECT_ROOT = _project_root()


def _load_yaml_if_available() -> dict[str, Any]:
    try:
        from lxx_share.fog_config import load_fog_config  # noqa: WPS433

        return load_fog_config(PROJECT_ROOT)
    except Exception:
        return {}


def _dailyreport_config() -> dict[str, Any]:
    data = _load_yaml_if_available()
    section = data.get("lx_dapanribao", {})
    return section if isinstance(section, dict) else {}


def _default_root_folder_id() -> str:
    return str(_dailyreport_config().get("enterprise_root_folder_id", "") or "")


def _default_person() -> str:
    return str(_dailyreport_config().get("default_person", "") or "")


def _default_folder_template() -> str:
    return str(_dailyreport_config().get("operator_folder_name_template", "{operator}-运营主体") or "{operator}-运营主体")


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": 1,
            "root_folder_id": "",
            "entities": {},
        }
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise RuntimeError(f"企业版缓存顶层不是对象: {path}")
    data.setdefault("schema_version", 1)
    data.setdefault("root_folder_id", "")
    data.setdefault("entities", {})
    if not isinstance(data["entities"], dict):
        raise RuntimeError(f"企业版缓存 entities 不是对象: {path}")
    return data


def _save_cache(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _entity_entry(cache: dict[str, Any], operator: str) -> dict[str, Any]:
    entities = cache.setdefault("entities", {})
    entry = entities.setdefault(operator, {})
    entry.setdefault("files", {})
    return entry


def _exact_search(client: SaasDocsClient, title: str) -> dict[str, Any] | None:
    for item in client.search_file(title):
        if isinstance(item, dict) and item.get("title") == title:
            return item
    return None


def _file_id(item: dict[str, Any]) -> str:
    return str(item.get("file_id") or item.get("id") or "")


def _operators_from_db(person: str, db_config: str | None, limit: int) -> list[str]:
    if not person:
        raise RuntimeError("未指定 --person，且 config/fog_config.yaml 未配置 lx_dapanribao.default_person")

    lx_path = SKILLS_DIR / "lx_shujuku" / "scripts"
    if str(lx_path) not in sys.path:
        sys.path.insert(0, str(lx_path))

    from lx_shujuku import DataReportingClient  # noqa: WPS433

    configs: list[str | None] = []
    if db_config:
        configs.append(db_config)
    else:
        configs.append(str(PROJECT_ROOT / "config" / "fog_config.yaml"))
        fallback = SKILLS_DIR / "lx_shujuku" / "assets" / "config.yaml"
        if fallback.exists():
            configs.append(str(fallback))

    last_error: Exception | None = None
    client = None
    for config in configs:
        try:
            client = DataReportingClient(config_path=config)
            break
        except Exception as exc:
            last_error = exc
    if client is None:
        raise RuntimeError(f"无法初始化 lx_shujuku 客户端: {last_error}")

    safe_person = person.replace("'", "''")
    sql = (
        "SELECT DISTINCT operator_entity FROM operator_brand "
        f"WHERE contact_person = '{safe_person}' "
        "AND operator_entity IS NOT NULL AND operator_entity <> '' "
        f"ORDER BY operator_entity LIMIT {limit}"
    )
    rows = client.execute(sql)
    operators = []
    for row in rows:
        value = row.get("operator_entity") if isinstance(row, dict) else None
        if value:
            operators.append(str(value))
    return operators


def _parse_operator_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _ensure_folder(
    client: SaasDocsClient,
    cache: dict[str, Any],
    cache_path: Path,
    operator: str,
    title: str,
    root_folder_id: str,
    dry_run: bool,
    search: bool,
) -> dict[str, Any]:
    entry = _entity_entry(cache, operator)
    if entry.get("folder_id"):
        return {
            "status": "cached",
            "file_id": entry["folder_id"],
            "title": entry.get("folder_title", title),
            "url": entry.get("folder_url", ""),
        }

    if search:
        found = _exact_search(client, title)
        if found:
            entry["folder_id"] = _file_id(found)
            entry["folder_title"] = found.get("title", title)
            entry["folder_url"] = found.get("url", "")
            _save_cache(cache_path, cache)
            return {"status": "found", **entry}

    if dry_run:
        return {"status": "would-create", "title": title}

    created = client.create_file(title=title, file_type="folder", parent_id=root_folder_id)
    folder_id = _file_id(created)
    if not folder_id:
        raise RuntimeError(f"创建文件夹未返回 file_id: {created}")
    entry["folder_id"] = folder_id
    entry["folder_title"] = created.get("title", title)
    entry["folder_url"] = created.get("url", "")
    _save_cache(cache_path, cache)
    return {"status": "created", **entry}


def _ensure_sheet(
    client: SaasDocsClient,
    cache: dict[str, Any],
    cache_path: Path,
    operator: str,
    suffix: str,
    title: str,
    folder_id: str,
    dry_run: bool,
    search: bool,
) -> dict[str, Any]:
    entry = _entity_entry(cache, operator)
    files = entry.setdefault("files", {})
    file_entry = files.setdefault(suffix, {})
    if file_entry.get("file_id"):
        return {"status": "cached", **file_entry}

    if search:
        found = _exact_search(client, title)
        if found:
            file_entry["file_id"] = _file_id(found)
            file_entry["title"] = found.get("title", title)
            file_entry["url"] = found.get("url", "")
            _save_cache(cache_path, cache)
            return {"status": "found", **file_entry}

    if dry_run:
        return {"status": "would-create", "title": title}

    created = client.create_file(title=title, file_type="sheet", parent_id=folder_id)
    file_id = _file_id(created)
    if not file_id:
        raise RuntimeError(f"创建表格未返回 file_id: {created}")
    file_entry["file_id"] = file_id
    file_entry["title"] = created.get("title", title)
    file_entry["url"] = created.get("url", "")
    _save_cache(cache_path, cache)
    return {"status": "created", **file_entry}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="补齐腾讯文档企业版运营主体文件夹和表格")
    parser.add_argument("--root-folder-id", default=_default_root_folder_id(), help="企业版根文件夹 ID")
    parser.add_argument("--person", default=_default_person(), help="对接人中文全名，用 lx_shujuku 查询运营主体")
    parser.add_argument("--operators", help="逗号分隔的运营主体列表；传入后不查数据库")
    parser.add_argument("--db-config", help="lx_shujuku 配置路径；默认先用 config/fog_config.yaml，再回退 skill assets/config.yaml")
    parser.add_argument("--cache-path", default=str(DEFAULT_CACHE_PATH), help="企业版 file_id 缓存路径")
    parser.add_argument("--folder-template", default=_default_folder_template(), help="文件夹命名模板，支持 {operator}")
    parser.add_argument("--sheet-suffix", action="append", help="要创建的表格后缀；可重复传入")
    parser.add_argument("--mcp-config", help="WorkBuddy MCP 配置路径，默认 ~/.workbuddy/mcp.json")
    parser.add_argument("--server-name", default="tencent-docs", help="MCP server 名称")
    parser.add_argument("--min-interval", type=float, default=3.0, help="MCP 请求最小间隔秒数")
    parser.add_argument("--retries", type=int, default=0, help="遇到限流后的重试次数")
    parser.add_argument("--rate-limit-sleep", type=int, default=300, help="限流重试等待秒数")
    parser.add_argument("--limit", type=int, default=500, help="数据库查询主体上限")
    parser.add_argument("--no-search", action="store_true", help="不调用 search_file；仅信任缓存，缺失时直接创建")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写入腾讯文档")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.root_folder_id:
        print("错误：缺少 --root-folder-id，且配置中未设置 enterprise_root_folder_id", file=sys.stderr)
        return 1

    suffixes = args.sheet_suffix or DEFAULT_SUFFIXES
    operators = _parse_operator_list(args.operators) if args.operators else _operators_from_db(
        person=args.person,
        db_config=args.db_config,
        limit=args.limit,
    )
    if not operators:
        print("错误：未找到运营主体", file=sys.stderr)
        return 1

    cache_path = Path(args.cache_path).expanduser()
    cache = _load_cache(cache_path)
    cache["root_folder_id"] = args.root_folder_id
    _save_cache(cache_path, cache)

    client = SaasDocsClient(
        mcp_config_path=args.mcp_config,
        server_name=args.server_name,
        min_interval=args.min_interval,
        retries=args.retries,
        rate_limit_sleep=args.rate_limit_sleep,
    )
    search = not args.no_search
    results: list[dict[str, Any]] = []

    print("=== 企业版腾讯文档结构补齐 ===")
    print(f"根文件夹: {args.root_folder_id}")
    print(f"主体数量: {len(operators)}")
    print(f"表格后缀: {', '.join(suffixes)}")
    print(f"缓存路径: {cache_path}")
    print(f"模式: {'dry-run' if args.dry_run else 'write'}")
    print()

    try:
        for operator in operators:
            folder_title = args.folder_template.format(operator=operator)
            folder_result = _ensure_folder(
                client=client,
                cache=cache,
                cache_path=cache_path,
                operator=operator,
                title=folder_title,
                root_folder_id=args.root_folder_id,
                dry_run=args.dry_run,
                search=search,
            )
            folder_id = str(folder_result.get("file_id") or folder_result.get("folder_id") or "")
            print(f"{operator}: 文件夹 {folder_result['status']} {folder_title}")
            results.append({
                "operator": operator,
                "kind": "folder",
                "title": folder_title,
                **folder_result,
            })

            if not folder_id and not args.dry_run:
                raise RuntimeError(f"{operator} 缺少 folder_id，无法创建表格")

            for suffix in suffixes:
                sheet_title = f"{operator}-{suffix}"
                sheet_result = _ensure_sheet(
                    client=client,
                    cache=cache,
                    cache_path=cache_path,
                    operator=operator,
                    suffix=suffix,
                    title=sheet_title,
                    folder_id=folder_id,
                    dry_run=args.dry_run,
                    search=search,
                )
                print(f"{operator}: 表格 {sheet_result['status']} {sheet_title}")
                results.append({
                    "operator": operator,
                    "kind": "sheet",
                    "title": sheet_title,
                    "suffix": suffix,
                    **sheet_result,
                })
    except SaasDocsRateLimitError as exc:
        print(f"限流中断：{exc}", file=sys.stderr)
        if args.json:
            print(json.dumps({"results": results, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        if args.json:
            print(json.dumps({"results": results, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    created = sum(1 for item in results if item.get("status") == "created")
    found = sum(1 for item in results if item.get("status") == "found")
    cached = sum(1 for item in results if item.get("status") == "cached")
    planned = sum(1 for item in results if item.get("status") == "would-create")
    print()
    print("=== 完成 ===")
    print(f"created={created} found={found} cached={cached} would-create={planned} total={len(results)}")
    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
