import json
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
    OperatorSyncError,
    OperatorWorkbook,
    SheetRef,
    SheetTable,
    SheetImage,
    TableRow,
    align_decorated_headers,
    build_plan,
    common_append_columns,
    extract_embed_images,
    format_validation_message,
    group_contiguous_columns,
    operator_from_workbook_title,
    parse_annotated_csv,
    strip_header_decoration,
    plain_cell_risk,
    result_writeback_specs,
    submitted_values_for,
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
    def __init__(self, result=None, *, drive_result=None, mounted_tokens=None):
        self.result = {"ok": True} if result is None else result
        self.drive_result = {"ok": True} if drive_result is None else drive_result
        self.mounted_tokens = list(mounted_tokens or [])
        self.calls = []
        self.drive_calls = []
        self._mount_count = 0

    def drive(self, args, *, retries=1, cwd=None):
        self.drive_calls.append((args, retries, cwd))
        if cwd is not None and "--output" in args:
            output_name = args[args.index("--output") + 1]
            destination = Path(cwd) / output_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"\x89PNG\r\n")
        return self.drive_result

    def sheets(self, args, *, input_text=None, retries=1, cwd=None):
        self.calls.append((args, input_text, retries, cwd))
        if "+cells-set-image" in args:
            self._mount_count += 1
        if "+cells-get" in args and self.mounted_tokens:
            index = self._mount_count - 1
            if index < 0 or index >= len(self.mounted_tokens):
                raise AssertionError(f"unexpected cells-get mount index {index}")
            token = self.mounted_tokens[index]
            return {
                "data": {
                    "ranges": [
                        {
                            "cells": [
                                [
                                    {
                                        "rich_text": [
                                            {
                                                "type": "embed-image",
                                                "image_token": token,
                                                "image_name": "mounted.png",
                                                "image_width": 320,
                                                "image_height": 240,
                                            }
                                        ]
                                    }
                                ]
                            ]
                        }
                    ]
                }
            }
        return self.result


class ReadbackCli:
    def __init__(self, *, scalar_values=None, image_cells=None):
        self.scalar_values = scalar_values or {}
        self.image_cells = image_cells or {}

    def sheets(self, args, *, input_text=None, retries=1, cwd=None):
        cell = args[args.index("--range") + 1]
        if "+csv-get" in args:
            value = self.scalar_values.get(cell, "")
            return {"data": {"annotated_csv": f"[row=1] {value}"}}
        if "+cells-get" in args:
            return {"data": {"ranges": [{"cells": [[self.image_cells.get(cell, {})]]}]}}
        raise AssertionError(f"unexpected fake CLI call: {args}")


def make_image_copy(**overrides):
    payload = {
        "operator": "方舟行武汉",
        "source_token": "source-token",
        "source_sheet_id": "source-sheet",
        "source_sheet_name": "来源",
        "source_row_number": 2,
        "source_column_number": 4,
        "source_column_name": "人证",
        "target_token": "master-token",
        "target_sheet_id": "master-sheet",
        "target_sheet_name": "大表",
        "target_row_number": 8,
        "target_column_number": 4,
        "target_column_name": "人证",
        "images": [
            SheetImage(
                image_token="img-token",
                image_name="id-card.png",
                image_width=320,
                image_height=240,
            )
        ],
    }
    payload.update(overrides)
    return ImageCopyTask(**payload)


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

    def test_result_writeback_overwrites_example_marker_without_skip_list(self):
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
            [(2, {"品牌": "线下出行", "司机ID": "615", "城市": "威海", "背审结果": "/示例", "是否提交": "填写已提交"})],
            last_row=2,
        )

        plan = build_plan(make_context(profile, master, source))

        self.assertEqual(len(plan["result_updates"]), 1)
        self.assertEqual(plan["result_updates"][0].old_value, "/示例")
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
        copy_task = make_image_copy()

        results = write_image_copies(fake_cli, [copy_task], 0)

        self.assertEqual(results[0]["target_cell"], "D8")
        self.assertEqual(results[0]["image_count"], 1)
        self.assertEqual(len(fake_cli.drive_calls), 1)
        self.assertEqual(len(fake_cli.calls), 1)
        drive_args, _, drive_cwd = fake_cli.drive_calls[0]
        sheet_args, payload, _, sheet_cwd = fake_cli.calls[0]
        self.assertEqual(drive_args[0], "+preview")
        self.assertEqual(drive_args[drive_args.index("--file-token") + 1], "img-token")
        self.assertEqual(drive_args[drive_args.index("--type") + 1], "source_file")
        output_name = drive_args[drive_args.index("--output") + 1]
        image_name = sheet_args[sheet_args.index("--image") + 1]
        self.assertEqual(output_name, image_name)
        self.assertFalse(Path(output_name).is_absolute())
        self.assertEqual(Path(output_name).name, output_name)
        self.assertIsNotNone(drive_cwd)
        self.assertEqual(Path(sheet_cwd), Path(drive_cwd))
        self.assertFalse(Path(drive_cwd).exists())
        self.assertIn("+cells-set-image", sheet_args)
        self.assertNotIn("+cells-set", sheet_args)
        self.assertNotIn("img-token", sheet_args)
        self.assertEqual(sheet_args[sheet_args.index("--spreadsheet-token") + 1], "master-token")
        self.assertEqual(sheet_args[sheet_args.index("--sheet-id") + 1], "master-sheet")
        self.assertEqual(sheet_args[sheet_args.index("--range") + 1], "D8")
        self.assertIsNone(payload)

    def test_write_image_copies_remounts_multiple_images_with_target_tokens(self):
        fake_cli = FakeCli(mounted_tokens=["target-token-1", "target-token-2"])
        copy_task = make_image_copy(
            images=[
                SheetImage(image_token="source-token-1", image_name="front.png", image_width=320, image_height=240),
                SheetImage(image_token="source-token-2", image_name="back.jpg", image_width=300, image_height=200),
            ]
        )

        results = write_image_copies(fake_cli, [copy_task], 0)

        self.assertEqual(results[0]["image_count"], 2)
        preview_tokens = [
            args[args.index("--file-token") + 1]
            for args, _, _ in fake_cli.drive_calls
        ]
        self.assertEqual(preview_tokens, ["source-token-1", "source-token-2"])
        set_image_calls = [call for call in fake_cli.calls if "+cells-set-image" in call[0]]
        readback_calls = [call for call in fake_cli.calls if "+cells-get" in call[0]]
        assemble_calls = [call for call in fake_cli.calls if "+cells-set" in call[0]]
        self.assertEqual(len(set_image_calls), 2)
        self.assertEqual(len(readback_calls), 2)
        self.assertEqual(len(assemble_calls), 1)
        payload = assemble_calls[0][1]
        self.assertIn("target-token-1", payload)
        self.assertIn("target-token-2", payload)
        self.assertNotIn("source-token-1", payload)
        self.assertNotIn("source-token-2", payload)
        self.assertFalse(Path(fake_cli.drive_calls[0][2]).exists())

    def test_write_image_copies_rejects_missing_token_without_upload(self):
        fake_cli = FakeCli({"ok": True})
        copy_task = make_image_copy(images=[SheetImage(image_uri="sheet://image")])

        with self.assertRaises(OperatorSyncError):
            write_image_copies(fake_cli, [copy_task], 0)

        self.assertEqual(fake_cli.drive_calls, [])
        self.assertEqual(fake_cli.calls, [])

    def test_write_image_copies_removes_temp_files_when_preview_fails(self):
        class PreviewFailureCli:
            def __init__(self):
                self.cwd = None

            def drive(self, args, *, retries=1, cwd=None):
                self.cwd = Path(cwd)
                output_name = args[args.index("--output") + 1]
                (self.cwd / output_name).write_bytes(b"partial")
                raise OperatorSyncError("preview failed")

            def sheets(self, args, *, input_text=None, retries=1, cwd=None):
                raise AssertionError("failed preview must not upload")

        fake_cli = PreviewFailureCli()
        with self.assertRaises(OperatorSyncError):
            write_image_copies(fake_cli, [make_image_copy()], 0)

        self.assertIsNotNone(fake_cli.cwd)
        self.assertFalse(fake_cli.cwd.exists())


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

    def test_image_readback_accepts_same_count_with_different_token(self):
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
            images=[SheetImage(image_token="expected-image", image_width=320, image_height=240)],
        )

        checks = verify_image_copies(
            ReadbackCli(
                image_cells={
                    "D2": {
                        "rich_text": [
                            {
                                "type": "embed-image",
                                "image_token": "other-image",
                                "image_width": 320,
                                "image_height": 240,
                            }
                        ]
                    }
                }
            ),
            [copy],
        )

        self.assertTrue(checks[0]["ok"])
        self.assertEqual(checks[0]["expected_image_count"], 1)
        self.assertEqual(checks[0]["actual_image_count"], 1)
        self.assertEqual(checks[0]["expected_dimensions"], [[320, 240]])
        self.assertEqual(checks[0]["actual_dimensions"], [[320, 240]])

    def test_image_readback_rejects_missing_image(self):
        copy = ImageCopyTask(
            operator="测试主体",
            source_token="source-token",
            source_sheet_id="source-sheet",
            source_sheet_name="来源",
            source_row_number=2,
            source_column_number=12,
            source_column_name="退卡凭证",
            target_token="master-token",
            target_sheet_id="master-sheet",
            target_sheet_name="大表",
            target_row_number=1001,
            target_column_number=12,
            target_column_name="退卡凭证",
            images=[SheetImage(image_token="source-image")],
        )

        checks = verify_image_copies(ReadbackCli(image_cells={"L1001": {}}), [copy])

        self.assertFalse(checks[0]["ok"])
        self.assertEqual(checks[0]["expected_image_count"], 1)
        self.assertEqual(checks[0]["actual_image_count"], 0)

    def test_image_readback_reports_dimensions_without_failing_count_match(self):
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
            images=[SheetImage(image_token="expected-image", image_width=320, image_height=240)],
        )

        checks = verify_image_copies(
            ReadbackCli(
                image_cells={
                    "D2": {
                        "rich_text": [
                            {
                                "type": "embed-image",
                                "image_token": "mounted-image",
                                "image_width": 10,
                                "image_height": 10,
                            }
                        ]
                    }
                }
            ),
            [copy],
        )

        self.assertTrue(checks[0]["ok"])
        self.assertEqual(checks[0]["actual_image_count"], 1)
        self.assertEqual(checks[0]["expected_dimensions"], [[320, 240]])
        self.assertEqual(checks[0]["actual_dimensions"], [[10, 10]])


