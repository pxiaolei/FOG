import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from run_split_publish import (  # noqa: E402
    NongfuError,
    OperatorPublish,
    SourceSheet,
    TargetWorkbook,
    auto_header_row,
    col_to_a1,
    extract_folder_token,
    extract_sheet_token,
    group_rows_by_operator,
    normalize_color,
    parse_annotated_csv,
    read_header_format,
    refresh_existing_header_format,
    rows_to_csv,
    sanitize_cell_for_set,
    write_and_verify,
)


class FeishuParsingTests(unittest.TestCase):
    def test_extract_tokens_from_urls(self):
        self.assertEqual(
            extract_sheet_token("https://x.feishu.cn/sheets/AbCd123?sheet=abc"),
            "AbCd123",
        )
        self.assertEqual(
            extract_folder_token("https://x.feishu.cn/drive/folder/Fld123?x=1"),
            "Fld123",
        )
        self.assertEqual(extract_sheet_token("bareToken"), "bareToken")

    def test_parse_annotated_csv_keeps_csv_semantics(self):
        text = '[row=1] 品牌,城市\n[row=2] "A,品牌",杭州市'
        self.assertEqual(parse_annotated_csv(text), [["品牌", "城市"], ["A,品牌", "杭州市"]])

    def test_rows_to_csv_round_trips_fixed_columns(self):
        text = rows_to_csv([["品牌", "城市"], ["A"]], column_count=3)
        self.assertEqual(parse_annotated_csv(text), [["品牌", "城市", ""], ["A", "", ""]])

    def test_col_to_a1(self):
        self.assertEqual(col_to_a1(1), "A")
        self.assertEqual(col_to_a1(26), "Z")
        self.assertEqual(col_to_a1(27), "AA")


class SplitLogicTests(unittest.TestCase):
    def test_auto_header_row_detects_brand_city(self):
        rows = [["配置SOP"], ["商家名单"], ["品牌名称", "城市", "辅助列"]]
        self.assertEqual(auto_header_row(rows, ["品牌名称"], ["城市"], 10), 3)

    def test_group_rows_by_operator_exact_brand_city(self):
        rows = [
            ["配置SOP"],
            ["品牌名称", "城市", "辅助列"],
            ["A", "杭州市", "A杭州市"],
            ["B", "上海市", "B上海市"],
        ]
        mapping = {("A", "杭州市"): "主体A"}
        groups, out_of_scope, valid_count = group_rows_by_operator(rows, 2, 0, 1, mapping)
        self.assertEqual(valid_count, 2)
        self.assertEqual(groups["主体A"], [["A", "杭州市", "A杭州市"]])
        self.assertEqual(out_of_scope[0]["brand"], "B")


class StylePayloadTests(unittest.TestCase):
    def test_normalize_rgb_color_to_hex(self):
        self.assertEqual(normalize_color("rgb(255, 217, 0)"), "#FFD900")
        self.assertEqual(normalize_color("#ABCDEF"), "#ABCDEF")

    def test_sanitize_cell_prefers_rich_text_over_value(self):
        cell = {
            "value": "https://example.test",
            "rich_text": [{"type": "link", "text": "link", "link": "https://example.test"}],
            "cell_styles": {"background_color": "rgb(255, 217, 0)"},
            "ignored": "x",
        }
        result = sanitize_cell_for_set(cell)
        self.assertNotIn("value", result)
        self.assertNotIn("ignored", result)
        self.assertEqual(result["cell_styles"]["background_color"], "#FFD900")


