#!/usr/bin/env python3
"""兼容入口：个人版腾讯文档发布依赖本机私有 lx-txdocs。

分享给同事的 GitHub 模板不包含 lx-txdocs；线上协作请走
lx-nongfu / lx-txsaasdocs 的企业版流程。
"""

import runpy
import sys
from pathlib import Path


def _find_skills_dir() -> Path:
    for p in Path(__file__).resolve().parents:
        if (p / "lx-txdocs").is_dir():
            return p
    return Path(__file__).resolve().parents[2]


def main() -> None:
    skills_dir = _find_skills_dir()
    target = skills_dir / "lx-txdocs" / "scripts" / "publish_excel_folder.py"
    if not target.exists():
        raise FileNotFoundError(
            f"本机私有 lx-txdocs 发布脚本不存在: {target}；"
            "同事共享流程请使用 lx-nongfu / lx-txsaasdocs"
        )
    sys.argv[0] = str(target)
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