JINGMO_PROFILE = {
    "status_column": "是否提交",
    "status_column_number": 9,
    "submitted_value": "已提报",
    "accepted_submitted_values": ["填写已提交", "已提报"],
    "key_columns": ["品牌", "城市", "订单ID", "用户ID（乘客ID）"],
    "required_columns": ["品牌", "城市", "订单ID", "用户ID（乘客ID）"],
    "require_nonempty_columns": ["用户ID（乘客ID）"],
    "max_source_column": 8,
    "image_columns": [],
}


class JingmoProfileRuleTests(unittest.TestCase):
    def test_max_source_column_truncates_append_columns(self):
        master = make_table(
            "master",
            ["品牌", "城市", "订单ID", "用户ID（乘客ID）", "工单描述", "备注J", "是否提交"],
            [],
            last_row=1,
        )
        # A..I then J-like 备注 beyond max_source_column=8
        source = make_table(
            "source",
            ["品牌", "城市", "订单ID", "用户ID（乘客ID）", "工单描述", "扩展F", "扩展G", "扩展H", "是否提交", "备注J"],
            [
                (
                    2,
                    {
                        "品牌": "盛世兄弟",
                        "城市": "杭州",
                        "订单ID": "O1",
                        "用户ID（乘客ID）": "U1",
                        "工单描述": "desc",
                        "扩展F": "f",
                        "扩展G": "g",
                        "扩展H": "h",
                        "是否提交": "",
                        "备注J": "should-not-sync",
                    },
                )
            ],
            last_row=2,
        )
        # Force 备注J to column 10 (J) even if header order would place 是否提交 at 9
        source.headers = {
            "品牌": 1,
            "城市": 2,
            "订单ID": 3,
            "用户ID（乘客ID）": 4,
            "工单描述": 5,
            "扩展F": 6,
            "扩展G": 7,
            "扩展H": 8,
            "是否提交": 9,
            "备注J": 10,
        }
        master.headers = {
            "品牌": 1,
            "城市": 2,
            "订单ID": 3,
            "用户ID（乘客ID）": 4,
            "工单描述": 5,
            "备注J": 6,
            "是否提交": 7,
        }

        cols = common_append_columns(source, master, JINGMO_PROFILE)
        self.assertEqual(cols, ["品牌", "城市", "订单ID", "用户ID（乘客ID）", "工单描述"])
        self.assertNotIn("备注J", cols)

        plan = build_plan(make_context(JINGMO_PROFILE, master, source))
        self.assertEqual(len(plan["append_rows"]), 1)
        self.assertNotIn(6, plan["append_rows"][0].values_by_column)  # master 备注J col
        self.assertEqual(
            plan["append_rows"][0].values_by_column,
            {1: "盛世兄弟", 2: "杭州", 3: "O1", 4: "U1", 5: "desc"},
        )

    def test_require_nonempty_columns_skips_missing_user_id(self):
        master = make_table(
            "master",
            ["品牌", "城市", "订单ID", "用户ID（乘客ID）"],
            [],
            last_row=1,
        )
        source = make_table(
            "source",
            ["品牌", "城市", "订单ID", "用户ID（乘客ID）", "是否提交"],
            [
                (2, {"品牌": "盛世兄弟", "城市": "杭州", "订单ID": "O1", "用户ID（乘客ID）": "", "是否提交": ""}),
                (3, {"品牌": "盛世兄弟", "城市": "杭州", "订单ID": "O2", "用户ID（乘客ID）": "U2", "是否提交": ""}),
            ],
            last_row=3,
        )
        source.headers = {
            "品牌": 1,
            "城市": 2,
            "订单ID": 3,
            "用户ID（乘客ID）": 4,
            "是否提交": 9,
        }

        plan = build_plan(make_context(JINGMO_PROFILE, master, source))

        self.assertEqual(len(plan["append_rows"]), 1)
        self.assertEqual(plan["append_rows"][0].source_row_number, 3)
        skipped = [item for item in plan["skipped"] if item["reason"] == "missing_required_values"]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["row_number"], 2)
        self.assertEqual(skipped[0]["missing"], ["用户ID（乘客ID）"])
        self.assertEqual(skipped[0]["values"]["用户ID（乘客ID）"], "")

    def test_accepted_submitted_values_treats_old_status_as_submitted(self):
        master = make_table(
            "master",
            ["品牌", "城市", "订单ID", "用户ID（乘客ID）"],
            [],
            last_row=1,
        )
        source = make_table(
            "source",
            ["品牌", "城市", "订单ID", "用户ID（乘客ID）", "是否提交"],
            [
                (
                    2,
                    {
                        "品牌": "盛世兄弟",
                        "城市": "杭州",
                        "订单ID": "O1",
                        "用户ID（乘客ID）": "U1",
                        "是否提交": "填写已提交",
                    },
                )
            ],
            last_row=2,
        )
        source.headers = {
            "品牌": 1,
            "城市": 2,
            "订单ID": 3,
            "用户ID（乘客ID）": 4,
            "是否提交": 9,
        }

        plan = build_plan(make_context(JINGMO_PROFILE, master, source))

        self.assertEqual(plan["append_rows"], [])
        self.assertEqual(plan["status_updates"], [])
        self.assertEqual(plan["skipped"][0]["reason"], "source_already_submitted")

    def test_status_column_number_writes_to_column_i(self):
        master = make_table(
            "master",
            ["品牌", "城市", "订单ID", "用户ID（乘客ID）"],
            [],
            last_row=1,
        )
        # headers A-D only; I column has no header yet
        source = make_table(
            "source",
            ["品牌", "城市", "订单ID", "用户ID（乘客ID）"],
            [(2, {"品牌": "盛世兄弟", "城市": "杭州", "订单ID": "O1", "用户ID（乘客ID）": "U1"})],
            last_row=2,
        )
        source.headers = {
            "品牌": 1,
            "城市": 2,
            "订单ID": 3,
            "用户ID（乘客ID）": 4,
        }

        plan = build_plan(make_context(JINGMO_PROFILE, master, source))

        self.assertEqual(len(plan["append_rows"]), 1)
        self.assertEqual(len(plan["status_header_updates"]), 1)
        self.assertEqual(plan["status_header_updates"][0].cell, "I1")
        self.assertEqual(plan["status_header_updates"][0].new_value, "是否提交")
        self.assertEqual(plan["status_updates"][0].cell, "I2")
        self.assertEqual(plan["status_updates"][0].column_name, "是否提交")
        self.assertEqual(plan["status_updates"][0].new_value, "已提报")

    def test_status_column_number_prefers_existing_header_at_column(self):
        master = make_table(
            "master",
            ["品牌", "城市", "订单ID", "用户ID（乘客ID）"],
            [],
            last_row=1,
        )
        source = make_table(
            "source",
            ["品牌", "城市", "订单ID", "用户ID（乘客ID）", "提报状态"],
            [
                (
                    2,
                    {
                        "品牌": "盛世兄弟",
                        "城市": "杭州",
                        "订单ID": "O1",
                        "用户ID（乘客ID）": "U1",
                        "提报状态": "",
                    },
                )
            ],
            last_row=2,
        )
        source.headers = {
            "品牌": 1,
            "城市": 2,
            "订单ID": 3,
            "用户ID（乘客ID）": 4,
            "提报状态": 9,
        }

        plan = build_plan(make_context(JINGMO_PROFILE, master, source))

        self.assertEqual(plan["status_header_updates"], [])
        self.assertEqual(plan["status_updates"][0].cell, "I2")
        self.assertEqual(plan["status_updates"][0].column_name, "提报状态")
        self.assertEqual(plan["status_updates"][0].new_value, "已提报")




