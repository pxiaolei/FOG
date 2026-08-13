#!/usr/bin/env python3
"""Generate or verify the FOG shared Skill index from real directories."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / ".workbuddy" / "skills"
DEFAULT_OUTPUT = ROOT / "SKILLS.md"


@dataclass(frozen=True)
class SkillRecord:
    name: str
    description: str
    display_name: str
    invocation: str
    contract_status: str
    relative_path: str


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _read_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"缺少 YAML frontmatter: {path}")
    parts = text.split("---\n", 2)
    if len(parts) != 3:
        raise ValueError(f"frontmatter 未闭合: {path}")

    values: dict[str, str] = {}
    for line in parts[1].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = _unquote(value)
    if not values.get("name") or not values.get("description"):
        raise ValueError(f"frontmatter 缺少 name/description: {path}")
    return values


def _quoted_yaml_value(text: str, key: str, path: Path) -> str:
    matches = re.findall(rf'^\s*{re.escape(key)}:\s*(.+?)\s*$', text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"openai.yaml 的 {key} 数量应为 1，实际为 {len(matches)}: {path}")
    raw = matches[0].strip()
    if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
        raise ValueError(f"openai.yaml 的 {key} 必须使用双引号: {path}")
    return _unquote(raw)


def _read_openai_yaml(path: Path, skill_name: str) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    implicit = re.findall(
        r"^\s*allow_implicit_invocation:\s*(true|false)\s*$",
        text,
        flags=re.MULTILINE,
    )
    if len(implicit) != 1:
        raise ValueError(
            f"openai.yaml 的 allow_implicit_invocation 数量应为 1，"
            f"实际为 {len(implicit)}: {path}"
        )
    display_name = _quoted_yaml_value(text, "display_name", path)
    _quoted_yaml_value(text, "short_description", path)
    default_prompt = _quoted_yaml_value(text, "default_prompt", path)
    if f"${skill_name}" not in default_prompt:
        raise ValueError(f"openai.yaml 的 default_prompt 必须包含 ${skill_name}: {path}")
    invocation = "可隐式路由" if implicit[0] == "true" else "显式"
    return display_name, invocation


def _validate_execution_contract(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for heading in ("## 执行契约", "### 输入", "### 输出", "### 验收"):
        count = sum(1 for line in text.splitlines() if line.strip() == heading)
        if count != 1:
            raise ValueError(f"{path} 的 {heading} 数量应为 1，实际为 {count}")


def collect_skills() -> list[SkillRecord]:
    records: list[SkillRecord] = []
    seen: set[str] = set()
    for skill_file in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        frontmatter = _read_frontmatter(skill_file)
        name = frontmatter["name"]
        if name in seen:
            raise ValueError(f"Skill 名称重复: {name}")
        seen.add(name)

        openai_yaml = skill_file.parent / "agents" / "openai.yaml"
        is_standard = set(frontmatter) == {"name", "description"} and openai_yaml.is_file()
        if is_standard:
            _validate_execution_contract(skill_file)
            display_name, invocation = _read_openai_yaml(openai_yaml, name)
            contract_status = "标准共享契约"
        else:
            display_name = name
            invocation = "仅显式使用"
            contract_status = "历史保留，未自动同步"

        records.append(
            SkillRecord(
                name=name,
                description=frontmatter["description"],
                display_name=display_name,
                invocation=invocation,
                contract_status=contract_status,
                relative_path=skill_file.relative_to(ROOT).as_posix(),
            )
        )
    return sorted(records, key=lambda item: item.name.casefold())


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def render_index(records: list[SkillRecord]) -> str:
    standard_count = sum(item.contract_status == "标准共享契约" for item in records)
    legacy_count = len(records) - standard_count
    lines = [
        "# FOG 共享 Skill 索引",
        "",
        "> 本文件由 `python3 tools/generate_skill_index.py` 根据共享仓真实目录生成；"
        "不要手工维护 Skill 表。流程和安全边界以各 Skill 的 `SKILL.md` 为准。",
        "",
        f"当前共 {len(records)} 个 Skill：{standard_count} 个标准共享契约，"
        f"{legacy_count} 个历史保留项。",
        "",
        "| Skill | 显示名 | 调用策略 | 状态 | 入口 | 描述 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        lines.append(
            f"| `{_cell(record.name)}` | {_cell(record.display_name)} | "
            f"{_cell(record.invocation)} | {_cell(record.contract_status)} | "
            f"[`SKILL.md`]({_cell(record.relative_path)}) | "
            f"{_cell(record.description)} |"
        )
    lines.extend(
        [
            "",
            "## 校验",
            "",
            "```bash",
            "python3 tools/generate_skill_index.py --check",
            "```",
            "",
            "校验会动态枚举真实目录；标准共享契约还会检查 frontmatter、"
            "`agents/openai.yaml` 和唯一执行契约结构。历史保留项只表示文件仍在，"
            "不表示会随私人源仓自动更新。",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="生成或检查 FOG 共享 Skill 索引")
    parser.add_argument("--check", action="store_true", help="只检查索引是否与真实目录一致")
    parser.add_argument("--stdout", action="store_true", help="输出到 stdout，不写文件")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出路径")
    args = parser.parse_args(argv)

    try:
        records = collect_skills()
        content = render_index(records)
    except (OSError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    if args.stdout:
        print(content, end="")
        return 0
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != content:
            print(f"[FAIL] Skill 索引漂移: {args.output}", file=sys.stderr)
            return 1
        print(f"[PASS] Skill 索引与 {len(records)} 个真实 Skill 一致")
        return 0

    args.output.write_text(content, encoding="utf-8")
    print(f"[PASS] 已生成 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
