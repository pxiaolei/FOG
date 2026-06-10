#!/usr/bin/env python3
"""
日报格式后处理：合并表头单元格 + 数字格式。

通过腾讯文档 Open API 批量操作。
合并单元格需要通过 V2 API 逐个调用（batchUpdate V3 不支持 mergeCells）。
数字格式直接内嵌在写入数据中（腾讯文档自动识别数值类型），无需额外设置。
"""

import sys
import requests
import time
from datetime import datetime, timedelta
from pathlib import Path

# 确保 lxx_share 可 import
def _find_skills_dir():
    from pathlib import Path
    for p in Path(__file__).resolve().parents:
        if (p / "lxx_share").is_dir():
            return p
    return Path(__file__).resolve().parents[2]

_skills_dir = _find_skills_dir()
if str(_skills_dir) not in sys.path:
    sys.path.insert(0, str(_skills_dir))

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from lxx_share.tdocs_api import TdocsClient
from config import METRICS, load_dailyreport_cache

# 旧个人版腾讯文档格式化入口；同事共享发布走 lx-txsaasdocs 企业版流程。
_tdocs_client = TdocsClient()
HEADERS = {
    'Access-Token': _tdocs_client.access_token,
    'Client-Id': _tdocs_client.client_id,
    'Open-Id': _tdocs_client.open_id,
}

# 构建合并列表
MERGES = [
    {'sr': 0, 'er': 1, 'sc': 0, 'ec': 0},  # 品牌
    {'sr': 0, 'er': 1, 'sc': 1, 'ec': 1},  # 城市
]
for i in range(len(METRICS)):
    sc = 2 + i * 5
    MERGES.append({'sr': 0, 'er': 0, 'sc': sc, 'ec': sc + 4})


def _default_sheet_title() -> str:
    """默认 Sheet 标题为昨日日期（MMDD 格式），与日报发布一致。"""
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime("%m%d")


def get_sheet_id(fid: str, title: str = None) -> str:
    """获取指定标题的 sheet_id"""
    if title is None:
        title = _default_sheet_title()
    resp = requests.get(
        f'https://docs.qq.com/openapi/spreadsheet/v3/files/{fid}',
        headers=HEADERS, timeout=15
    )
    if resp.status_code != 200:
        raise RuntimeError(f"获取 sheet 信息失败: {resp.status_code}")
    props = resp.json().get('properties', [])
    for p in props:
        if p.get('title') == title:
            return p['sheetId']
    raise RuntimeError(f"未找到 sheet: {title}")


def merge_cells(fid: str, sid: str, merges: list):
    """通过 Open API 逐个合并单元格（使用专门的 merge API endpoint）"""
    for m in merges:
        url = (f'https://docs.qq.com/openapi/spreadsheet/v3/files/{fid}/'
               f'sheets/{sid}/merge')
        body = {
            "range": {
                "startRowIndex": m['sr'],
                "endRowIndex": m['er'] + 1,
                "startColumnIndex": m['sc'],
                "endColumnIndex": m['ec'] + 1,
            },
            "mergeType": "MERGE_ALL",
        }
        resp = requests.post(url, headers=HEADERS, json=body, timeout=30)
        if resp.status_code == 404:
            pass
        elif resp.status_code != 200:
            print(f"  合并失败 sr={m['sr']},sc={m['sc']}: {resp.status_code} {resp.text[:100]}")
        time.sleep(0.5)


def process_entity(name: str, fid: str, sheet_title: str = None):
    """处理单个实体的格式"""
    if sheet_title is None:
        sheet_title = _default_sheet_title()
    print(f"\n{'='*40}")
    print(f"{name}: {fid}")
    sid = get_sheet_id(fid, sheet_title)
    print(f"  sheet_id: {sid}")

    # 合并单元格
    print(f"  合并 {len(MERGES)} 个区域...")
    merge_cells(fid, sid, MERGES)
    print(f"  合并完成")

    print(f"  ✅ {name} 格式处理完成")


def main():
    cache = load_dailyreport_cache()
    if not cache:
        print("缓存为空，请先运行 main.py 发布日报")
        sys.exit(1)

    for name, info in cache.items():
        fid = info['file_id']
        try:
            process_entity(name, fid)
        except Exception as e:
            print(f"  ❌ {name}: {e}")


if __name__ == '__main__':
    main()