TUIKA_HEADERS = [
    "填写日期",
    "品牌名称",
    "品牌id",
    "城市",
    "司机id",
    "卡券名称",
    "卡券id",
    "售价",
    "退款原因",
    "商家是否已调账补款",
    "若调账-调账ID",
    "截图",
    "是否已提报",
    "平台退卡金额",
    "商家需退卡金额",
    "平台是否完成打款",
]

TUIKA_PROFILE = {
    "status_column": "是否已提报",
    "status_column_number": 13,
    "submitted_value": "已提报",
    "accepted_submitted_values": ["已提报", "/"],
    "write_validation_status": True,
    "key_columns": ["司机id", "卡券id"],
    "required_columns": [
        "填写日期",
        "品牌名称",
        "品牌id",
        "城市",
        "司机id",
        "卡券名称",
        "卡券id",
        "售价",
        "退款原因",
        "商家是否已调账补款",
        "截图",
    ],
    "require_nonempty_columns": [
        "填写日期",
        "品牌名称",
        "品牌id",
        "城市",
        "司机id",
        "卡券名称",
        "卡券id",
        "售价",
        "退款原因",
        "商家是否已调账补款",
        "截图",
    ],
    "conditional_required": [{"when": {"商家是否已调账补款": "是"}, "columns": ["若调账-调账ID"]}],
    "max_source_column": 12,
    "image_columns": ["截图"],
    "result_writeback": {
        "enabled": True,
        "ignore_duplicates": True,
        "columns": [
            {"column": "平台退卡金额", "source_column": "平台退卡金额"},
            {"column": "商家需退卡金额", "source_column": "商家需退卡金额"},
            {"column": "平台是否完成打款", "source_column": "平台是否完成打款"},
        ],
        "key_columns": ["司机id", "卡券id"],
    },
}


def tuika_row(**overrides):
    base = {
        "填写日期": "2026-10-27",
        "品牌名称": "测试品牌",
        "品牌id": "B1",
        "城市": "杭州",
        "司机id": "D1",
        "卡券名称": "体验卡",
        "卡券id": "C1",
        "售价": "100",
        "退款原因": "不用了",
        "商家是否已调账补款": "否",
        "若调账-调账ID": "",
        "截图": "img",
        "是否已提报": "",
        "平台退卡金额": "",
        "商家需退卡金额": "",
        "平台是否完成打款": "",
    }
    base.update(overrides)
    return base


