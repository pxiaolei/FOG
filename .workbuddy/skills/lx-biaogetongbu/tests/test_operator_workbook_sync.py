import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from operator_workbook_sync import (  # noqa: E402
    BuildContext,
    OperatorWorkbook,
    SheetRef,
    SheetTable,
    TableRow,
    build_plan,
    group_contiguous_columns,
    parse_annotated_csv,
    plain_cell_risk,
)


def make_table(label, headers, rows, *, last_row=None):
    header_map = {name: index for index, name in enumerate(headers, start=1)}
    records = [
        TableRow(row_number=row_number, values={name: str(values.get(name, "")) for name in headers})
        for row_number, values in rows
    ]
    return SheetTable(
        label=label,
        ref=SheetRef(
            token=f"{label}-token",
            url="",
            sheet_id=f"{label}-sheet",
            sheet_name="Sheet1",
            row_count=max(last_row or 1, 200),
            column_count=max(len(headers), 20),
        ),
        headers=header_map,
        rows=records,
        last_nonblank_row=last_row or (max((row.row_number for row in records), default=1)),
    )


def make_context(profile, master, source):
    workbook = OperatorWorkbook(
        operator="方舟行武汉",
        folder_token="folder",
        token="source-token",
        url="",
        name="方舟行武汉-背审申诉",
    )
    profile = dict(profile)
    profile["_cli"] = None
    return BuildContext(
        profile=profile,
        master=master,
        sources=[(workbook, source)],
        operators_requested=["方舟行武汉"],
    )


BASE_PROFILE = {
    "status_column": "是否提交",
    "submitted_value": "填写已提交",
    "key_columns": ["司机ID"],
    "required_columns": ["品牌", "司机ID", "城市"],
    "image_columns": [],
}


class CsvParsingTests(unittest.TestCase):
    def test_parse_annotated_csv_keeps_multiline_fields(self):
        text = '[row=1] 品牌,问题描述\n[row=2] 方舟行,"第一行\n第二行"'
        self.assertEqual(parse_annotated_csv(text), [["品牌", "问题描述"], ["方舟行", "第一行\n第二行"]])


class OperatorSyncPlanTests(unittest.TestCase):
    def test_existing_master_row_marks_source_submitted_without_append(self):
        master = make_table(
            "master",
            ["品牌", "司机ID", "城市"],
            [(2, {"品牌": "线下出行", "司机ID": "615", "城市": "威海"})],
            last_row=2,
        )
        source = make_table(
            "source",
            ["品牌", "司机ID", "城市"],
            [(2, {"品牌": "线下出行", "司机ID": "615", "城市": "威海"})],
            last_row=2,
        )

        plan = build_plan(make_context(BASE_PROFILE, master, source))

        self.assertEqual(plan["append_rows"], [])
        self.assertEqual(len(plan["status_header_updates"]), 1)
        self.assertEqual(len(plan["status_updates"]), 1)
        self.assertEqual(plan["status_updates"][0].cell, "D2")
        self.assertEqual(plan["already_in_master"][0]["master_row_number"], 2)

    def test_new_source_row_appends_to_next_master_row_and_marks_submitted(self):
        master = make_table(
            "master",
            ["品牌", "司机ID", "城市"],
            [(2, {"品牌": "其他", "司机ID": "111", "城市": "杭州"})],
            last_row=7,
        )
        source = make_table(
            "source",
            ["品牌", "司机ID", "城市", "是否提交"],
            [(2, {"品牌": "线下出行", "司机ID": "615", "城市": "威海", "是否提交": ""})],
            last_row=2,
        )

        plan = build_plan(make_context(BASE_PROFILE, master, source))

        self.assertEqual(len(plan["append_rows"]), 1)
        self.assertEqual(plan["append_rows"][0].target_row_number, 8)
        self.assertEqual(plan["append_rows"][0].values_by_column, {1: "线下出行", 2: "615", 3: "威海"})
        self.assertEqual(plan["status_updates"][0].cell, "D2")
        self.assertEqual(plan["status_updates"][0].reason, "appended_to_master")

    def test_result_writeback_updates_source_even_when_source_already_submitted(self):
        profile = {
            **BASE_PROFILE,
            "result_writeback": {
                "enabled": True,
                "column": "背审结果",
                "source_column": "背审结果",
                "key_columns": ["司机ID"],
            },
        }
        master = make_table(
            "master",
            ["品牌", "司机ID", "城市", "背审结果"],
            [(2, {"品牌": "线下出行", "司机ID": "615", "城市": "威海", "背审结果": "申诉通过"})],
            last_row=2,
        )
        source = make_table(
            "source",
            ["品牌", "司机ID", "城市", "背审结果", "是否提交"],
            [(2, {"品牌": "线下出行", "司机ID": "615", "城市": "威海", "背审结果": "", "是否提交": "填写已提交"})],
            last_row=2,
        )

        plan = build_plan(make_context(profile, master, source))

        self.assertEqual(plan["append_rows"], [])
        self.assertEqual(plan["status_updates"], [])
        self.assertEqual(len(plan["result_updates"]), 1)
        self.assertEqual(plan["result_updates"][0].cell, "D2")
        self.assertEqual(plan["result_updates"][0].new_value, "申诉通过")


class CellRiskTests(unittest.TestCase):
    def test_plain_text_cell_is_not_risky(self):
        self.assertFalse(plain_cell_risk({"value": "文字"}))

    def test_embed_image_rich_text_is_risky(self):
        self.assertTrue(plain_cell_risk({"rich_text": [{"type": "embed-image", "image_token": "tok"}]}))

    def test_group_contiguous_columns(self):
        self.assertEqual(group_contiguous_columns({2: "B", 3: "C", 5: "E"}), [(2, ["B", "C"]), (5, ["E"])])


if __name__ == "__main__":
    unittest.main()
