"""Configuration helpers for lx-celuehuodong."""

from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "config" / "fog_config.yaml.example").exists() and (candidate / ".workbuddy").is_dir():
            return candidate
    return Path.cwd().resolve()


PROJECT_ROOT = find_project_root()
SKILLS_DIR = PROJECT_ROOT / ".workbuddy" / "skills"
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def resolve_project_path(value: str | Path | None, default: str) -> Path:
    raw = str(value or default)
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def load_celuehuodong_config(config_path: str | Path | None = None) -> dict[str, Any]:
    if config_path:
        raw = load_yaml(Path(config_path).expanduser())
        section = raw.get("lx_celuehuodong", raw)
    else:
        example = load_yaml(PROJECT_ROOT / "config" / "fog_config.yaml.example").get("lx_celuehuodong", {})
        shared = load_yaml(PROJECT_ROOT / "config" / "fog_config.yaml").get("lx_celuehuodong", {})
        personal = load_yaml(PROJECT_ROOT / "config" / "personal_config.yaml").get("lx_celuehuodong", {})
        section = deep_merge(deep_merge(example if isinstance(example, dict) else {}, shared if isinstance(shared, dict) else {}), personal if isinstance(personal, dict) else {})

    if not isinstance(section, dict):
        section = {}

    config = dict(section)
    config["项目根目录"] = str(PROJECT_ROOT)
    config["strategy_workbook_path"] = resolve_project_path(
        config.get("strategy_workbook"),
        "workspace/05策略活动/策略活动表/城市策略活动表2604版_v2.xlsm",
    )
    config["import_output_dir_path"] = resolve_project_path(
        config.get("import_output_dir"),
        "workspace/05策略活动/导入后台表格",
    )
    config["gongbu_archive_dir_path"] = resolve_project_path(
        config.get("gongbu_archive_dir"),
        "workspace/07共补活动/共补原表存档",
    )
    config.setdefault("target_cities", [])
    config.setdefault("calendar_cities", [])
    config.setdefault("cities", {})
    config.setdefault("default", {})
    config.setdefault("prices", {})
    config.setdefault("styles", {})
    config.setdefault("require_confirmed", True)
    return config


def parse_date_range_token(token: str, today: date | None = None) -> tuple[date, date]:
    match = re.search(r"(\d{1,2})\.?(\d{1,2})-(\d{1,2})\.?(\d{1,2})", token)
    if not match:
        raise ValueError(f"无法从日期区间解析起止日期: {token}")
    sm, sd, em, ed = [int(part) for part in match.groups()]
    base = today or date.today()
    year = base.year
    start = date(year, sm, sd)
    end = date(year, em, ed)
    if end < start:
        end = date(year + 1, em, ed)
    return start, end


def compact_date_range(start: date, end: date) -> str:
    return f"{start:%m%d}-{end:%m%d}"


def latest_gongbu_archive_batch(archive_dir: Path) -> dict[str, Any] | None:
    if not archive_dir.exists():
        return None
    candidates: list[dict[str, Any]] = []
    for path in list(archive_dir.glob("*.xlsx")) + list(archive_dir.glob("*.xlsm")):
        if path.name.startswith("."):
            continue
        try:
            start, end = parse_date_range_token(path.name)
        except ValueError:
            continue
        candidates.append({
            "file": path,
            "filename": path.name,
            "start": start,
            "end": end,
            "mtime": path.stat().st_mtime,
        })
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item["start"], item["end"], item["mtime"]))[-1]


def iter_dates(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