class TuikaProfileRuleTests(unittest.TestCase):
    def test_accepted_submitted_values_only_skip_listed_statuses(self):
        self.assertEqual(submitted_values_for(TUIKA_PROFILE), {"已提报", "/"})
        master = make_table("master", TUIKA_HEADERS[:12], [], last_row=1)
        source = make_table(
            "source",
            TUIKA_HEADERS,
            [
                (2, tuika_row(司机id="D2", 卡券id="C2", 是否已提报="已提交")),
                (3, tuika_row(司机id="D3", 卡券id="C3", 是否已提报="/")),
                (4, tuika_row(司机id="D4", 卡券id="C4", 是否已提报="缺少L列图片")),
            ],
            last_row=4,
        )
        plan = build_plan(make_context(TUIKA_PROFILE, master, source))
        skipped_submitted = [item for item in plan["skipped"] if item["reason"] == "source_already_submitted"]
        self.assertEqual([item["row_number"] for item in skipped_submitted], [3])
        append_rows = {item.source_row_number for item in plan["append_rows"]}
        skipped_rows = {item["row_number"] for item in plan["skipped"]}
        # 已提交 / 缺项提示都继续走校验或追加，不会因非空状态被当成已处理
        self.assertIn(2, append_rows | skipped_rows)
        self.assertIn(4, append_rows | skipped_rows)
        self.assertIn(2, append_rows)
        self.assertIn(4, append_rows)

    def test_conditional_required_needs_adjustment_id_when_yes(self):
        master = make_table("master", TUIKA_HEADERS[:12], [], last_row=1)
        source = make_table(
            "source",
            TUIKA_HEADERS,
            [(2, tuika_row(商家是否已调账补款="是", **{"若调账-调账ID": ""}))],
            last_row=2,
        )
        plan = build_plan(make_context(TUIKA_PROFILE, master, source))
        self.assertEqual(plan["append_rows"], [])
        skipped = [item for item in plan["skipped"] if item["reason"] == "missing_required_values"]
        self.assertEqual(len(skipped), 1)
        self.assertIn("若调账-调账ID", skipped[0]["missing"])
        self.assertEqual(plan["status_updates"][0].reason, "validation_status")
        self.assertIn("K列", plan["status_updates"][0].new_value)

    def test_validation_message_formats_text_and_image_columns(self):
        source = make_table("source", TUIKA_HEADERS, [], last_row=1)
        message = format_validation_message(
            missing_text_columns=["品牌名称", "退款原因"],
            missing_image_columns=["截图"],
            source=source,
        )
        self.assertEqual(message, "缺少B列、I列信息；缺少L列图片")

    def test_max_source_column_stops_before_status(self):
        master = make_table("master", TUIKA_HEADERS, [], last_row=1)
        source = make_table("source", TUIKA_HEADERS, [(2, tuika_row())], last_row=2)
        cols = common_append_columns(source, master, TUIKA_PROFILE)
        self.assertEqual(cols[-1], "截图")
        self.assertNotIn("是否已提报", cols)
        self.assertNotIn("平台退卡金额", cols)

    def test_multi_column_result_writeback(self):
        specs = result_writeback_specs(TUIKA_PROFILE)
        self.assertEqual(len(specs), 3)
        master = make_table(
            "master",
            TUIKA_HEADERS,
            [
                (
                    2,
                    tuika_row(
                        平台退卡金额="10",
                        商家需退卡金额="20",
                        平台是否完成打款="是",
                        是否已提报="已提报",
                    ),
                )
            ],
            last_row=2,
        )
        source = make_table(
            "source",
            TUIKA_HEADERS,
            [(2, tuika_row(是否已提报="已提报"))],
            last_row=2,
        )
        plan = build_plan(make_context(TUIKA_PROFILE, master, source))
        self.assertEqual(plan["append_rows"], [])
        self.assertEqual(len(plan["result_updates"]), 3)
        self.assertEqual({item.column_name for item in plan["result_updates"]}, {
            "平台退卡金额",
            "商家需退卡金额",
            "平台是否完成打款",
        })

    def test_same_validation_message_is_not_rewritten(self):
        master = make_table("master", TUIKA_HEADERS[:12], [], last_row=1)
        tip = "缺少L列图片"
        source = make_table(
            "source",
            TUIKA_HEADERS,
            [(2, tuika_row(截图="", 是否已提报=tip))],
            last_row=2,
        )
        plan = build_plan(make_context(TUIKA_PROFILE, master, source))
        self.assertEqual(plan["status_updates"], [])
        skipped = [item for item in plan["skipped"] if item["reason"] == "missing_required_values"]
        self.assertEqual(skipped[0]["validation_message"], tip)

    def test_master_duplicates_block_without_ignore(self):
        profile = {
            **TUIKA_PROFILE,
            "result_writeback": {
                **TUIKA_PROFILE["result_writeback"],
                "ignore_duplicates": False,
            },
        }
        master = make_table(
            "master",
            TUIKA_HEADERS,
            [
                (
                    2,
                    tuika_row(
                        平台退卡金额="10",
                        商家需退卡金额="20",
                        平台是否完成打款="是",
                        是否已提报="已提报",
                    ),
                ),
                (
                    3,
                    tuika_row(
                        平台退卡金额="11",
                        商家需退卡金额="21",
                        平台是否完成打款="否",
                        是否已提报="已提报",
                    ),
                ),
            ],
            last_row=3,
        )
        source = make_table(
            "source",
            TUIKA_HEADERS,
            [(2, tuika_row(是否已提报="已提报"))],
            last_row=2,
        )
        plan = build_plan(make_context(profile, master, source))
        self.assertTrue(plan["blocking"]["master_duplicates"])
        self.assertEqual(plan["duplicate_warnings"], [])
        # 无 ignore 时仍可用第一行回填，但会 blocking
        self.assertEqual(len(plan["result_updates"]), 3)
        self.assertEqual({item.new_value for item in plan["result_updates"]}, {"10", "20", "是"})

    def test_master_duplicates_ignored_for_tuika_writeback(self):
        master = make_table(
            "master",
            TUIKA_HEADERS,
            [
                (
                    2,
                    tuika_row(
                        平台退卡金额="10",
                        商家需退卡金额="20",
                        平台是否完成打款="是",
                        是否已提报="已提报",
                    ),
                ),
                (
                    3,
                    tuika_row(
                        平台退卡金额="99",
                        商家需退卡金额="99",
                        平台是否完成打款="否",
                        是否已提报="已提报",
                    ),
                ),
            ],
            last_row=3,
        )
        source = make_table(
            "source",
            TUIKA_HEADERS,
            [(2, tuika_row(是否已提报="已提报"))],
            last_row=2,
        )
        plan = build_plan(make_context(TUIKA_PROFILE, master, source))
        self.assertEqual(plan["blocking"]["master_duplicates"], [])
        self.assertFalse(any(plan["blocking"].values()))
        self.assertEqual(len(plan["duplicate_warnings"]), 1)
        self.assertEqual(plan["duplicate_warnings"][0]["reason"], "result_writeback_duplicate")
        self.assertEqual(plan["duplicate_warnings"][0]["first_row_number"], 2)
        self.assertEqual(plan["duplicate_warnings"][0]["row_number"], 3)
        # 回填继续用第一行
        self.assertEqual(len(plan["result_updates"]), 3)
        self.assertEqual({item.new_value for item in plan["result_updates"]}, {"10", "20", "是"})

    def test_operator_title_parser(self):
        self.assertEqual(operator_from_workbook_title("盛世兄弟-日常信息"), "盛世兄弟")
        self.assertEqual(operator_from_workbook_title("保交行快车-运营主体-日常信息"), "保交行快车")

    def test_empty_accepted_list_keeps_legacy_submitted_value(self):
        self.assertEqual(submitted_values_for({"submitted_value": "填写已提交"}), {"填写已提交"})


BEISHEN_FIELDS = [
    "品牌",
    "司机ID",
    "手机号",
    "司机姓名",
    "身份证号码",
    "车牌号",
    "车辆识别代码（Vin码）",
    "城市",
    "问题描述",
    "人证",
    "承诺书",
    "司机端审核失败原因截图",
    "HH后台审核失败截图",
    "身份证正面",
]

BEISHEN_PROFILE_PATH = SKILL_DIR / "assets" / "profiles" / "beishen_shensu.json"


def load_beishen_profile():
    return json.loads(BEISHEN_PROFILE_PATH.read_text(encoding="utf-8"))


def beishen_source_headers():
    return BEISHEN_FIELDS + ["提报", "背审结果"]


def beishen_row(**overrides):
    base = {name: "已填" for name in BEISHEN_FIELDS}
    base["提报"] = ""
    base["背审结果"] = ""
    base.update(overrides)
    return base


def beishen_master():
    master = make_table("master", BEISHEN_FIELDS + ["背审结果"], [], last_row=1)
    master.headers = {name: index + 2 for index, name in enumerate(BEISHEN_FIELDS)}
    master.headers["背审结果"] = 16
    return master


