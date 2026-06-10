#!/usr/bin/env python3
"""FOG local project utility.

This is the non-Skill entrypoint for initialization, config checks, and
fog_config.yaml migration. Skills read config/fog_config.yaml directly.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "config" / "fog_config.yaml.example").exists() and (candidate / ".workbuddy").is_dir():
            return candidate
    return Path.cwd().resolve()


PROJECT_ROOT = find_project_root()
CONFIG_PATH = PROJECT_ROOT / "config" / "fog_config.yaml"
EXAMPLE_PATH = PROJECT_ROOT / "config" / "fog_config.yaml.example"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def merge_missing(base: Any, defaults: Any) -> Any:
    if isinstance(base, dict) and isinstance(defaults, dict):
        merged = dict(base)
        for key, value in defaults.items():
            merged[key] = merge_missing(merged[key], value) if key in merged else value
        return merged
    return base


def ensure_config() -> bool:
    """Ensure config/fog_config.yaml exists. Returns True when created."""
    if CONFIG_PATH.exists():
        return False
    if not EXAMPLE_PATH.exists():
        raise FileNotFoundError(f"统一配置模板不存在: {EXAMPLE_PATH}")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EXAMPLE_PATH, CONFIG_PATH)
    try:
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass
    return True


def resolve_path(value: str | None, default: str = "") -> Path:
    raw = value or default
    path = Path(str(raw)).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def workspace_dirs(config: dict[str, Any]) -> list[Path]:
    dirs = [
        resolve_path("workspace/01主体拆表"),
        resolve_path("workspace/01主体拆表/输入"),
        resolve_path("workspace/01主体拆表/输出"),
        resolve_path("workspace/01主体拆表/原表存档"),
        resolve_path("workspace/01主体拆表/处理日志"),
        resolve_path("workspace/03数据报表/日报"),
        resolve_path("workspace/03数据报表/周报"),
        resolve_path("workspace/03数据报表/月报"),
        resolve_path("workspace/03数据报表/其他"),
        resolve_path("workspace/04数据分析"),
        resolve_path("workspace/10表格同步"),
        resolve_path("workspace/10表格同步/待处理"),
        resolve_path("workspace/10表格同步/输出"),
        resolve_path("workspace/10表格同步/处理日志"),
        resolve_path("workspace/12农夫协作"),
        resolve_path("workspace/12农夫协作/待处理"),
        resolve_path("workspace/12农夫协作/输出"),
        resolve_path("workspace/12农夫协作/处理日志"),
    ]

    zhutichaibiao = config.get("lx_zhutichaibiao", {})
    if isinstance(zhutichaibiao, dict):
        base = resolve_path(zhutichaibiao.get("work_dir"), "workspace/01主体拆表")
        dirs.extend([base, base / "输入", base / "输出", base / "原表存档", base / "处理日志"])

    dapanribao = config.get("lx_dapanribao", {})
    if isinstance(dapanribao, dict):
        dirs.append(resolve_path(dapanribao.get("output_dir"), "workspace/03数据报表/日报"))

    haibao = config.get("lx_haibao", {})
    if isinstance(haibao, dict):
        dirs.append(resolve_path(haibao.get("output_dir"), "workspace/09端外海报图/产出图"))
        dirs.append(resolve_path(haibao.get("meta_dir"), "workspace/09端外海报图/元数据"))
        dirs.append(resolve_path(haibao.get("tmp_dir"), "workspace/09端外海报图/临时图"))

    nongfu = config.get("lx_nongfu", {})
    if isinstance(nongfu, dict):
        base = resolve_path(nongfu.get("workspace_dir"), "workspace/12农夫协作")
        dirs.extend([base, base / "待处理", base / "输出", base / "处理日志"])

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in dirs:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def cmd_init(args: argparse.Namespace) -> int:
    created = ensure_config()
    config = load_yaml(CONFIG_PATH)
    for path in workspace_dirs(config):
        if args.dry_run:
            print(f"[dry-run] create {path}")
            continue
        path.mkdir(parents=True, exist_ok=True)
        (path / ".gitkeep").touch(exist_ok=True)
        print(f"[ok] {path}")
    if created:
        print("已创建 config/fog_config.yaml，请填写个人账号、token、目录等配置后运行 check。")
        return 1
    return 0


def cmd_migrate_config(args: argparse.Namespace) -> int:
    created = ensure_config()
    if created:
        print("已创建 config/fog_config.yaml，请填写个人配置。")
        return 1
    current = load_yaml(CONFIG_PATH)
    defaults = load_yaml(EXAMPLE_PATH)
    migrated = merge_missing(current, defaults)
    if migrated == current:
        print("config/fog_config.yaml 已包含当前模板需要的配置键。")
        return 0
    if args.dry_run:
        print("dry-run: 将向 config/fog_config.yaml 补充模板新增配置键，不覆盖已有值。")
        return 0
    backup = CONFIG_PATH.with_suffix(".yaml.bak")
    shutil.copy2(CONFIG_PATH, backup)
    save_yaml(CONFIG_PATH, migrated)
    print(f"已补充新增配置键，旧配置备份到: {backup}")
    return 0


def add_check(items: list[tuple[str, str, str]], status: str, name: str, message: str) -> None:
    items.append((status, name, message))


def required(items: list[tuple[str, str, str]], name: str, value: Any, severity: str = "warning") -> None:
    if value:
        add_check(items, "ok", name, "已配置")
    else:
        add_check(items, severity, name, "未配置")


def cmd_check(_: argparse.Namespace) -> int:
    if not CONFIG_PATH.exists():
        print(f"[error] config.fog_config: 不存在 {CONFIG_PATH}")
        return 1

    config = load_yaml(CONFIG_PATH)
    enabled = config.get("enabled_skills", {})
    if not isinstance(enabled, dict):
        enabled = {}

    items: list[tuple[str, str, str]] = []

    if enabled.get("lx_shujuku"):
        api = (config.get("lx_shujuku", {}) or {}).get("api", {})
        required(items, "lx_shujuku.api.base_url", api.get("base_url"), "error")
        required(items, "lx_shujuku.api.username", api.get("username"), "error")
        required(items, "lx_shujuku.api.password", api.get("password"), "error")

    if enabled.get("lx_zhutichaibiao"):
        zhutichaibiao = config.get("lx_zhutichaibiao", {}) or {}
        required(items, "lx_zhutichaibiao.work_dir", zhutichaibiao.get("work_dir"), "error")
        if not zhutichaibiao.get("default_persons"):
            add_check(items, "warning", "lx_zhutichaibiao.default_persons", "未配置默认对接人")

    if enabled.get("lx_txdocs"):
        txdocs = config.get("lx_txdocs", {}) or {}
        legacy_txwendang = config.get("lx_txwendang", {}) or {}
        tdocs = txdocs.get("tdocs") if isinstance(txdocs, dict) else {}
        if not isinstance(tdocs, dict) or not tdocs:
            tdocs = legacy_txwendang.get("tdocs", {}) if isinstance(legacy_txwendang, dict) else {}
        openapi = tdocs.get("openapi", {}) if isinstance(tdocs, dict) else {}
        required(items, "lx_txdocs.tdocs.root_folder_id", tdocs.get("root_folder_id") if isinstance(tdocs, dict) else "")
        required(items, "lx_txdocs.tdocs.openapi.client_id", openapi.get("client_id"))
        required(items, "lx_txdocs.tdocs.openapi.access_token", openapi.get("access_token"))
        required(items, "lx_txdocs.tdocs.openapi.open_id", openapi.get("open_id"))

    if enabled.get("lx_txsaasdocs") or enabled.get("lx_dapanribao"):
        txsaasdocs = config.get("lx_txsaasdocs", {}) or {}
        api = txsaasdocs.get("api", {}) if isinstance(txsaasdocs, dict) else {}
        required(items, "lx_txsaasdocs.api.base_url", api.get("base_url"))
        required(items, "lx_txsaasdocs.api.token_endpoint", api.get("token_endpoint"))
        required(items, "lx_txsaasdocs.api.client_id", api.get("client_id"))
        required(items, "lx_txsaasdocs.api.client_secret", api.get("client_secret"))

    if enabled.get("lx_haibao"):
        image_api = ((config.get("lx_haibao", {}) or {}).get("image_api", {}) or {})
        primary = str(image_api.get("provider_primary") or "volcengine_seedream")
        providers = [primary, str(image_api.get("provider_fallback") or "")]
        configured = False
        for provider in providers:
            provider_config = image_api.get(provider, {}) if provider else {}
            if isinstance(provider_config, dict) and provider_config.get("api_key"):
                configured = True
        if os.environ.get("ARK_API_KEY") or os.environ.get("APIMART_API_KEY") or os.environ.get("OPENAI_API_KEY"):
            configured = True
        if configured:
            add_check(items, "ok", "lx_haibao.image_api", "至少一个 provider 已配置 API Key")
        else:
            add_check(items, "warning", "lx_haibao.image_api", "未配置图片 API Key；海报生成会不可用")

    if enabled.get("lx_nongfu"):
        nongfu = config.get("lx_nongfu", {}) or {}
        required(items, "lx_nongfu.workspace_dir", nongfu.get("workspace_dir"), "error")
        if not nongfu.get("default_contact_persons"):
            add_check(items, "warning", "lx_nongfu.default_contact_persons", "未配置默认对接人")
        large_doc = nongfu.get("large_doc", {}) if isinstance(nongfu, dict) else {}
        keys = large_doc.get("required_key_columns", []) if isinstance(large_doc, dict) else []
        if "品牌" in keys and "城市" in keys:
            add_check(items, "ok", "lx_nongfu.large_doc.required_key_columns", "已配置品牌+城市定位键")
        else:
            add_check(items, "error", "lx_nongfu.large_doc.required_key_columns", "必须包含 品牌 和 城市")
        operator_doc = nongfu.get("operator_doc", {}) if isinstance(nongfu, dict) else {}
        required(items, "lx_nongfu.operator_doc.target_table_name_template", operator_doc.get("target_table_name_template"), "error")
        sync = nongfu.get("sync", {}) if isinstance(nongfu, dict) else {}
        if sync.get("require_brand_city_match") is False:
            add_check(items, "error", "lx_nongfu.sync.require_brand_city_match", "必须开启品牌+城市匹配")
        else:
            add_check(items, "ok", "lx_nongfu.sync.require_brand_city_match", "已开启")

    personal_config_path = PROJECT_ROOT / "config" / "personal_config.yaml"
    for path in [CONFIG_PATH, personal_config_path]:
        try:
            mode = path.stat().st_mode & 0o777
        except OSError:
            continue
        if mode & 0o077:
            add_check(items, "warning", f"permissions.{path.relative_to(PROJECT_ROOT)}", f"权限 {mode:o} 过宽，建议仅本人可读")
        else:
            add_check(items, "ok", f"permissions.{path.relative_to(PROJECT_ROOT)}", f"权限 {mode:o}")

    print("FOG 配置检查")
    print("=" * 40)
    for status, name, message in items:
        print(f"[{status}] {name}: {message}")
    return 1 if any(status == "error" for status, _, _ in items) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FOG 本地初始化与配置工具")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="创建配置文件和 workspace 目录")
    init_parser.add_argument("--dry-run", action="store_true", help="只预览，不写入")

    check_parser = subparsers.add_parser("check", help="检查 config/fog_config.yaml")
    check_parser.set_defaults(func=cmd_check)

    migrate_parser = subparsers.add_parser("migrate-config", help="补充 fog_config.yaml 新增配置键")
    migrate_parser.add_argument("--dry-run", action="store_true", help="只预览，不写入")

    init_parser.set_defaults(func=cmd_init)
    migrate_parser.set_defaults(func=cmd_migrate_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
