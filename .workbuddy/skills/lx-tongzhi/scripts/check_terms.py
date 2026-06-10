#!/usr/bin/env python3
"""Check notice text against lx-tongzhi Markdown term rules."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def find_skill_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "SKILL.md").exists() and candidate.name == "lx-tongzhi":
            return candidate
        nested = candidate / ".workbuddy" / "skills" / "lx-tongzhi"
        if (nested / "SKILL.md").exists():
            return nested
    return Path(__file__).resolve().parents[1]


SKILL_ROOT = find_skill_root()
AUDIENCE_TERMS = {
    "shangjia": SKILL_ROOT / "references" / "banned_terms" / "shangjia.md",
    "siji": SKILL_ROOT / "references" / "banned_terms" / "siji.md",
    "qudao": SKILL_ROOT / "references" / "banned_terms" / "qudao.md",
}


def read_terms(path: Path) -> tuple[list[str], list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"禁词文件不存在: {path}")

    blocked: list[str] = []
    warn: list[str] = []
    section: str | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            title = stripped[3:].strip()
            if title == "禁止出现":
                section = "blocked"
            elif title == "需要人工确认":
                section = "warn"
            else:
                section = None
            continue
        if not stripped.startswith("- "):
            continue
        term = stripped[2:].strip()
        if not term:
            continue
        if section == "blocked":
            blocked.append(term)
        elif section == "warn":
            warn.append(term)

    return blocked, warn


def find_hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term and term in text]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查通知文案中的禁词和风险词。")
    parser.add_argument("--audience", choices=sorted(AUDIENCE_TERMS), required=True, help="通知对象")
    parser.add_argument("--text", help="直接传入待检查文案")
    parser.add_argument("--text-file", help="待检查文案文件")
    parser.add_argument("--terms-file", help="自定义禁词 Markdown 文件；不传时按 audience 读取")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if bool(args.text) == bool(args.text_file):
        print("[FAIL] 必须且只能传入 --text 或 --text-file", file=sys.stderr)
        return 1

    text = args.text if args.text is not None else Path(args.text_file).read_text(encoding="utf-8")
    terms_path = Path(args.terms_file).expanduser().resolve() if args.terms_file else AUDIENCE_TERMS[args.audience]
    blocked_terms, warn_terms = read_terms(terms_path)
    blocked_hits = find_hits(text, blocked_terms)
    warn_hits = find_hits(text, warn_terms)

    if blocked_hits:
        print("[blocked] 命中禁止词: " + "、".join(blocked_hits))
    else:
        print("[ok] 未命中禁止词")

    if warn_hits:
        print("[warning] 命中风险词: " + "、".join(warn_hits))
    else:
        print("[ok] 未命中风险词")

    return 2 if blocked_hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