class BeishenProfileRuleTests(unittest.TestCase):
    def test_profile_contract(self):
        profile = load_beishen_profile()
        self.assertEqual(profile["scenario_id"], "beishen_shensu")
        self.assertEqual(profile["master_sheet_name"], "司机背审申诉")
        self.assertEqual(profile["master_sheet_id"], "0AOZVh")
        self.assertTrue(profile["use_configured_operator_urls"])
        self.assertTrue(profile["match_decorated_headers"])
        self.assertEqual(profile["status_column"], "提报")
        self.assertEqual(profile["status_column_number"], 15)
        self.assertEqual(profile["submitted_value"], "已提报")
        self.assertFalse(profile["skip_already_in_master"])
        self.assertEqual(profile["same_batch_duplicate_status"], "同期重复提报")
        self.assertEqual(profile["accepted_submitted_values"], ["已提报", "/举例", "同期重复提报"])
        self.assertTrue(profile["write_validation_status"])
        self.assertEqual(profile["key_columns"], ["司机ID"])
        self.assertEqual(profile["max_source_column"], 14)
        self.assertEqual(profile["required_columns"], BEISHEN_FIELDS)
        self.assertEqual(profile["require_nonempty_columns"], BEISHEN_FIELDS)
        self.assertEqual(
            profile["image_columns"],
            ["人证", "承诺书", "司机端审核失败原因截图", "HH后台审核失败截图", "身份证正面"],
        )
        self.assertEqual(profile["result_writeback"]["column"], "背审结果")
        self.assertEqual(profile["result_writeback"]["source_column"], "背审结果")
        self.assertEqual(profile["result_writeback"]["key_columns"], ["司机ID"])
        self.assertTrue(profile["result_writeback"]["ignore_duplicates"])
        self.assertTrue(profile["result_writeback"]["use_last_row"])
        self.assertEqual(
            profile["default_operators"],
            [
                "同舟科技",
                "方舟行武汉",
                "乖乖马出行",
                "哈啰文山",
                "杭州华耀",
                "江豚出行",
                "盛世兄弟",
                "杭州法一",
                "小象快跑",
                "易惠出行",
                "土生福州",
            ],
        )
        self.assertEqual(submitted_values_for(profile), {"已提报", "/举例", "同期重复提报"})

    def test_header_decoration_strips_template_url_only(self):
        self.assertEqual(strip_header_decoration("承诺书https://example.com/tpl"), "承诺书")
        self.assertEqual(strip_header_decoration("承诺书\nhttps://example.com/tpl"), "承诺书")
        self.assertEqual(strip_header_decoration("承诺书HTTPS://example.com/tpl"), "承诺书")
        self.assertEqual(strip_header_decoration("车牌号码"), "车牌号码")

    def test_only_submitted_and_example_marker_skip(self):
        profile = load_beishen_profile()
        master = beishen_master()
        source = make_table(
            "source",
            beishen_source_headers(),
            [
                (2, beishen_row(司机ID="D2", 提报="已提交")),
                (3, beishen_row(司机ID="D3", 提报="/举例")),
                (4, beishen_row(司机ID="D4", 提报="已提报")),
                (5, beishen_row(司机ID="D5", 提报="缺少L列图片")),
            ],
            last_row=5,
        )
        plan = build_plan(make_context(profile, master, source))
        skipped_submitted = [item["row_number"] for item in plan["skipped"] if item["reason"] == "source_already_submitted"]
        self.assertEqual(skipped_submitted, [3, 4])
        self.assertIn(2, {item.source_row_number for item in plan["append_rows"]})
        self.assertIn(5, {item.source_row_number for item in plan["append_rows"]})

    def test_validation_tip_uses_column_letters_and_does_not_repeat(self):
        profile = load_beishen_profile()
        master = beishen_master()
        source = make_table(
            "source",
            beishen_source_headers(),
            [
                (
                    2,
                    beishen_row(**{"司机ID": "", "问题描述": "", "司机端审核失败原因截图": ""}),
                )
            ],
            last_row=2,
        )
        plan = build_plan(make_context(profile, master, source))
        self.assertEqual(plan["append_rows"], [])
        skipped = [item for item in plan["skipped"] if item["reason"] == "missing_required_values"]
        self.assertEqual(skipped[0]["validation_message"], "缺少B列、I列信息；缺少L列图片")
        self.assertEqual(plan["status_updates"][0].cell, "O2")
        self.assertEqual(plan["status_updates"][0].new_value, "缺少B列、I列信息；缺少L列图片")
        self.assertEqual(plan["status_updates"][0].reason, "validation_status")

        source_again = make_table(
            "source",
            beishen_source_headers(),
            [
                (
                    2,
                    beishen_row(
                        **{
                            "司机ID": "",
                            "问题描述": "",
                            "司机端审核失败原因截图": "",
                            "提报": "缺少B列、I列信息；缺少L列图片",
                        }
                    ),
                )
            ],
            last_row=2,
        )
        plan_again = build_plan(make_context(profile, beishen_master(), source_again))
        self.assertEqual(plan_again["status_updates"], [])

    def test_append_maps_source_a_n_onto_master_b_o_by_header(self):
        profile = load_beishen_profile()
        master = beishen_master()
        source = make_table(
            "source",
            beishen_source_headers(),
            [(2, beishen_row(品牌="线下出行", 司机ID="615", 背审结果="不要追加"))],
            last_row=2,
        )
        plan = build_plan(make_context(profile, master, source))
        self.assertEqual(len(plan["append_rows"]), 1)
        values = plan["append_rows"][0].values_by_column
        self.assertNotIn(1, values)
        self.assertEqual(values[2], "线下出行")
        self.assertEqual(values[3], "615")
        self.assertEqual(values[15], "已填")
        self.assertNotIn(16, values)
        self.assertEqual(set(values), set(range(2, 16)))
        cols = common_append_columns(source, master, profile)
        self.assertNotIn("提报", cols)
        self.assertNotIn("背审结果", cols)
        self.assertEqual(plan["status_updates"][0].new_value, "已提报")
        self.assertEqual(plan["status_updates"][0].column_number, 15)

    def test_decorated_headers_align_template_url_and_parenthetical_note(self):
        profile = load_beishen_profile()
        headers = []
        for name in beishen_source_headers():
            if name == "手机号":
                headers.append("手机号（必填）")
            elif name == "承诺书":
                headers.append("承诺书https://example.com/tpl")
            else:
                headers.append(name)
        row = {}
        for header, canonical in zip(headers, beishen_source_headers()):
            row[header] = beishen_row()[canonical]
        row["手机号（必填）"] = "13800000000"
        row["承诺书https://example.com/tpl"] = "img"
        source = make_table("source", headers, [(2, row)], last_row=2)
        plan = build_plan(make_context(profile, beishen_master(), source))
        self.assertEqual(plan["blocking"]["missing_headers"], [])
        self.assertEqual(len(plan["append_rows"]), 1)
        values = plan["append_rows"][0].values_by_column
        self.assertEqual(values[4], "13800000000")
        self.assertEqual(values[12], "img")
        self.assertEqual(source.headers["承诺书"], 11)
        self.assertEqual(source.headers["手机号"], 3)

    def test_missing_promise_image_uses_column_k_after_url_header(self):
        profile = load_beishen_profile()
        headers = ["承诺书https://example.com/tpl" if name == "承诺书" else name for name in beishen_source_headers()]
        row = {}
        for header, canonical in zip(headers, beishen_source_headers()):
            row[header] = beishen_row()[canonical]
        row["承诺书https://example.com/tpl"] = ""
        source = make_table("source", headers, [(2, row)], last_row=2)
        plan = build_plan(make_context(profile, beishen_master(), source))
        self.assertEqual(plan["append_rows"], [])
        skipped = [item for item in plan["skipped"] if item["reason"] == "missing_required_values"]
        self.assertEqual(skipped[0]["validation_message"], "缺少K列图片")

    def test_plate_header_does_not_absorb_a_longer_field_name(self):
        profile = load_beishen_profile()
        headers = ["车牌号码" if name == "车牌号" else name for name in beishen_source_headers()]
        row = {header: "已填" for header in headers}
        row["提报"] = ""
        source = make_table("source", headers, [(2, row)], last_row=2)
        plan = build_plan(make_context(profile, beishen_master(), source))
        self.assertEqual(plan["append_rows"], [])
        missing = plan["blocking"]["missing_headers"][0]["missing_required"]
        self.assertEqual(missing, ["车牌号"])
        self.assertNotIn("车牌号", source.headers)
        self.assertIn("车牌号码", source.headers)

    def test_result_writeback_uses_operator_column_p(self):
        profile = load_beishen_profile()
        master = beishen_master()
        master.rows = [
            TableRow(
                row_number=2,
                values=beishen_row(司机ID="615", 背审结果="申诉通过"),
            )
        ]
        master.last_nonblank_row = 2
        source = make_table(
            "source",
            beishen_source_headers(),
            [(2, beishen_row(司机ID="615", 提报="已提报", 背审结果=""))],
            last_row=2,
        )
        plan = build_plan(make_context(profile, master, source))
        self.assertEqual(plan["append_rows"], [])
        self.assertEqual(len(plan["result_updates"]), 1)
        update = plan["result_updates"][0]
        self.assertEqual(update.column_name, "背审结果")
        self.assertEqual(update.column_number, 16)
        self.assertEqual(update.cell, "P2")
        self.assertEqual(update.new_value, "申诉通过")

    def test_master_same_driver_still_appends(self):
        profile = load_beishen_profile()
        master = beishen_master()
        master.rows = [TableRow(row_number=2, values=beishen_row(司机ID="615", 提报="已提报"))]
        master.last_nonblank_row = 2
        source = make_table(
            "source",
            beishen_source_headers(),
            [(4, beishen_row(司机ID="615", 问题描述="改图重提"))],
            last_row=4,
        )
        plan = build_plan(make_context(profile, master, source))
        self.assertEqual(plan["already_in_master"], [])
        self.assertEqual([row.source_row_number for row in plan["append_rows"]], [4])
        self.assertEqual(plan["status_updates"][0].reason, "appended_to_master")
        self.assertEqual(plan["status_updates"][0].new_value, "已提报")

    def test_same_batch_keeps_first_row_and_marks_later_rows(self):
        profile = load_beishen_profile()
        source = make_table(
            "source",
            beishen_source_headers(),
            [
                (2, beishen_row(司机ID="615", 问题描述="第一行")),
                (5, beishen_row(司机ID="615", 问题描述="第二行")),
            ],
            last_row=5,
        )
        plan = build_plan(make_context(profile, beishen_master(), source))
        self.assertEqual([row.source_row_number for row in plan["append_rows"]], [2])
        duplicate_updates = [item for item in plan["status_updates"] if item.reason == "source_duplicate"]
        self.assertEqual(len(duplicate_updates), 1)
        self.assertEqual(duplicate_updates[0].row_number, 5)
        self.assertEqual(duplicate_updates[0].cell, "O5")
        self.assertEqual(duplicate_updates[0].new_value, "同期重复提报")
        self.assertEqual(plan["blocking"]["source_duplicates"], [])
        self.assertEqual(plan["source_duplicates"][0]["row_number"], 5)
        self.assertEqual(plan["source_duplicates"][0]["first_row_number"], 2)
        skipped = [item for item in plan["skipped"] if item["reason"] == "source_duplicate"]
        self.assertEqual(skipped[0]["row_number"], 5)

    def test_same_batch_duplicate_status_is_skipped_on_later_scan(self):
        profile = load_beishen_profile()
        self.assertIn("同期重复提报", submitted_values_for(profile))
        source = make_table(
            "source",
            beishen_source_headers(),
            [(2, beishen_row(司机ID="615", 提报="同期重复提报"))],
            last_row=2,
        )
        plan = build_plan(make_context(profile, beishen_master(), source))
        self.assertEqual(plan["append_rows"], [])
        self.assertEqual(plan["status_updates"], [])
        self.assertEqual(plan["skipped"][0]["reason"], "source_already_submitted")

    def test_writeback_uses_last_master_row_only_when_result_present(self):
        profile = load_beishen_profile()
        source = make_table(
            "source",
            beishen_source_headers(),
            [(2, beishen_row(司机ID="615", 提报="已提报", 背审结果="主体旧值"))],
            last_row=2,
        )
        master_blank_tail = beishen_master()
        master_blank_tail.rows = [
            TableRow(row_number=2, values=beishen_row(司机ID="615", 背审结果="旧结果")),
            TableRow(row_number=4, values=beishen_row(司机ID="615", 背审结果="")),
        ]
        master_blank_tail.last_nonblank_row = 4
        plan_blank = build_plan(make_context(profile, master_blank_tail, source))
        self.assertEqual(plan_blank["result_updates"], [])
        self.assertEqual(plan_blank["blocking"]["master_duplicates"], [])
        self.assertEqual(plan_blank["duplicate_warnings"][0]["first_row_number"], 2)
        self.assertEqual(plan_blank["duplicate_warnings"][0]["row_number"], 4)

        master_filled_tail = beishen_master()
        master_filled_tail.rows = [
            TableRow(row_number=2, values=beishen_row(司机ID="615", 背审结果="旧结果")),
            TableRow(row_number=5, values=beishen_row(司机ID="615", 背审结果="最新通过")),
        ]
        master_filled_tail.last_nonblank_row = 5
        plan_filled = build_plan(make_context(profile, master_filled_tail, source))
        self.assertEqual(len(plan_filled["result_updates"]), 1)
        self.assertEqual(plan_filled["result_updates"][0].new_value, "最新通过")
        self.assertEqual(plan_filled["blocking"]["master_duplicates"], [])

    def test_operator_titles(self):
        self.assertEqual(operator_from_workbook_title("盛世兄弟-背审申诉"), "盛世兄弟")
        self.assertEqual(operator_from_workbook_title("土生福州-日常信息"), "土生福州")

    def test_align_keeps_ambiguous_decorations(self):
        table = make_table(
            "source",
            ["承诺书https://example.com/a", "承诺书（模板）"],
            [(2, {"承诺书https://example.com/a": "1", "承诺书（模板）": "2"})],
            last_row=2,
        )
        align_decorated_headers(table, ["承诺书"])
        self.assertNotIn("承诺书", table.headers)
        self.assertEqual(table.rows[0].values["承诺书https://example.com/a"], "1")


