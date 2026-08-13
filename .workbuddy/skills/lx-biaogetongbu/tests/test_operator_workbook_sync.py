import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from operator_workbook_sync import (  # noqa: E402
    AppendRow,
    BuildContext,
    CellUpdate,
    ImageCopyTask,
    OperatorWorkbook,
    SheetRef,
    SheetTable,
    SheetImage,
    TableRow,
    build_plan,
    extract_embed_images,
    group_contiguous_columns,
    parse_annotated_csv,
    plain_cell_risk,
    verify_append_keys,
    verify_image_copies,
    verify_updates,
    write_image_copies,
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


class FakeCli:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def sheets(self, args, *, input_text=None, retries=1):
        self.calls.append((args, input_text, retries))
        return self.result


class ReadbackCli:
    def __init__(self, *, scalar_values=None, image_cells=None):
        self.scalar_values = scalar_values or {}
        self.image_cells = image_cells or {}

    def sheets(self, args, *, input_text=None, retries=1):
        cell = args[args.index("--range") + 1]
        if "+csv-get" in args:
            value = self.scalar_values.get(cell, "")
            return {"data": {"annotated_csv": f"[row=1] {value}"}}
        if "+cells-get" in args:
            return {"data": {"ranges": [{"cells": [[self.image_cells.get(cell, {})]]}]}}
        raise AssertionError(f"unexpected fake CLI call: {args}")


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

    def test_image_column_creates_copy_task_without_blocking_append(self):
        profile = {
            **BASE_PROFILE,
            "image_columns": ["人证"],
        }
        master = make_table(
            "master",
            ["品牌", "司机ID", "城市", "人证"],
            [],
            last_row=1,
        )
        source = make_table(
            "source",
            ["品牌", "司机ID", "城市", "人证", "是否提交"],
            [(2, {"品牌": "线下出行", "司机ID": "615", "城市": "威海", "人证": "", "是否提交": ""})],
            last_row=2,
        )
        source.ref.row_count = 2
        source.ref.column_count = 5
        fake_cli = FakeCli(
            {
                "data": {
                    "ranges": [
                        {
                            "row_indices": [2],
                            "col_indices": ["D"],
                            "cells": [
                                [
                                    {
                                        "rich_text": [
                                            {
                                                "type": "embed-image",
                                                "text": "id-card.png",
                                                "image_name": "id-card.png",
                                                "image_token": "img-token",
                                                "image_width": 320,
                                                "image_height": 240,
                                            }
                                        ]
                                    }
                                ]
                            ],
                        }
                    ]
                }
            }
        )

        context = make_context(profile, master, source)
        context.profile["_cli"] = fake_cli
        plan = build_plan(context)

        self.assertEqual(plan["blocking"]["image_risks"], [])
        self.assertEqual(len(plan["append_rows"]), 1)
        self.assertEqual(len(plan["image_copies"]), 1)
        copy_task = plan["image_copies"][0]
        self.assertEqual(copy_task.source_cell, "D2")
        self.assertEqual(copy_task.target_cell, "D2")
        self.assertEqual(copy_task.image.image_token, "img-token")
        self.assertEqual(copy_task.image.image_name, "id-card.png")


class CellRiskTests(unittest.TestCase):
    def test_plain_text_cell_is_not_risky(self):
        self.assertFalse(plain_cell_risk({"value": "文字"}))

    def test_embed_image_rich_text_is_risky(self):
        self.assertTrue(plain_cell_risk({"rich_text": [{"type": "embed-image", "image_token": "tok"}]}))

    def test_group_contiguous_columns(self):
        self.assertEqual(group_contiguous_columns({2: "B", 3: "C", 5: "E"}), [(2, ["B", "C"]), (5, ["E"])])

    def test_extract_embed_images_keeps_token_and_dimensions(self):
        images = extract_embed_images(
            {
                "rich_text": [
                    {
                        "type": "embed-image",
                        "text": "proof.jpg",
                        "image_token": "tok",
                        "image_width": 120,
                        "image_height": 90,
                    }
                ]
            }
        )

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].image_token, "tok")
        self.assertEqual(images[0].image_name, "proof.jpg")
        self.assertEqual(images[0].image_width, 120)
        self.assertEqual(images[0].image_height, 90)


