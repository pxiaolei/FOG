#!/usr/bin/env python3
"""FOG 统一配置初始化入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from connection_check import CheckItem, check_config, has_errors
from init_workspace import init_workspace
from utils import (
    WriteResult,
    find_project_root,
    load_yaml,
    rel,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="lx-init — FOG 项目初始化")
    parser.add_argument(
        "--config",
        default="config/fog_config.yaml",
        help="统一配置路径，默认 config/fog_config.yaml",
    )
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    parser.add_argument("--force", action="store_true", help="允许覆盖已有真实配置，会先备份")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("check", help="检查统一配置")
    init_workspace_parser = subparsers.add_parser("init-workspace", help="创建 workspace 目录")
    write_configs_parser = subparsers.add_parser("write-configs", help="兼容旧命令：不再生成各 Skill config.yaml")
    apply_parser = subparsers.add_parser("apply", help="创建目录并检查 config/fog_config.yaml")

    for subparser in (init_workspace_parser, write_configs_parser, apply_parser):
        subparser.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS, help="只预览，不写文件")
    for subparser in (write_configs_parser, apply_parser):
        subparser.add_argument("--force", action="store_true", default=argparse.SUPPRESS, help="兼容旧参数；当前不会覆盖 per-Skill 配置")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = args.command or "check"

    try:
        project_root = find_project_root()
        config_path = _resolve_config_path(project_root, args.config)
        config = load_yaml(config_path)
    except Exception as exc:
        print(f"❌ 初始化失败: {exc}")
        print("   如首次使用，请先复制 config/fog_config.yaml.example 为 config/fog_config.yaml 并填写。")
        return 1

    if command == "check":
        return run_check(config, project_root)
    if command == "init-workspace":
        results = init_workspace(config, project_root, dry_run=args.dry_run)
        print_results("Workspace 初始化", results, project_root)
        return 0
    if command == "write-configs":
        results = write_skill_configs(config, project_root, dry_run=args.dry_run, force=args.force)
        print_results("Skill 配置分发", results, project_root)
        return 0
    if command == "apply":
        check_status = run_check(config, project_root, exit_on_error=False)
        if check_status != 0:
            print("\n⚠️ 配置存在错误，已停止写入。")
            return check_status
        workspace_results = init_workspace(config, project_root, dry_run=args.dry_run)
        print_results("Workspace 初始化", workspace_results, project_root)
        config_results = write_skill_configs(config, project_root, dry_run=args.dry_run, force=args.force)
        print_results("Skill 配置分发（兼容占位）", config_results, project_root)
        if not args.dry_run:
            write_report(config, project_root, workspace_results + config_results)
        return 0

    print(f"未知命令: {command}")
    return 1


def run_check(config: dict[str, Any], project_root: Path, exit_on_error: bool = True) -> int:
    items = check_config(config, project_root)
    print("配置检查")
    print("=" * 40)
    for item in items:
        print(f"[{item.status}] {item.name}: {item.message}")
    status = 1 if has_errors(items) else 0
    if status and exit_on_error:
        return status
    return status


def write_skill_configs(
    config: dict[str, Any],
    project_root: Path,
    dry_run: bool = False,
    force: bool = False,
) -> list[WriteResult]:
    """兼容旧入口：所有共享 Skill 已改为直接读取 config/fog_config.yaml。"""
    return [
        WriteResult(
            path=project_root / "config" / "fog_config.yaml",
            action="skipped",
            message="所有共享 Skill 直接读取 config/fog_config.yaml，不再生成 assets/config.yaml",
        )
    ]


def write_report(config: dict[str, Any], project_root: Path, results: list[WriteResult]) -> None:
    report_path = project_root / config.get("init", {}).get("report_path", ".lx-init-report.md")
    lines = [
        "# lx-init 初始化报告",
        "",
        "## 写入结果",
        "",
        "| 路径 | 动作 | 说明 |",
        "|------|------|------|",
    ]
    for result in results:
        lines.append(f"| `{rel(result.path, project_root)}` | {result.action} | {result.message} |")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n初始化报告: {rel(report_path, project_root)}")


def print_results(title: str, results: list[WriteResult], project_root: Path) -> None:
    print(f"\n{title}")
    print("=" * 40)
    for result in results:
        print(f"[{result.action}] {rel(result.path, project_root)} - {result.message}")


def _resolve_config_path(project_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return project_root / path


if __name__ == "__main__":
    sys.exit(main())