YICHANG_FEE = "费用—不当所得（单位：元）"
YICHANG_NOTICE = "订单判责通知书截图"
YICHANG_REVIEW = "【商家复核】其他说明（必须详细）"
YICHANG_RESULT = "【治理反馈】本单复核结果"
YICHANG_RESULT_SOURCE_HEADER = "【治理反馈】本单复核结果\n（商家无需填写）"
YICHANG_OPERATOR_N = "司机申诉结果（无需填写，平台跑数）"
YICHANG_MASTER_N = "司机申诉结果（无需填写，中台跑数）"
YICHANG_ANY_IMAGES = [
    "其他证据1（照片）",
    "其他证据2（照片）",
    "其他证据3（照片）",
    "其他证据4（照片）",
]
YICHANG_TEXT_REQUIRED = [
    "商家名称",
    "商家id",
    "填表日期",
    "订单日期",
    "订单ID",
    "司机ID",
    "是否政诉",
    "判责类型",
    YICHANG_FEE,
    "case标签",
    "对应需要提供信息/证据",
    YICHANG_REVIEW,
]
YICHANG_PROFILE_PATH = SKILL_DIR / "assets" / "profiles" / "yichang_panzhe_case.json"
YICHANG_ANY_IMAGE_GAP = "缺少P\u2013S列图片"


def load_yichang_profile():
    return json.loads(YICHANG_PROFILE_PATH.read_text(encoding="utf-8"))


def yichang_source_headers():
    return [
        "提报人",
        "商家名称",
        "商家id",
        "填表日期",
        "订单日期",
        "订单ID",
        "司机ID",
        "是否政诉",
        "判责类型",
        YICHANG_FEE,
        "case标签",
        "对应需要提供信息/证据",
        YICHANG_NOTICE,
        YICHANG_OPERATOR_N,
        YICHANG_REVIEW,
        *YICHANG_ANY_IMAGES,
        "是否提报",
        YICHANG_RESULT_SOURCE_HEADER,
    ]


def yichang_master_headers():
    return [
        "提报人",
        "商家名称",
        "商家id",
        "填表日期",
        "订单日期",
        "订单ID",
        "司机ID",
        "是否政诉",
        "判责类型",
        YICHANG_FEE,
        "case标签",
        "对应需要提供信息/证据",
        YICHANG_NOTICE,
        YICHANG_MASTER_N,
        YICHANG_REVIEW,
        *YICHANG_ANY_IMAGES,
        YICHANG_RESULT,
        "是否补分补款",
        "是否本周收取（送职场）",
    ]


def yichang_source_row(**overrides):
    base = {name: "" for name in yichang_source_headers()}
    for name in YICHANG_TEXT_REQUIRED:
        base[name] = "已填"
    base[YICHANG_NOTICE] = "通知书图"
    base[YICHANG_ANY_IMAGES[0]] = "证据图"
    base["订单ID"] = "OID-1"
    base.update(overrides)
    return base


def yichang_master_row(**overrides):
    base = {name: "" for name in yichang_master_headers()}
    for name in YICHANG_TEXT_REQUIRED:
        base[name] = "已填"
    base["订单ID"] = "OID-1"
    base[YICHANG_RESULT] = ""
    base.update(overrides)
    return base


def yichang_master(rows=None, *, last_row=1):
    return make_table("master", yichang_master_headers(), rows or [], last_row=last_row)


