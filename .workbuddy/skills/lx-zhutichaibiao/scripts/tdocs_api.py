#!/usr/bin/env python3
"""
腾讯文档 Open API V3 封装模块（重导出薄壳）。

实际代码已迁移至 lxx_share.tdocs_api，此处保留向后兼容。
"""

import sys
from pathlib import Path

_skills_dir = Path(__file__).resolve().parents[2]
if str(_skills_dir) not in sys.path:
    sys.path.insert(0, str(_skills_dir))

from lxx_share.tdocs_api import *  # noqa: F401,F403
from lxx_share.tdocs_api import (  # noqa: F401 — 显式导出供 IDE 识别
    TdocsClient,
    add_sheet,
    write_range,
    write_range_auto,
    create_spreadsheet,
    delete_sheet,
    get_sheet_ids,
    oauth_flow,
    setup_simple,
    CONFIG_PATH,
)
