"""腾讯文档企业版发布计划模块（单行表头版）。

本模块不直接调用旧版腾讯文档 OpenAPI。日报发布依赖全局
`tencent-saas-docs` skill/MCP；脚本负责生成可执行的发布计划 JSON，
再由 WorkBuddy/Codex 读取计划并用 `tencent-saas-docs` 写入企业版表格。

数据格式：
- 单行表头：品牌 | 城市 | 完单当日值 | 完单环比 | ... | 司机取消率城市同比
- 数值直接可读：量值整数、率值当日值×100、量值变化×100、率值变化保持pp值
- 不需要合并单元格
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

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

from config import (
    ENTERPRISE_ROOT_FOLDER_ID,
    ENTERPRISE_ROOT_FOLDER_URL,
    DEFAULT_TDOCS_TITLE_SUFFIX,
    MISSING_DISPLAY_VALUE,
    METRICS,
    OPERATOR_FOLDER_NAME_TEMPLATE,
    PUBLISH_BACKEND,
    REPORT_TITLE_TEMPLATE,
    SUB_COLUMNS,
)

DAILY_REPORT_TITLE_SUFFIX = DEFAULT_TDOCS_TITLE_SUFFIX
DECIMAL_VOLUME_METRICS = {"tph", "unit_price", "avg_orders_per_driver", "online_duration_hours"}


def _build_spreadsheet_title(operator_name: str) -> str:
    if "{operator}" in REPORT_TITLE_TEMPLATE:
        return REPORT_TITLE_TEMPLATE.format(operator=operator_name)
    return f"{operator_name}-{DAILY_REPORT_TITLE_SUFFIX}"


def _build_operator_folder_name(operator_name: str) -> str:
    if "{operator}" in OPERATOR_FOLDER_NAME_TEMPLATE:
        return OPERATOR_FOLDER_NAME_TEMPLATE.format(operator=operator_name)
    return OPERATOR_FOLDER_NAME_TEMPLATE or operator_name


def _is_missing(val) -> bool:
    if val is None:
        return True
    try:
        return bool(pd.isna(val))
    except TypeError:
        return False


def _sub_column_label(m, sub: str) -> str:
    """列名后缀"""
    if sub == "当日值":
        if m.type == "rate":
            return "当日值(%)"
        return "当日值"
    if m.type == "rate":
        return f"{sub}(pp)"
    else:
        return f"{sub}(%)"


def _fmt_signed(val: float) -> str:
    """带正负号的两位小数格式"""
    if val > 0:
        return f"+{val:.2f}"
    elif val < 0:
        return f"{val:.2f}"
    return "0.00"


def _format_report_data(report_df: pd.DataFrame):
    """
    构建单行表头 + 数据行二维数组。

    列名：量值当日值无后缀，率值当日值(%)，量值变化(%) ，率值变化(pp)
    数值：所有环比/同比带 ± 号两位小数，当日值不带 ±
    """
    if report_df.empty:
        return [], 0

    header = ["品牌", "城市"]
    for m in METRICS:
        for sub in SUB_COLUMNS:
            header.append(f"{m.name}{_sub_column_label(m, sub)}")

    data_rows = [header]

    for _, row in report_df.iterrows():
        r = [str(row["品牌"]), str(row["城市"])]
        for m in METRICS:
            for sub in SUB_COLUMNS:
                col = f"{m.key}_{sub}"
                val = row.get(col)

                if _is_missing(val):
                    r.append(MISSING_DISPLAY_VALUE)
                elif sub == "当日值":
                    if m.type == "volume":
                        if m.key in DECIMAL_VOLUME_METRICS:
                            r.append(round(float(val), 2))
                        else:
                            r.append(int(round(float(val))))
                    else:
                        # 率值当日值 → ×100，两位小数
                        r.append(round(float(val) * 100, 2))
                else:
                    # 环比/同比/城市环比/城市同比 → 全部带 ± 号两位小数
                    pct = round(float(val) * 100, 2)
                    r.append(_fmt_signed(pct))
        data_rows.append(r)

    total_cols = 2 + len(METRICS) * len(SUB_COLUMNS)
    return data_rows, total_cols


def publish_to_tdocs(
    operator_name: str,
    date_label: str,
    report_df: pd.DataFrame,
    folder_id: str = "",
    existing_file_id: Optional[str] = None,
    deep_analysis: str = "",
    dry_run: bool = False,
) -> dict:
    result = {
        "operator": operator_name,
        "file_id": existing_file_id or "",
        "sheet_id": "",
        "url": "",
        "sheet_name": date_label,
        "row_count": len(report_df),
        "dry_run": dry_run,
    }

    if report_df.empty:
        print(f"  [{operator_name}] 无数据，跳过发布")
        result["error"] = "无数据"
        return result

    # 构建数据
    data_2d, total_cols = _format_report_data(report_df)

    # 追加分析文案
    if deep_analysis:
        for line in deep_analysis.split("\n"):
            if line.strip():
                data_2d.append([line.strip()] + [""] * (total_cols - 1))

    result.update({
        "publish_backend": PUBLISH_BACKEND,
        "root_folder_url": ENTERPRISE_ROOT_FOLDER_URL,
        "root_folder_id": ENTERPRISE_ROOT_FOLDER_ID,
        "operator_folder_name": _build_operator_folder_name(operator_name),
        "spreadsheet_title": _build_spreadsheet_title(operator_name),
        "sheet_name": date_label,
        "row_count": len(data_2d),
        "column_count": total_cols,
        "data_rows": data_2d,
        "instructions": [
            "使用全局 tencent-saas-docs skill/MCP。",
            "在 enterprise_root_folder 下按 operator_folder_name 查找运营主体文件夹。",
            "在运营主体文件夹中查找或创建 spreadsheet_title 在线表格。",
            "在目标表格中按 sheet_name 创建或替换同名子表。",
            "用 sheet.batch_update 写入 data_rows。",
        ],
    })

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"  [{operator_name}] {prefix}已生成企业版发布计划: "
          f"{result['spreadsheet_title']} / sheet={date_label}")
    return result


def publish_all(
    operator_reports: dict[str, pd.DataFrame],
    date_label: str,
    deep_analyses: dict[str, str] = None,
    dry_run: bool = False,
    output_dir: str | Path | None = None,
) -> list[dict]:
    if deep_analyses is None:
        deep_analyses = {}

    results = []

    for operator_name, report_df in operator_reports.items():
        result = publish_to_tdocs(
            operator_name=operator_name,
            date_label=date_label,
            report_df=report_df,
            folder_id="",
            existing_file_id=None,
            deep_analysis=deep_analyses.get(operator_name, ""),
            dry_run=dry_run,
        )
        results.append(result)

    if output_dir:
        write_publish_plan(results, date_label, output_dir)

    return results


def write_publish_plan(results: list[dict], date_label: str, output_dir: str | Path) -> Path:
    """写入 tencent-saas-docs 发布计划 JSON，供后续 MCP 发布步骤读取。"""
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"dapanribao_publish_plan_{date_label}.json"
    payload = {
        "schema_version": 1,
        "publish_backend": PUBLISH_BACKEND,
        "enterprise_root_folder_url": ENTERPRISE_ROOT_FOLDER_URL,
        "enterprise_root_folder_id": ENTERPRISE_ROOT_FOLDER_ID,
        "target_rules": {
            "operator_folder_name_template": OPERATOR_FOLDER_NAME_TEMPLATE,
            "report_title_template": REPORT_TITLE_TEMPLATE,
            "sheet_name": date_label,
        },
        "reports": results,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n  发布计划: {path}")
    return path
