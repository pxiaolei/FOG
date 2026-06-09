#!/usr/bin/env python3
"""兼容入口：腾讯文档发布已迁移到 lx-txwendang。

保留此文件是为了让旧命令不立即失效。
"""

import runpy
import sys
from pathlib import Path


def _find_skills_dir() -> Path:
    for p in Path(__file__).resolve().parents:
        if (p / "lx-txwendang").is_dir():
            return p
    return Path(__file__).resolve().parents[2]


def main() -> None:
    skills_dir = _find_skills_dir()
    target = skills_dir / "lx-txwendang" / "scripts" / "publish_excel_folder.py"
    if not target.exists():
        raise FileNotFoundError(f"lx-txwendang 发布脚本不存在: {target}")
    sys.argv[0] = str(target)
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
