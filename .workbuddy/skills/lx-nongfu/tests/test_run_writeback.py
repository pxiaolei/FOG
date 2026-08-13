import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from run_split_publish import TargetWorkbook  # noqa: E402
from run_writeback import (  # noqa: E402
    Change,
    build_table,
    build_writeback_plan,
    group_contiguous_changes,
    parse_operator_args,
    parse_update_columns,
    verify_changes,
)


TARGET = TargetWorkbook(operator="测试主体", folder_token="", spreadsheet_token="token", url="")
BRAND_FIELDS = ["品牌名称", "品牌"]
CITY_FIELDS = ["城市"]


class WritebackConfigTests(unittest.TestCase):
    def test_update_columns_cli_takes_precedence_and_dedupes(self):
        self.assertEqual(parse_update_columns("字段A,字段B,字段A", ["旧字段"]), ["字段A", "字段B"])

    def test_update_columns_can_fallback_to_config(self):
        self.assertEqual(parse_update_columns("", ["字段A", "字段B"]), ["字段A", "字段B"])

    def test_update_columns_requires_explicit_fields_when_config_empty(self):
        with self.assertRaisesRegex(Exception, "缺少回填字段"):
            parse_update_columns("", [])

    def test_operator_args_accept_repeated_and_comma_values(self):
        self.assertEqual(parse_operator_args(["A,B", "A", "C"]), ["A", "B", "C"])


class WritebackPlanTests(unittest.TestCase):
    def build(self, operator, rows):
        return build_table(
            operator=operator,
            target=TARGET,
            sheet_id="sid",
            sheet_name="活动",
            rows=rows,
            brand_fields=BRAND_FIELDS,
            city_fields=CITY_FIELDS,
            update_columns=["首页侧边栏bannerID", "短信ID"],
            header_row=2,
            max_header_scan_rows=10,
        )

    def test_plan_changes_by_brand_city(self):
        master = self.build(
            "MASTER",
            [
                ["配置SOP"],
                ["品牌名称", "城市", "首页侧边栏bannerID", "短信ID"],
                ["方舟行", "武汉市", "", ""],
            ],
        )
        source = self.build(
            "方舟行武汉",
            [
                ["配置SOP"],
                ["品牌名称", "城市", "首页侧边栏bannerID", "短信ID"],
                ["方舟行", "武汉市", "123", "456"],
            ],
        )

        plan = build_writeback_plan(master, [source], ["首页侧边栏bannerID", "短信ID"])

        self.assertEqual(len(plan["changes"]), 2)
        self.assertEqual(plan["changes"][0].cell, "C3")
        self.assertEqual(plan["changes"][1].cell, "D3")

    def test_empty_source_values_do_not_overwrite_by_default(self):
        master = self.build(
            "MASTER",
            [
                ["配置SOP"],
                ["品牌名称", "城市", "首页侧边栏bannerID", "短信ID"],
                ["方舟行", "武汉市", "old", ""],
            ],
        )
        source = self.build(
            "方舟行武汉",
            [
                ["配置SOP"],
                ["品牌名称", "城市", "首页侧边栏bannerID", "短信ID"],
                ["方舟行", "武汉市", "", "456"],
            ],
        )

        plan = build_writeback_plan(master, [source], ["首页侧边栏bannerID", "短信ID"])

        self.assertEqual(len(plan["changes"]), 1)
        self.assertEqual(plan["changes"][0].column, "短信ID")
        self.assertEqual(len(plan["skipped_empty"]), 1)

    def test_duplicates_block_plan(self):
        master = self.build(
            "MASTER",
            [
                ["配置SOP"],
                ["品牌名称", "城市", "首页侧边栏bannerID", "短信ID"],
                ["方舟行", "武汉市", "", ""],
                ["方舟行", "武汉市", "", ""],
            ],
        )
        source = self.build(
            "方舟行武汉",
            [
                ["配置SOP"],
                ["品牌名称", "城市", "首页侧边栏bannerID", "短信ID"],
                ["方舟行", "武汉市", "123", "456"],
            ],
        )

        plan = build_writeback_plan(master, [source], ["首页侧边栏bannerID", "短信ID"])

        self.assertEqual(len(plan["master_duplicates"]), 1)

    def test_group_contiguous_changes(self):
        master = self.build(
            "MASTER",
            [
                ["配置SOP"],
                ["品牌名称", "城市", "首页侧边栏bannerID", "短信ID"],
                ["方舟行", "武汉市", "", ""],
            ],
        )
        source = self.build(
            "方舟行武汉",
            [
                ["配置SOP"],
                ["品牌名称", "城市", "首页侧边栏bannerID", "短信ID"],
                ["方舟行", "武汉市", "123", "456"],
            ],
        )
        plan = build_writeback_plan(master, [source], ["首页侧边栏bannerID", "短信ID"])

        groups = group_contiguous_changes(plan["changes"])

        self.assertEqual(len(groups), 1)
        self.assertEqual([item.cell for item in groups[0]], ["C3", "D3"])


class WritebackReadbackTests(unittest.TestCase):
    def change(self):
        return Change(
            operator="测试主体",
            brand="方舟行",
            city="武汉市",
            column="首页侧边栏bannerID",
            row_number=3,
            column_number=3,
            cell="C3",
            old_value="",
            new_value="123",
        )

    def test_verify_changes_accepts_value_only_with_stable_brand_city_key(self):
        class FakeCli:
            def sheets(self, args):
                self.requested_range = args[args.index("--range") + 1]
                if self.requested_range == "C3":
                    return {"data": {"annotated_csv": "123"}}
                return {"data": {"annotated_csv": "方舟行,武汉市,123"}}

        checks = verify_changes(FakeCli(), "master-token", "sheet-id", [self.change()])

        self.assertTrue(checks[0]["ok"])
        self.assertEqual(checks[0]["actual_brand"], "方舟行")
        self.assertEqual(checks[0]["actual_city"], "武汉市")

    def test_verify_changes_rejects_brand_or_city_row_drift(self):
        for label, row in (
            ("brand", "错误品牌,武汉市,123"),
            ("city", "方舟行,错误城市,123"),
        ):
            with self.subTest(label=label):
                class FakeCli:
                    def sheets(self, args):
                        requested_range = args[args.index("--range") + 1]
                        if requested_range == "C3":
                            return {"data": {"annotated_csv": "123"}}
                        return {"data": {"annotated_csv": row}}

                checks = verify_changes(FakeCli(), "master-token", "sheet-id", [self.change()])

                self.assertFalse(checks[0]["ok"])


if __name__ == "__main__":
    unittest.main()
