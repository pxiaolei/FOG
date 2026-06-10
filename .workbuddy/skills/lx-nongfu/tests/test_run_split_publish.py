import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from run_split_publish import (  # noqa: E402
    auto_header_row,
    col_to_a1,
    extract_folder_token,
    extract_sheet_token,
    group_rows_by_operator,
    normalize_color,
    parse_annotated_csv,
    rows_to_csv,
    sanitize_cell_for_set,
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


if __name__ == "__main__":
    unittest.main()
