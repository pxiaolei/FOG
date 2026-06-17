#!/usr/bin/env python3
"""Preview and execute lx-celuehuodong workflows."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import (  # noqa: E402
    compact_date_range,
    iter_dates,
    latest_gongbu_archive_batch,
    load_celuehuodong_config,
    parse_date_range_token,
)
from create_mianyongka import (  # noqa: E402
    calculate_card_periods,
    create_mianyongka_records,
    get_all_city_brands,
    get_brand_card_config,
    get_gongbu_periods,
)
from generate_mianyongka_import import generate_import_files  # noqa: E402
from update_gongbu_activity import get_gongbu_data, update_gongbu_activity_sheet  # noqa: E402
from update_gongbu_calendar import get_gongbu_data as get_calendar_gongbu_data  # noqa: E402
from update_gongbu_calendar import update_city_calendar  # noqa: E402
from lxx_share import DatabaseConnector  # noqa: E402


def get_target_cities(config: dict[str, Any], city_filter: str | None = None) -> list[str]:
    if city_filter:
        return [city_filter]
    return [str(city).strip() for city in config.get("target_cities", []) if str(city).strip()]


def get_calendar_cities(config: dict[str, Any], city_filter: str | None = None) -> list[str]:
    if city_filter:
        return [city_filter]
    configured = config.get("calendar_cities")
    if configured:
        return [str(city).strip() for city in configured if str(city).strip()]
    return get_target_cities(config)


def select_date_range(args: argparse.Namespace, config: dict[str, Any]):
    if args.start and args.end:
        return (
            datetime.strptime(args.start, "%Y-%m-%d").date(),
            datetime.strptime(args.end, "%Y-%m-%d").date(),
            "manual",
            None,
        )
    if args.date_range:
        start, end = parse_date_range_token(args.date_range)
        return start, end, "manual", None
    batch = latest_gongbu_archive_batch(config["gongbu_archive_dir_path"])
    if not batch:
        raise FileNotFoundError(f"未检测到可解析日期的共补原表: {config['gongbu_archive_dir_path']}")
    return batch["start"], batch["end"], "auto", batch


def select_city_brands(config: dict[str, Any], city: str | None = None, brand: str | None = None) -> list[tuple[str, str]]:
    if city and brand:
        return [(city, brand)]
    if city:
        brands = (config.get("cities", {}).get(city, {}) or {}).get("brands", {})
        return [(city, brand_name) for brand_name in brands.keys()]
    return get_all_city_brands(config)


def preview(args: argparse.Namespace, config: dict[str, Any], start_date, end_date, batch):
    workbook = Path(args.file).expanduser() if args.file else config["strategy_workbook_path"]
    cities = get_target_cities(config, args.city)
    calendar_cities = get_calendar_cities(config, args.city)
    city_brands = select_city_brands(config, args.city, args.brand)
    step = args.step

    print("策略活动预览")
    print("=" * 50)
    print(f"目标工作簿: {workbook}")
    print(f"工作簿存在: {workbook.exists()}")
    print(f"日期范围: {start_date} 到 {end_date}")
    if batch:
        print(f"自动识别批次: {batch['filename']}")
    print(f"城市范围: {', '.join(cities) if cities else '未配置'}")
    if step in ("all", "calendar"):
        print(f"日历城市范围: {', '.join(calendar_cities) if calendar_cities else '未配置'}")
    print(f"城市-品牌配置数: {len(city_brands)}")
    print(f"执行步骤: {step}")

    db = DatabaseConnector()
    with db.connect() as conn:
        if step in ("all", "activity"):
            activity_rows = len(get_gongbu_data(conn, cities, start_date, end_date)) if cities else 0
            print(f"[activity] 预计追加共补活动记录: {activity_rows}")

        if step in ("all", "calendar"):
            calendar_rows = 0
            for city in calendar_cities:
                calendar_rows += len(get_calendar_gongbu_data(conn, city, start_date, end_date))
            print(f"[calendar] 预计写入日历时段记录: {calendar_rows}")

        if step in ("all", "card"):
            estimated_cards = 0
            for city, brand in city_brands:
                card_configs = get_brand_card_config(config, city, brand)
                for day in iter_dates(start_date, end_date):
                    gongbu_periods, is_isolated, quick_gongbu_periods = get_gongbu_periods(conn, city, day)
                    for card_config in card_configs.values():
                        source_periods = quick_gongbu_periods if card_config.get("k_only") and quick_gongbu_periods else gongbu_periods
                        if calculate_card_periods(card_config, source_periods, is_isolated):
                            estimated_cards += 1
            print(f"[card] 预计生成免佣卡记录: {estimated_cards}")

    if step == "export":
        date_range = args.date_range or compact_date_range(start_date, end_date)
        print(f"[export] 后台导入日期区间: {date_range}")
        print(f"[export] 输出目录: {config['import_output_dir_path']}")


def execute(args: argparse.Namespace, config: dict[str, Any], start_date, end_date) -> None:
    workbook = Path(args.file).expanduser() if args.file else config["strategy_workbook_path"]
    cities = get_target_cities(config, args.city)
    calendar_cities = get_calendar_cities(config, args.city)
    step = args.step

    if not workbook.exists():
        raise FileNotFoundError(f"策略活动表不存在: {workbook}")

    if step in ("all", "activity"):
        count = update_gongbu_activity_sheet(workbook, start_date, end_date, cities)
        print(f"[activity] 已追加记录: {count}")

    if step in ("all", "card"):
        city_brands = select_city_brands(config, args.city, args.brand)
        total = 0
        for city, brand in city_brands:
            records = create_mianyongka_records(workbook, city, brand, start_date, end_date, config=config)
            print(f"[card] {city} / {brand}: {len(records)}")
            total += len(records)
        print(f"[card] 已生成免佣卡记录: {total}")

    if step in ("all", "calendar"):
        total = 0
        for city in calendar_cities:
            records = update_city_calendar(workbook, city, start_date, end_date)
            print(f"[calendar] {city}: {len(records)}")
            total += len(records)
        print(f"[calendar] 已写入日历时段记录: {total}")

    if step == "export":
        date_range = args.date_range or compact_date_range(start_date, end_date)
        files = generate_import_files(
            date_range=date_range,
            source_file=workbook,
            output_dir=config["import_output_dir_path"],
        )
        print(f"[export] 已生成后台导入文件: {len(files)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="策略活动表处理入口")
    parser.add_argument("--file", help="策略活动表 .xlsm 路径；默认读取配置")
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--date-range", help="紧凑日期区间，如 0615-0617")
    parser.add_argument("--auto", action="store_true", help="从共补原表存档自动识别最新日期范围")
    parser.add_argument("--step", choices=["all", "activity", "card", "calendar", "export"], default="all")
    parser.add_argument("--city", help="指定城市")
    parser.add_argument("--brand", help="指定品牌，仅 card 步骤使用")
    parser.add_argument("--config", help="额外配置文件路径")
    parser.add_argument("--confirmed", action="store_true", help="确认写入 Excel 或生成文件")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写入；默认行为")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.confirmed and args.dry_run:
        parser.error("--confirmed 和 --dry-run 不能同时使用")
    if bool(args.start) != bool(args.end):
        parser.error("--start 和 --end 必须同时提供")

    config = load_celuehuodong_config(args.config)
    start_date, end_date, _, batch = select_date_range(args, config)

    preview(args, config, start_date, end_date, batch)
    if not args.confirmed:
        print("\n未写入。确认无误后追加 --confirmed 执行。")
        return 0

    print("\n开始执行写入...")
    execute(args, config, start_date, end_date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