class YichangPanzheProfileRuleTests(unittest.TestCase):
    def test_profile_contract(self):
        profile = load_yichang_profile()
        self.assertEqual(profile["scenario_id"], "yichang_panzhe_case")
        self.assertEqual(profile["master_sheet_name"], "10月case提报")
        self.assertEqual(profile["master_sheet_id"], "aWDUZd")
        self.assertTrue(profile["use_configured_operator_urls"])
        self.assertTrue(profile["match_decorated_headers"])
        self.assertFalse(profile["skip_already_in_master"])
        self.assertEqual(profile["same_batch_duplicate_status"], "同期重复提报")
        self.assertEqual(profile["status_column"], "是否提报")
        self.assertEqual(profile["status_column_number"], 20)
        self.assertEqual(profile["submitted_value"], "已提报")
        self.assertEqual(profile["accepted_submitted_values"], ["已提报", "/举例", "/示例", "同期重复提报"])
        self.assertTrue(profile["write_validation_status"])
        self.assertEqual(profile["key_columns"], ["订单ID"])
        self.assertEqual(profile["max_source_column"], 19)
        self.assertEqual(profile["require_nonempty_columns"], YICHANG_TEXT_REQUIRED + [YICHANG_NOTICE])
        self.assertNotIn("提报人", profile["require_nonempty_columns"])
        self.assertNotIn("提报人", profile["required_columns"])
        self.assertNotIn(YICHANG_OPERATOR_N, profile["require_nonempty_columns"])
        self.assertNotIn(YICHANG_OPERATOR_N, profile["required_columns"])
        self.assertNotIn(YICHANG_MASTER_N, profile["required_columns"])
        for column in YICHANG_ANY_IMAGES:
            self.assertNotIn(column, profile["require_nonempty_columns"])
            self.assertIn(column, profile["image_columns"])
        self.assertIn(YICHANG_NOTICE, profile["image_columns"])
        self.assertEqual(profile["require_any_image_columns"], [YICHANG_ANY_IMAGES])
        self.assertEqual(profile["result_writeback"]["column"], YICHANG_RESULT)
        self.assertEqual(profile["result_writeback"]["source_column"], YICHANG_RESULT)
        self.assertEqual(profile["result_writeback"]["key_columns"], ["订单ID"])
        self.assertTrue(profile["result_writeback"]["enabled"])
        self.assertTrue(profile["result_writeback"]["ignore_duplicates"])
        self.assertTrue(profile["result_writeback"]["use_last_row"])
        self.assertEqual(profile["result_writeback"]["skip_source_values"], ["/示例", "/举例"])
        self.assertEqual(
            profile["default_operators"],
            [
                "同舟科技",
                "盛世兄弟",
                "江豚出行",
                "方舟行武汉",
                "乖乖马出行",
                "易惠出行",
                "小象",
                "哈啰曲靖",
                "哈啰文山",
            ],
        )
        self.assertEqual(submitted_values_for(profile), {"已提报", "/举例", "/示例", "同期重复提报"})

    def test_example_markers_and_submitted_skip(self):
        profile = load_yichang_profile()
        source = make_table(
            "source",
            yichang_source_headers(),
            [
                (2, yichang_source_row(订单ID="OID-2", **{"是否提报": "已提交"})),
                (3, yichang_source_row(订单ID="OID-3", **{"是否提报": "/举例"})),
                (4, yichang_source_row(订单ID="OID-4", **{"是否提报": "/示例"})),
                (5, yichang_source_row(订单ID="OID-5", **{"是否提报": "已提报"})),
                (6, yichang_source_row(订单ID="OID-6", **{"是否提报": "缺少M列图片"})),
            ],
            last_row=6,
        )
        plan = build_plan(make_context(profile, yichang_master(), source))
        skipped_submitted = [
            item["row_number"] for item in plan["skipped"] if item["reason"] == "source_already_submitted"
        ]
        self.assertEqual(skipped_submitted, [3, 4, 5])
        appended = {item.source_row_number for item in plan["append_rows"]}
        self.assertIn(2, appended)
        self.assertIn(6, appended)

    def test_any_image_group_message_uses_column_span_or_letters(self):
        source = make_table("source", yichang_source_headers(), [], last_row=1)
        spanned = format_validation_message(
            missing_text_columns=[],
            missing_image_columns=[],
            missing_any_image_groups=[YICHANG_ANY_IMAGES],
            source=source,
        )
        self.assertEqual(spanned, YICHANG_ANY_IMAGE_GAP)
        scattered = make_table("source", ["甲", "乙", "丙"], [], last_row=1)
        listed = format_validation_message(
            missing_text_columns=[],
            missing_image_columns=[],
            missing_any_image_groups=[["甲", "丙"]],
            source=scattered,
        )
        self.assertEqual(listed, "缺少A列、C列图片")

    def test_p_to_s_requires_at_least_one_image(self):
        profile = load_yichang_profile()
        only_q = yichang_source_row(
            **{
                YICHANG_ANY_IMAGES[0]: "",
                YICHANG_ANY_IMAGES[1]: "证据图",
                YICHANG_ANY_IMAGES[2]: "",
                YICHANG_ANY_IMAGES[3]: "",
            }
        )
        plan_one = build_plan(
            make_context(
                profile,
                yichang_master(),
                make_table("source", yichang_source_headers(), [(2, only_q)], last_row=2),
            )
        )
        self.assertEqual([row.source_row_number for row in plan_one["append_rows"]], [2])
        self.assertFalse(any(item["reason"] == "missing_required_values" for item in plan_one["skipped"]))

        only_s = yichang_source_row(
            **{
                YICHANG_ANY_IMAGES[0]: "",
                YICHANG_ANY_IMAGES[1]: "",
                YICHANG_ANY_IMAGES[2]: "",
                YICHANG_ANY_IMAGES[3]: "证据图",
            }
        )
        plan_s = build_plan(
            make_context(
                profile,
                yichang_master(),
                make_table("source", yichang_source_headers(), [(2, only_s)], last_row=2),
            )
        )
        self.assertEqual([row.source_row_number for row in plan_s["append_rows"]], [2])

        none = yichang_source_row(
            **{name: "" for name in YICHANG_ANY_IMAGES}
        )
        plan_none = build_plan(
            make_context(
                profile,
                yichang_master(),
                make_table("source", yichang_source_headers(), [(2, none)], last_row=2),
            )
        )
        self.assertEqual(plan_none["append_rows"], [])
        skipped = [item for item in plan_none["skipped"] if item["reason"] == "missing_required_values"]
        self.assertEqual(skipped[0]["validation_message"], YICHANG_ANY_IMAGE_GAP)
        self.assertEqual(plan_none["status_updates"][0].cell, "T2")
        self.assertEqual(plan_none["status_updates"][0].new_value, YICHANG_ANY_IMAGE_GAP)
        self.assertEqual(plan_none["status_updates"][0].reason, "validation_status")

    def test_notice_image_m_is_required_even_when_other_evidence_exists(self):
        profile = load_yichang_profile()
        missing_notice = yichang_source_row(**{YICHANG_NOTICE: ""})
        plan = build_plan(
            make_context(
                profile,
                yichang_master(),
                make_table("source", yichang_source_headers(), [(2, missing_notice)], last_row=2),
            )
        )
        self.assertEqual(plan["append_rows"], [])
        skipped = [item for item in plan["skipped"] if item["reason"] == "missing_required_values"]
        self.assertEqual(skipped[0]["validation_message"], "缺少M列图片")
        self.assertNotIn("P", skipped[0]["validation_message"])

        missing_both = yichang_source_row(**{YICHANG_NOTICE: "", **{name: "" for name in YICHANG_ANY_IMAGES}})
        plan_both = build_plan(
            make_context(
                profile,
                yichang_master(),
                make_table("source", yichang_source_headers(), [(3, missing_both)], last_row=3),
            )
        )
        skipped_both = [item for item in plan_both["skipped"] if item["reason"] == "missing_required_values"]
        self.assertEqual(skipped_both[0]["validation_message"], f"缺少M列图片；{YICHANG_ANY_IMAGE_GAP}")
        self.assertEqual(plan_both["status_updates"][0].cell, "T3")

    def test_same_batch_marks_later_order_rows_and_skips_them_later(self):
        profile = load_yichang_profile()
        source = make_table(
            "source",
            yichang_source_headers(),
            [
                (2, yichang_source_row(订单ID="OID-9")),
                (5, yichang_source_row(订单ID="OID-9")),
            ],
            last_row=5,
        )
        plan = build_plan(make_context(profile, yichang_master(), source))
        self.assertEqual([row.source_row_number for row in plan["append_rows"]], [2])
        duplicate_updates = [item for item in plan["status_updates"] if item.reason == "source_duplicate"]
        self.assertEqual(len(duplicate_updates), 1)
        self.assertEqual(duplicate_updates[0].row_number, 5)
        self.assertEqual(duplicate_updates[0].cell, "T5")
        self.assertEqual(duplicate_updates[0].new_value, "同期重复提报")
        self.assertEqual(plan["blocking"]["source_duplicates"], [])

        later = make_table(
            "source",
            yichang_source_headers(),
            [(5, yichang_source_row(订单ID="OID-9", **{"是否提报": "同期重复提报"}))],
            last_row=5,
        )
        plan_later = build_plan(make_context(profile, yichang_master(), later))
        self.assertEqual(plan_later["append_rows"], [])
        self.assertEqual(plan_later["status_updates"], [])
        self.assertEqual(plan_later["skipped"][0]["reason"], "source_already_submitted")

    def test_writeback_uses_last_master_row_and_skips_blank_tail(self):
        profile = load_yichang_profile()
        source = make_table(
            "source",
            yichang_source_headers(),
            [
                (
                    2,
                    yichang_source_row(
                        订单ID="OID-9",
                        **{"是否提报": "已提报", YICHANG_RESULT_SOURCE_HEADER: "主体旧值"},
                    ),
                )
            ],
            last_row=2,
        )
        master_blank_tail = yichang_master(
            [
                (2, yichang_master_row(订单ID="OID-9", **{YICHANG_RESULT: "旧结果"})),
                (4, yichang_master_row(订单ID="OID-9", **{YICHANG_RESULT: ""})),
            ],
            last_row=4,
        )
        plan_blank = build_plan(make_context(profile, master_blank_tail, source))
        self.assertEqual(plan_blank["result_updates"], [])
        self.assertEqual(plan_blank["blocking"]["master_duplicates"], [])
        self.assertEqual(plan_blank["duplicate_warnings"][0]["first_row_number"], 2)
        self.assertEqual(plan_blank["duplicate_warnings"][0]["row_number"], 4)
        self.assertEqual(source.headers[YICHANG_RESULT], 21)

        master_filled_tail = yichang_master(
            [
                (2, yichang_master_row(订单ID="OID-9", **{YICHANG_RESULT: "旧结果"})),
                (5, yichang_master_row(订单ID="OID-9", **{YICHANG_RESULT: "最新通过"})),
            ],
            last_row=5,
        )
        source_filled = make_table(
            "source",
            yichang_source_headers(),
            [
                (
                    2,
                    yichang_source_row(
                        订单ID="OID-9",
                        **{"是否提报": "已提报", YICHANG_RESULT_SOURCE_HEADER: "主体旧值"},
                    ),
                )
            ],
            last_row=2,
        )
        plan_filled = build_plan(make_context(profile, master_filled_tail, source_filled))
        self.assertEqual(len(plan_filled["result_updates"]), 1)
        update = plan_filled["result_updates"][0]
        self.assertEqual(update.new_value, "最新通过")
        self.assertEqual(update.column_name, YICHANG_RESULT)
        self.assertEqual(update.column_number, 21)
        self.assertEqual(update.cell, "U2")
        self.assertEqual(plan_filled["blocking"]["master_duplicates"], [])

    def test_writeback_skips_result_cell_marked_example(self):
        profile = load_yichang_profile()
        source = make_table(
            "source",
            yichang_source_headers(),
            [
                (
                    2,
                    yichang_source_row(
                        订单ID="OID-9",
                        **{"是否提报": "已提报", YICHANG_RESULT_SOURCE_HEADER: "/示例"},
                    ),
                )
            ],
            last_row=2,
        )
        master = yichang_master(
            [
                (2, yichang_master_row(订单ID="OID-9", **{YICHANG_RESULT: "更早结果"})),
                (6, yichang_master_row(订单ID="OID-9", **{YICHANG_RESULT: "商家信息呢"})),
            ],
            last_row=6,
        )
        plan = build_plan(make_context(profile, master, source))
        self.assertEqual(plan["result_updates"], [])

    def test_writeback_skips_result_cell_marked_illustration(self):
        profile = load_yichang_profile()
        source = make_table(
            "source",
            yichang_source_headers(),
            [
                (
                    2,
                    yichang_source_row(
                        订单ID="OID-9",
                        **{"是否提报": "已提报", YICHANG_RESULT_SOURCE_HEADER: "/举例"},
                    ),
                )
            ],
            last_row=2,
        )
        master = yichang_master(
            [(4, yichang_master_row(订单ID="OID-9", **{YICHANG_RESULT: "商家信息呢"}))],
            last_row=4,
        )
        plan = build_plan(make_context(profile, master, source))
        self.assertEqual(plan["result_updates"], [])

    def test_writeback_trims_whitespace_around_example_markers(self):
        profile = load_yichang_profile()
        source = make_table(
            "source",
            yichang_source_headers(),
            [
                (
                    2,
                    yichang_source_row(
                        订单ID="OID-A",
                        **{"是否提报": "已提报", YICHANG_RESULT_SOURCE_HEADER: "  /示例  "},
                    ),
                ),
                (
                    3,
                    yichang_source_row(
                        订单ID="OID-B",
                        **{"是否提报": "已提报", YICHANG_RESULT_SOURCE_HEADER: "\t/举例\n"},
                    ),
                ),
            ],
            last_row=3,
        )
        master = yichang_master(
            [
                (2, yichang_master_row(订单ID="OID-A", **{YICHANG_RESULT: "商家信息呢"})),
                (3, yichang_master_row(订单ID="OID-B", **{YICHANG_RESULT: "最新通过"})),
            ],
            last_row=3,
        )
        plan = build_plan(make_context(profile, master, source))
        self.assertEqual(plan["result_updates"], [])

    def test_writeback_fills_blank_and_ordinary_result_cells(self):
        profile = load_yichang_profile()
        source = make_table(
            "source",
            yichang_source_headers(),
            [
                (
                    2,
                    yichang_source_row(
                        订单ID="OID-A",
                        **{"是否提报": "已提报", YICHANG_RESULT_SOURCE_HEADER: ""},
                    ),
                ),
                (
                    3,
                    yichang_source_row(
                        订单ID="OID-B",
                        **{"是否提报": "已提报", YICHANG_RESULT_SOURCE_HEADER: "主体旧值"},
                    ),
                ),
            ],
            last_row=3,
        )
        master = yichang_master(
            [
                (2, yichang_master_row(订单ID="OID-A", **{YICHANG_RESULT: "更早结果"})),
                (4, yichang_master_row(订单ID="OID-A", **{YICHANG_RESULT: "商家信息呢"})),
                (3, yichang_master_row(订单ID="OID-B", **{YICHANG_RESULT: "更早结果"})),
                (5, yichang_master_row(订单ID="OID-B", **{YICHANG_RESULT: "最新通过"})),
            ],
            last_row=5,
        )
        plan = build_plan(make_context(profile, master, source))
        updates = {(item.cell, item.old_value, item.new_value) for item in plan["result_updates"]}
        self.assertEqual(
            updates,
            {
                ("U2", "", "商家信息呢"),
                ("U3", "主体旧值", "最新通过"),
            },
        )

    def test_reporter_and_platform_run_column_are_optional(self):
        profile = load_yichang_profile()
        row = yichang_source_row(**{"提报人": "", YICHANG_OPERATOR_N: ""})
        master = yichang_master()
        plan = build_plan(
            make_context(
                profile,
                master,
                make_table("source", yichang_source_headers(), [(2, row)], last_row=2),
            )
        )
        self.assertEqual([item.source_row_number for item in plan["append_rows"]], [2])
        values = plan["append_rows"][0].values_by_column
        self.assertEqual(values[master.headers["提报人"]], "")
        self.assertNotIn(master.headers[YICHANG_MASTER_N], values)
        self.assertNotIn(master.headers[YICHANG_RESULT], values)
        self.assertEqual(plan["status_updates"][0].new_value, "已提报")
        self.assertEqual(plan["status_updates"][0].column_number, 20)
        self.assertEqual(plan["status_updates"][0].cell, "T2")
        self.assertEqual(plan["blocking"]["missing_headers"], [])
        appended_names = common_append_columns(
            make_table("source", yichang_source_headers(), [(2, row)], last_row=2),
            master,
            profile,
        )
        self.assertNotIn(YICHANG_OPERATOR_N, appended_names)
        self.assertNotIn(YICHANG_MASTER_N, appended_names)
        self.assertNotIn("是否提报", appended_names)
        self.assertNotIn(YICHANG_RESULT, appended_names)

    def test_operator_title_strips_case_workbook_suffix(self):
        self.assertEqual(operator_from_workbook_title("小象-异常判责case登记-新"), "小象")
        self.assertEqual(operator_from_workbook_title("哈啰曲靖-异常判责case登记-新"), "哈啰曲靖")
        self.assertEqual(operator_from_workbook_title("哈啰文山-异常判责case登记-新"), "哈啰文山")
        self.assertEqual(operator_from_workbook_title("盛世兄弟-背审申诉"), "盛世兄弟")
        self.assertEqual(
            operator_from_workbook_title("商家新-异常判责case登记-LX"),
            "商家新-异常判责case登记-LX",
        )


if __name__ == "__main__":
    unittest.main()
