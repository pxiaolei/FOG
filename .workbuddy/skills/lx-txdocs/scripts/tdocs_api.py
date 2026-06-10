#!/usr/bin/env python3
"""腾讯文档 OpenAPI 工具入口。

实际实现位于 lxx_share.tdocs_api；此文件只提供 lx-txdocs 内的 CLI 入口。
"""

import sys
from pathlib import Path


def _find_skills_dir() -> Path:
    for p in Path(__file__).resolve().parents:
        if (p / "lxx_share").is_dir():
            return p
    return Path(__file__).resolve().parents[2]


_skills_dir = _find_skills_dir()
if str(_skills_dir) not in sys.path:
    sys.path.insert(0, str(_skills_dir))

from lxx_share.tdocs_api import *  # noqa: F401,F403
from lxx_share.tdocs_api import main  # noqa: E402


if __name__ == "__main__":
    main()
