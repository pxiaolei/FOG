"""共享缓存格式校验工具。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("lxx.cache_utils")

CACHE_SCHEMA_VERSION = 1
ENTITY_CACHE_SECTION = "entities"
DAILYREPORT_CACHE_SECTION = "reports"


def load_entity_cache(path: str | Path) -> dict[str, dict[str, Any]]:
    """读取 entity_cache.json，兼容旧扁平格式并校验关键字段。"""
    return _load_cache(
        path=Path(path),
        section=ENTITY_CACHE_SECTION,
        cache_name="entity_cache.json",
        required_fields=("file_id", "folder_id", "url"),
    )


def load_dailyreport_cache(path: str | Path) -> dict[str, dict[str, Any]]:
    """读取 dailyreport_cache.json，兼容旧扁平格式并校验关键字段。"""
    return _load_cache(
        path=Path(path),
        section=DAILYREPORT_CACHE_SECTION,
        cache_name="dailyreport_cache.json",
        required_fields=("file_id",),
    )


def save_dailyreport_cache(path: str | Path, reports: dict[str, dict[str, Any]]) -> None:
    """以版本化格式保存 dailyreport_cache.json。"""
    _validate_entries(
        data=reports,
        path=Path(path),
        cache_name="dailyreport_cache.json",
        required_fields=("file_id",),
    )
    _write_cache(Path(path), DAILYREPORT_CACHE_SECTION, reports)


def save_entity_cache(path: str | Path, entities: dict[str, dict[str, Any]]) -> None:
    """以版本化格式保存 entity_cache.json。"""
    _validate_entries(
        data=entities,
        path=Path(path),
        cache_name="entity_cache.json",
        required_fields=("file_id", "folder_id", "url"),
    )
    _write_cache(Path(path), ENTITY_CACHE_SECTION, entities)


def versioned_entity_cache_template() -> dict[str, Any]:
    """返回可复制的 entity_cache.json 新格式示例。"""
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        ENTITY_CACHE_SECTION: {
            "拼哒出行": {
                "file_id": "腾讯文档表格ID",
                "folder_id": "运营主体文件夹ID",
                "url": "腾讯文档链接",
            }
        },
    }


def _load_cache(
    path: Path,
    section: str,
    cache_name: str,
    required_fields: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise RuntimeError(f"{cache_name} 顶层格式不是对象: {path}")

    if "schema_version" in raw:
        version = raw.get("schema_version")
        if version != CACHE_SCHEMA_VERSION:
            raise RuntimeError(
                f"{cache_name} schema_version 不支持: {version}，当前支持 {CACHE_SCHEMA_VERSION}"
            )
        data = raw.get(section)
        if not isinstance(data, dict):
            raise RuntimeError(f"{cache_name} 缺少对象字段 {section}: {path}")
    else:
        logger.warning("%s 使用旧扁平缓存格式，建议迁移到 schema_version=1", path)
        data = raw

    _validate_entries(data, path, cache_name, required_fields)
    return data


def _validate_entries(
    data: dict[str, Any],
    path: Path,
    cache_name: str,
    required_fields: tuple[str, ...],
) -> None:
    for name, entry in data.items():
        if not isinstance(entry, dict):
            raise RuntimeError(f"{cache_name} 条目不是对象: {path} -> {name}")
        missing = [field for field in required_fields if field not in entry]
        if missing:
            fields = ", ".join(missing)
            raise RuntimeError(f"{cache_name} 条目缺少字段 {fields}: {path} -> {name}")


def _write_cache(path: Path, section: str, data: dict[str, dict[str, Any]]) -> None:
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        section: data,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    path.chmod(0o600)