class ConfirmedPublishReadbackTests(unittest.TestCase):
    def target(self):
        return TargetWorkbook(
            operator="测试主体",
            folder_token="folder",
            spreadsheet_token="sheet-token",
            url="https://example.invalid/sheet",
        )

    def test_write_and_verify_rejects_mismatch_after_third_column(self):
        class FakeCli:
            def sheets(self, args, *, input_text=None, retries=1):
                if args[0] in {"+csv-put", "+cells-set"}:
                    return {"ok": True}
                if args[0] == "+csv-get":
                    return {"data": {"annotated_csv": "A,B,C,D\n1,2,3,WRONG"}}
                raise AssertionError(args)

        publish = OperatorPublish(operator="测试主体", data_rows=[], target=self.target())
        with patch("run_split_publish.create_sheet", return_value="sheet-id"), patch(
            "run_split_publish.time.sleep", return_value=None
        ), self.assertRaisesRegex(NongfuError, "第 2 行第 4 列"):
            write_and_verify(
                FakeCli(),
                publish,
                "topic",
                [["A", "B", "C", "D"], ["1", "2", "3", "4"]],
                4,
                1,
                None,
                None,
                False,
                0,
            )

        self.assertEqual(publish.status, "pending")

    def test_confirmed_format_write_fails_closed_when_readback_is_unavailable(self):
        class FakeCli:
            def __init__(self):
                self.calls = []

            def sheets(self, args, *, input_text=None, retries=1):
                self.calls.append(args[0])
                if args[0] in {"+csv-put", "+cells-set"}:
                    return {"ok": True}
                if args[0] in {"+cells-get", "+sheet-info"}:
                    return {"data": {}}
                if args[0] == "+csv-get":
                    return {"data": {"annotated_csv": "品牌,城市\nA,杭州"}}
                raise AssertionError(args)

        publish = OperatorPublish(operator="测试主体", data_rows=[], target=self.target())
        cli = FakeCli()
        with patch("run_split_publish.create_sheet", return_value="sheet-id"), patch(
            "run_split_publish.time.sleep", return_value=None
        ), self.assertRaisesRegex(NongfuError, "格式读回"):
            write_and_verify(
                cli,
                publish,
                "topic",
                [["品牌", "城市"], ["A", "杭州"]],
                2,
                1,
                [[{"value": "品牌", "cell_styles": {"bold": True}}, {"value": "城市"}]],
                {"merged_cells": [], "row_heights": [], "column_widths": []},
                True,
                0,
            )

        self.assertEqual(publish.status, "pending")
        self.assertNotIn("+cells-set", cli.calls)

    def test_read_source_header_format_fails_closed_when_cells_are_unavailable(self):
        class FakeCli:
            def sheets(self, args, *, input_text=None, retries=1):
                return {"data": {}}

        source = SourceSheet(
            url="https://example.invalid/source",
            token="source-token",
            sheet_id="source-sheet",
            sheet_name="topic",
            row_count=2,
            column_count=2,
        )
        with self.assertRaisesRegex(NongfuError, "源表格式读取不可用"):
            read_header_format(FakeCli(), source, 1, 2)

    def test_read_source_header_format_fails_closed_when_layout_is_unavailable(self):
        class FakeCli:
            def sheets(self, args, *, input_text=None, retries=1):
                if args[0] == "+cells-get":
                    return {"data": {"ranges": [{"cells": [[{"value": "品牌"}, {"value": "城市"}]]}]}}
                if args[0] == "+sheet-info":
                    return {"data": {}}
                raise AssertionError(args)

        source = SourceSheet(
            url="https://example.invalid/source",
            token="source-token",
            sheet_id="source-sheet",
            sheet_name="topic",
            row_count=2,
            column_count=2,
        )
        with self.assertRaisesRegex(NongfuError, "源表格式读取不可用"):
            read_header_format(FakeCli(), source, 1, 2)

    def assert_refresh_existing_format_rejects(self, actual_cells, actual_layout):
        expected_cells = [[{"value": "品牌", "cell_styles": {"bold": True}}, {"value": "城市"}]]
        expected_layout = {
            "merged_cells": [{"range": "A1:B1"}],
            "row_heights": [{"rows": "1:1", "type": "pixel", "height": 32}],
            "column_widths": [{"cols": "A:B", "type": "pixel", "width": 120}],
        }

        class FakeCli:
            def sheets(self, args, *, input_text=None, retries=1):
                if args[0] in {"+cells-set", "+cells-merge", "+rows-resize", "+cols-resize"}:
                    return {"ok": True}
                if args[0] == "+cells-get":
                    return {"data": {"ranges": [{"cells": actual_cells}]}}
                if args[0] == "+sheet-info":
                    return {"data": actual_layout}
                raise AssertionError(args)

        publish = OperatorPublish(
            operator="测试主体",
            data_rows=[],
            target=self.target(),
            sheet_id="sheet-id",
            status="skipped",
        )
        with patch("run_split_publish.time.sleep", return_value=None), self.assertRaisesRegex(
            NongfuError, "格式读回"
        ):
            refresh_existing_header_format(
                FakeCli(),
                publish,
                expected_cells,
                expected_layout,
                1,
                2,
                0,
            )

        self.assertEqual(publish.status, "skipped")

    def test_refresh_existing_format_rejects_style_readback_mismatch(self):
        self.assert_refresh_existing_format_rejects(
            [[{"value": "品牌", "cell_styles": {"bold": False}}, {"value": "城市"}]],
            {
                "merged_cells": [{"range": "A1:B1"}],
                "row_heights": [{"rows": "1:1", "type": "pixel", "height": 32}],
                "column_widths": [{"cols": "A:B", "type": "pixel", "width": 120}],
            },
        )

    def test_refresh_existing_format_rejects_merge_readback_mismatch(self):
        self.assert_refresh_existing_format_rejects(
            [[{"value": "品牌", "cell_styles": {"bold": True}}, {"value": "城市"}]],
            {
                "merged_cells": [],
                "row_heights": [{"rows": "1:1", "type": "pixel", "height": 32}],
                "column_widths": [{"cols": "A:B", "type": "pixel", "width": 120}],
            },
        )

    def test_refresh_existing_format_rejects_row_height_readback_mismatch(self):
        self.assert_refresh_existing_format_rejects(
            [[{"value": "品牌", "cell_styles": {"bold": True}}, {"value": "城市"}]],
            {
                "merged_cells": [{"range": "A1:B1"}],
                "row_heights": [],
                "column_widths": [{"cols": "A:B", "type": "pixel", "width": 120}],
            },
        )

    def test_refresh_existing_format_rejects_column_width_readback_mismatch(self):
        self.assert_refresh_existing_format_rejects(
            [[{"value": "品牌", "cell_styles": {"bold": True}}, {"value": "城市"}]],
            {
                "merged_cells": [{"range": "A1:B1"}],
                "row_heights": [{"rows": "1:1", "type": "pixel", "height": 32}],
                "column_widths": [],
            },
        )

    def test_refresh_existing_format_accepts_custom_to_pixel_readback_when_sizes_match(self):
        cells = [[{"value": "品牌", "cell_styles": {"bold": True}}, {"value": "城市"}]]
        source_layout = {
            "merged_cells": [{"range": "A1:B1"}],
            "row_heights": [{"rows": "1:1", "type": "custom", "height": 32}],
            "column_widths": [{"cols": "A:B", "type": "custom", "width": 120}],
        }
        target_layout = {
            "merged_cells": [{"range": "A1:B1"}],
            "row_heights": [{"rows": "1:1", "type": "pixel", "height": 32}],
            "column_widths": [{"cols": "A:B", "type": "pixel", "width": 120}],
        }

        class FakeCli:
            def sheets(self, args, *, input_text=None, retries=1):
                if args[0] in {"+cells-set", "+cells-merge", "+rows-resize", "+cols-resize"}:
                    return {"ok": True}
                if args[0] == "+cells-get":
                    return {"data": {"ranges": [{"cells": cells}]}}
                if args[0] == "+sheet-info":
                    return {"data": target_layout}
                raise AssertionError(args)

        publish = OperatorPublish(
            operator="测试主体",
            data_rows=[],
            target=self.target(),
            sheet_id="sheet-id",
            status="skipped",
        )
        with patch("run_split_publish.time.sleep", return_value=None):
            refresh_existing_header_format(FakeCli(), publish, cells, source_layout, 1, 2, 0)

        self.assertEqual(publish.status, "format_refreshed")


if __name__ == "__main__":
    unittest.main()