class ImageWriteTests(unittest.TestCase):
    def test_write_image_copies_uses_cells_set_rich_text(self):
        fake_cli = FakeCli({"ok": True})
        copy_task = ImageCopyTask(
            operator="方舟行武汉",
            source_token="source-token",
            source_sheet_id="source-sheet",
            source_sheet_name="来源",
            source_row_number=2,
            source_column_number=4,
            source_column_name="人证",
            target_token="master-token",
            target_sheet_id="master-sheet",
            target_sheet_name="大表",
            target_row_number=8,
            target_column_number=4,
            target_column_name="人证",
            images=[
                SheetImage(
                    image_token="img-token",
                    image_name="id-card.png",
                    image_width=320,
                    image_height=240,
                )
            ],
        )

        results = write_image_copies(fake_cli, [copy_task], 0)

        args, payload, _ = fake_cli.calls[0]
        self.assertEqual(results[0]["target_cell"], "D8")
        self.assertIn("+cells-set", args)
        self.assertIn("--cells", args)
        self.assertIn("--range", args)
        self.assertIn("D8", args)
        self.assertIn('"type": "embed-image"', payload)
        self.assertIn('"image_token": "img-token"', payload)


class CompleteReadbackTests(unittest.TestCase):
    def test_update_readback_includes_thirty_first_mismatch(self):
        updates = [
            CellUpdate(
                operator="测试主体",
                token="source-token",
                sheet_id="source-sheet",
                sheet_name="来源",
                row_number=index + 2,
                column_number=4,
                column_name="状态",
                old_value="",
                new_value=f"状态-{index}",
                reason="test",
            )
            for index in range(31)
        ]
        values = {update.cell: update.new_value for update in updates}
        values[updates[30].cell] = "mismatch"

        checks = verify_updates(ReadbackCli(scalar_values=values), updates)

        self.assertEqual(len(checks), 31)
        self.assertFalse(checks[30]["ok"])

    def test_append_key_readback_includes_thirty_first_mismatch(self):
        rows = [
            AppendRow(
                operator="测试主体",
                source_row_number=index + 2,
                target_row_number=index + 2,
                key_text=f"key-{index}",
                values_by_column={1: f"key-{index}"},
            )
            for index in range(31)
        ]
        values = {f"A{row.target_row_number}": row.key_text for row in rows}
        values[f"A{rows[30].target_row_number}"] = "mismatch"
        master = make_table("master", ["id"], [], last_row=1)

        checks = verify_append_keys(ReadbackCli(scalar_values=values), master, rows, ["id"])

        self.assertEqual(len(checks), 31)
        self.assertFalse(checks[30]["ok"])

    def test_append_readback_rejects_non_key_payload_mismatch(self):
        row = AppendRow(
            operator="测试主体",
            source_row_number=2,
            target_row_number=2,
            key_text="key-1",
            values_by_column={1: "key-1", 2: "expected-payload"},
        )
        master = make_table("master", ["id", "payload"], [], last_row=1)

        checks = verify_append_keys(
            ReadbackCli(scalar_values={"A2": "key-1", "B2": "wrong-payload"}),
            master,
            [row],
            ["id"],
        )

        self.assertFalse(checks[0]["ok"])
        self.assertEqual(checks[0]["cells"][1]["cell"], "B2")

    def test_image_readback_includes_thirty_first_mismatch(self):
        copies = [
            ImageCopyTask(
                operator="测试主体",
                source_token="source-token",
                source_sheet_id="source-sheet",
                source_sheet_name="来源",
                source_row_number=index + 2,
                source_column_number=4,
                source_column_name="人证",
                target_token="master-token",
                target_sheet_id="master-sheet",
                target_sheet_name="大表",
                target_row_number=index + 2,
                target_column_number=4,
                target_column_name="人证",
                images=[SheetImage(image_token=f"image-{index}")],
            )
            for index in range(31)
        ]
        image_cells = {
            copy.target_cell: {"rich_text": [{"type": "embed-image", "image_token": copy.image.image_token}]}
            for copy in copies[:30]
        }

        checks = verify_image_copies(ReadbackCli(image_cells=image_cells), copies)

        self.assertEqual(len(checks), 31)
        self.assertFalse(checks[30]["ok"])

    def test_image_readback_rejects_same_count_with_different_identity(self):
        copy = ImageCopyTask(
            operator="测试主体",
            source_token="source-token",
            source_sheet_id="source-sheet",
            source_sheet_name="来源",
            source_row_number=2,
            source_column_number=4,
            source_column_name="人证",
            target_token="master-token",
            target_sheet_id="master-sheet",
            target_sheet_name="大表",
            target_row_number=2,
            target_column_number=4,
            target_column_name="人证",
            images=[SheetImage(image_token="expected-image")],
        )

        checks = verify_image_copies(
            ReadbackCli(
                image_cells={
                    "D2": {"rich_text": [{"type": "embed-image", "image_token": "other-image"}]}
                }
            ),
            [copy],
        )

        self.assertFalse(checks[0]["ok"])
        self.assertEqual(checks[0]["expected_image_identities"], [("token", "expected-image")])


if __name__ == "__main__":
    unittest.main()
