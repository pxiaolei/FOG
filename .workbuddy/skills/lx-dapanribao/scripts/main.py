"""
运营日报 — 编排入口（飞书普通表格发布计划）

用法:
    # 为默认对接人的所有运营主体生成日报
    python3 main.py

    # 指定对接人
    python3 main.py --person 雷维亮

    # 指定日期
    python3 main.py --person 雷维亮 --date 2026-05-16

    # 指定运营主体
    python3 main.py --operator 江豚出行

    # 预览不发布
    python3 main.py --person 雷维亮 --dry-run
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 确保可 import lxx_share 和同目录模块
_scripts_dir = Path(__file__).resolve().parent
_skills_dir = _scripts_dir.parent.parent  # .workbuddy/skills/
for d in [str(_scripts_dir), str(_skills_dir)]:
    if d not in sys.path:
        sys.path.insert(0, d)

def yesterday_str() -> str:
    """默认日期：昨天（今天的数据可能未入库）"""
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def date_label(date_str: str) -> str:
    """2026-06-01 -> 0601"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%m%d")


def main():
    parser = argparse.ArgumentParser(
        description="运营日报生成工具（飞书普通表格发布计划）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 main.py                          # 为默认对接人生成今日日报
  python3 main.py --person 雷维亮             # 为雷维亮生成今日日报
  python3 main.py --operator 江豚出行       # 为江豚出行生成
  python3 main.py --person 雷维亮 --dry-run   # 预览不发布
  python3 main.py --date 2026-05-15        # 指定日期
        """,
    )
    parser.add_argument("--person", default=None,
                        help="对接人名称（默认读取配置 DEFAULT_PERSON）")
    parser.add_argument("--operator", default=None,
                        help="运营主体名称（指定后只生成该主体）")
    parser.add_argument("--date", default=None,
                        help="日期 YYYY-MM-DD（默认: 昨天）")
    parser.add_argument("--dry-run", action="store_true",
                        help="预览模式：只输出摘要不发布")
    parser.add_argument("--output-dir", default=None,
                        help="本地输出目录（默认读取配置 DEFAULT_OUTPUT_DIR）")
    args = parser.parse_args()

    from config import DEFAULT_PERSON, DEFAULT_OUTPUT_DIR
    from data_loader import (
        load_city_benchmark_data,
        load_data_for_operator,
        get_operators_for_person,
        get_brand_city_for_operator,
    )
    from report_builder import build_report, format_report_df
    from anomaly_detector import (
        deep_analyze_top_anomalies,
        detect_anomalies,
        format_anomaly_summary,
        get_anomaly_cell_map,
    )
    from feishu_publisher import publish_all

    person = args.person or DEFAULT_PERSON
    output_dir = args.output_dir or DEFAULT_OUTPUT_DIR
    today = args.date or yesterday_str()
    label = date_label(today)

    if not person and not args.operator:
        print("❌ 未指定对接人。请传 --person，或在 config/fog_config.yaml 的 lx_dapanribao.default_person 中配置。")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  运营日报 — {today}（{label}）")
    print(f"  对接人: {person or '-'}")
    print(f"{'='*60}\n")

    # 确定运营主体列表
    if args.operator:
        operators = [args.operator]
    else:
        operators = get_operators_for_person(person)
        if not operators:
            print(f"❌ 对接人 '{person}' 在码表中无运营主体")
            sys.exit(1)
        print(f"对接人 {person} 负责 {len(operators)} 个运营主体:")
        for op in operators:
            brands, cities, pairs = get_brand_city_for_operator(op)
            print(f"  - {op}: {len(brands)} 品牌 x {len(cities)} 城市 = {len(pairs)} 组合")

    # 收集各主体日报数据
    operator_reports = {}
    deep_analyses = {}
    cell_maps = {}

    for operator in operators:
        print(f"\n{'─'*40}")
        print(f"[{operator}] 加载数据...")

        df_raw = load_data_for_operator(operator, today)
        if df_raw.empty:
            print(f"  ⚠️ {operator}: 无数据，跳过")
            continue

        print(f"  原始数据: {len(df_raw)} 行")

        # 加载城市全品牌数据（用于城市基准）
        _, cities, _ = get_brand_city_for_operator(operator)
        df_city = load_city_benchmark_data(cities, today)

        # 构建日报
        report_df_full, city_benchmark = build_report(df_raw, df_city)
        if report_df_full.empty:
            print(f"  ⚠️ {operator}: 日报构建为空，跳过")
            continue

        report_df = format_report_df(report_df_full)
        print(f"  日报: {len(report_df)} 行 x {len(report_df.columns)} 列")

        # 异动检测
        anomalies = detect_anomalies(report_df_full)
        anomaly_summary = format_anomaly_summary(anomalies)
        cell_map = get_anomaly_cell_map(anomalies, report_df)

        neg_count = sum(1 for a in anomalies if a.direction == "negative")
        pos_count = sum(1 for a in anomalies if a.direction == "positive")
        print(f"  异动: {len(anomalies)} 个（⚠️{neg_count} ✅{pos_count}）")

        # 深度分析
        deep = ""
        if anomalies and not args.dry_run:
            deep = deep_analyze_top_anomalies(anomalies, today)

        operator_reports[operator] = report_df
        deep_analyses[operator] = deep
        cell_maps[operator] = cell_map

        if args.dry_run:
            if anomaly_summary:
                print(f"\n  ── 预览 ──")
                print(f"  {anomaly_summary}")

    # 生成飞书普通表格发布计划
    if not args.dry_run and operator_reports:
        print(f"\n{'='*60}")
        print(f"  生成飞书普通表格发布计划")
        print(f"{'='*60}\n")

        results = publish_all(
            operator_reports, label,
            deep_analyses=deep_analyses,
            dry_run=False,
            output_dir=output_dir,
        )
        for r in results:
            if r.get("error"):
                print(f"  ❌ {r['operator']}: {r['error']}")
            else:
                print(f"  ✅ {r['operator']}: "
                      f"{r['spreadsheet_title']} / "
                      f"sheet={r['sheet_name']}, "
                      f"{r['row_count']} 行")

    elif args.dry_run and operator_reports:
        print(f"\n{'='*60}")
        print(f"  [DRY RUN] 预览完成，未实际发布")
        print(f"{'='*60}")
        publish_all(operator_reports, label, dry_run=True, output_dir=output_dir)

    print(f"\n{'='*60}")
    print(f"  完成")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
