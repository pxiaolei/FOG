import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import operator_workbook_sync  # noqa: E402
import sync_table  # noqa: E402


class SyncTableSafetyTests(unittest.TestCase):
    def test_removed_skip_online_verify_flag_cannot_bypass_readback(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                sync_table.build_parser().parse_args(
                    [
                        "--online",
                        "--source-url",
                        "source",
                        "--target-url",
                        "target",
                        "--confirmed",
                        "--skip-online-verify",
                    ]
                )

    def test_online_readback_checks_the_twenty_first_update(self):
        updates = [
            sync_table.UpdateCell(
                key_text=str(index),
                source_row_number=index + 1,
                target_row_number=index + 1,
                target_column="id",
                target_column_number=1,
                old_value="old",
                new_value=f"value-{index}",
            )
            for index in range(1, 22)
        ]

        class ReadbackClient:
            def call_tool(self, name, payload):
                first_cell = str(payload["range"]).split(":", 1)[0]
                row_number = int(first_cell[1:])
                expected = f"value-{row_number - 1}"
                actual = "mismatch" if row_number == 22 else expected
                return {"grid_data": {"rows": [{"values": [sync_table.python_to_cell(actual)]}]}}

        with self.assertRaisesRegex(sync_table.SyncError, "A22"):
            sync_table.verify_online_cells(ReadbackClient(), "file", "sheet", updates)

    def test_online_confirmed_twenty_first_append_payload_mismatch_blocks_success_report(self):
        source_rows = [
            sync_table.RowRecord({"id": str(index), "value": f"new-{index}"}, index + 1)
            for index in range(1, 22)
        ]
        source = sync_table.TableData(
            "A",
            "Source",
            1,
            {"id": 1, "value": 2},
            source_rows,
        )
        target = sync_table.TableData("B", "Target", 1, {"id": 1, "value": 2}, [])
        source_sheet = sync_table.OnlineSheet("source-file", "source-sheet", "Source", 22, 2)
        target_sheet = sync_table.OnlineSheet("target-file", "target-sheet", "Target", 1, 2)

        class AppendMismatchClient:
            backend_label = "fake-feishu"

            def sheet_batch_update(self, file_id, requests):
                return None

            def call_tool(self, name, payload):
                first_cell = str(payload["range"]).split(":", 1)[0]
                column = first_cell[0]
                row_number = int(first_cell[1:])
                index = row_number - 1
                actual = str(index) if column == "A" else f"new-{index}"
                if first_cell == "B22":
                    actual = "mismatch"
                return {"grid_data": {"rows": [{"values": [sync_table.python_to_cell(actual)]}]}}

        args = sync_table.build_parser().parse_args(
            [
                "--online",
                "--source-url",
                "source",
                "--target-url",
                "target",
                "--key",
                "id",
                "--confirmed",
            ]
        )
        with patch.object(sync_table, "load_saas_client", return_value=AppendMismatchClient()), patch.object(
            sync_table,
            "read_online_table",
            side_effect=[(source, source_sheet), (target, target_sheet)],
        ), patch.object(
            sync_table,
            "write_report",
            side_effect=AssertionError("readback mismatch must block success report"),
        ):
            with self.assertRaisesRegex(sync_table.SyncError, "B22"):
                sync_table.run_online(args, {})

    def test_online_confirmed_twenty_first_update_mismatch_blocks_success_report(self):
        source_rows = [
            sync_table.RowRecord({"id": str(index), "value": f"new-{index}"}, index + 1)
            for index in range(1, 22)
        ]
        target_rows = [
            sync_table.RowRecord({"id": str(index), "value": f"old-{index}"}, index + 1)
            for index in range(1, 22)
        ]
        source = sync_table.TableData("A", "Source", 1, {"id": 1, "value": 2}, source_rows)
        target = sync_table.TableData("B", "Target", 1, {"id": 1, "value": 2}, target_rows)
        source_sheet = sync_table.OnlineSheet("source-file", "source-sheet", "Source", 22, 2)
        target_sheet = sync_table.OnlineSheet("target-file", "target-sheet", "Target", 22, 2)

        class UpdateMismatchClient:
            backend_label = "fake-feishu"

            def sheet_batch_update(self, file_id, requests):
                return None

            def call_tool(self, name, payload):
                first_cell = str(payload["range"]).split(":", 1)[0]
                row_number = int(first_cell[1:])
                actual = f"new-{row_number - 1}"
                if first_cell == "B22":
                    actual = "mismatch"
                return {"grid_data": {"rows": [{"values": [sync_table.python_to_cell(actual)]}]}}

        args = sync_table.build_parser().parse_args(
            [
                "--online",
                "--source-url",
                "source",
                "--target-url",
                "target",
                "--mode",
                "update-by-key",
                "--key",
                "id",
                "--update-column",
                "value",
                "--confirmed",
            ]
        )
        with patch.object(sync_table, "load_saas_client", return_value=UpdateMismatchClient()), patch.object(
            sync_table,
            "read_online_table",
            side_effect=[(source, source_sheet), (target, target_sheet)],
        ), patch.object(
            sync_table,
            "write_report",
            side_effect=AssertionError("readback mismatch must block success report"),
        ):
            with self.assertRaisesRegex(sync_table.SyncError, "B22"):
                sync_table.run_online(args, {})

    def test_excel_dry_run_does_not_write_report_output_or_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.xlsx"
            target = root / "target.xlsx"
            output = root / "output.xlsx"
            report_dir = root / "reports"
            for path, rows in (
                (source, [["id", "value"], ["1", "new"]]),
                (target, [["id", "value"]]),
            ):
                workbook = Workbook()
                sheet = workbook.active
                for row in rows:
                    sheet.append(row)
                workbook.save(path)
            target_before = target.read_bytes()

            result = sync_table.main(
                [
                    "--source",
                    str(source),
                    "--target",
                    str(target),
                    "--output",
                    str(output),
                    "--key",
                    "id",
                    "--report-dir",
                    str(report_dir),
                    "--dry-run",
                ]
            )

            self.assertEqual(result, 0)
            self.assertEqual(target.read_bytes(), target_before)
            self.assertFalse(output.exists())
            self.assertFalse(report_dir.exists())
            self.assertEqual(list(root.glob("target.xlsx.bak.*")), [])

    def test_online_dry_run_never_calls_write_or_report_helpers(self):
        source = sync_table.TableData("A", "Source", 1, {"id": 1}, [sync_table.RowRecord({"id": "1"}, 2)])
        target = sync_table.TableData("B", "Target", 1, {"id": 1}, [])
        source_sheet = sync_table.OnlineSheet("source-file", "source-sheet", "Source", 2, 1)
        target_sheet = sync_table.OnlineSheet("target-file", "target-sheet", "Target", 1, 1)
        fake_client = object()
        args = sync_table.build_parser().parse_args(
            [
                "--online",
                "--source-url",
                "source",
                "--target-url",
                "target",
                "--key",
                "id",
                "--dry-run",
            ]
        )

        with patch.object(sync_table, "load_saas_client", return_value=fake_client), patch.object(
            sync_table,
            "read_online_table",
            side_effect=[(source, source_sheet), (target, target_sheet)],
        ), patch.object(
            sync_table,
            "apply_online_requests",
            side_effect=AssertionError("dry-run must not write online"),
        ), patch.object(
            sync_table,
            "write_report",
            side_effect=AssertionError("dry-run must not write report"),
        ):
            result = sync_table.run_online(args, {})

        self.assertEqual(result, 0)


class OperatorWorkbookSafetyTests(unittest.TestCase):
    def test_confirmed_run_blocks_on_thirty_first_update_readback_mismatch(self):
        args = operator_workbook_sync.build_parser().parse_args(
            ["--scenario", "test", "--operator", "测试主体", "--confirmed", "--no-output-file"]
        )
        master = operator_workbook_sync.SheetTable(
            label="master",
            ref=operator_workbook_sync.SheetRef(
                token="master-token",
                url="",
                sheet_id="master-sheet",
                sheet_name="大表",
                row_count=1,
                column_count=1,
            ),
            headers={"id": 1},
            rows=[],
            last_nonblank_row=1,
        )
        updates = [
            operator_workbook_sync.CellUpdate(
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
        plan = {
            "append_rows": [],
            "image_copies": [],
            "status_header_updates": [],
            "status_updates": updates,
            "result_updates": [],
            "already_in_master": [],
            "skipped": [],
            "blocking": {"image_risks": []},
        }
        profile = {
            "scenario_id": "test",
            "target_table_template": "{operator}-测试",
            "key_columns": ["id"],
            "_profile_path": "test.json",
        }

        class ConfirmedReadbackCli:
            def __init__(self, *args, **kwargs):
                pass

            def sheets(self, cli_args, *, input_text=None, retries=1):
                cell = cli_args[cli_args.index("--range") + 1]
                row_number = int(cell[1:])
                actual = "mismatch" if row_number == 32 else f"状态-{row_number - 2}"
                return {"data": {"annotated_csv": f"[row=1] {actual}"}}

        with patch.object(operator_workbook_sync, "load_config", return_value={}), patch.object(
            operator_workbook_sync, "load_profile", return_value=profile
        ), patch.object(
            operator_workbook_sync, "resolve_contact_person", return_value="测试人"
        ), patch.object(
            operator_workbook_sync, "resolve_operator_root_folder", return_value="root-token"
        ), patch.object(
            operator_workbook_sync, "resolve_master_url", return_value="master-url"
        ), patch.object(
            operator_workbook_sync, "resolve_lark_cli", return_value="fake-cli"
        ), patch.object(
            operator_workbook_sync, "LarkCli", ConfirmedReadbackCli
        ), patch.object(
            operator_workbook_sync, "read_table", return_value=master
        ), patch.object(
            operator_workbook_sync,
            "resolve_operator_workbooks",
            return_value=([], [], ["测试主体"]),
        ), patch.object(
            operator_workbook_sync, "load_sources", return_value=([], [])
        ), patch.object(
            operator_workbook_sync, "build_plan", return_value=plan
        ), patch.object(
            operator_workbook_sync, "write_updates", return_value=[]
        ):
            with self.assertRaisesRegex(operator_workbook_sync.OperatorSyncError, "写后验证失败"):
                operator_workbook_sync.run(args)

    def test_existing_output_requires_overwrite_and_confirmed_before_client_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "existing.json"
            output.write_text("keep", encoding="utf-8")
            args = operator_workbook_sync.build_parser().parse_args(
                ["--scenario", "test", "--operator", "测试主体", "--output-json", str(output)]
            )
            with patch.object(operator_workbook_sync, "load_config", side_effect=AssertionError("must stop before client work")):
                with self.assertRaisesRegex(operator_workbook_sync.OperatorSyncError, "--overwrite --confirmed"):
                    operator_workbook_sync.run(args)
            self.assertEqual("keep", output.read_text(encoding="utf-8"))

    def test_unconfirmed_run_does_not_write_output_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "forbidden.json"
            args = operator_workbook_sync.build_parser().parse_args(
                ["--scenario", "test", "--operator", "测试主体", "--output-json", str(output)]
            )
            master = operator_workbook_sync.SheetTable(
                label="master",
                ref=operator_workbook_sync.SheetRef(
                    token="master-token",
                    url="",
                    sheet_id="master-sheet",
                    sheet_name="大表",
                    row_count=1,
                    column_count=1,
                ),
                headers={"id": 1},
                rows=[],
                last_nonblank_row=1,
            )
            empty_plan = {
                "append_rows": [],
                "image_copies": [],
                "status_header_updates": [],
                "status_updates": [],
                "result_updates": [],
                "already_in_master": [],
                "skipped": [],
                "blocking": {"image_risks": []},
            }
            profile = {
                "scenario_id": "test",
                "target_table_template": "{operator}-测试",
                "key_columns": ["id"],
                "_profile_path": "test.json",
            }

            with patch.object(operator_workbook_sync, "load_config", return_value={}), patch.object(
                operator_workbook_sync, "load_profile", return_value=profile
            ), patch.object(
                operator_workbook_sync, "resolve_contact_person", return_value="测试人"
            ), patch.object(
                operator_workbook_sync, "resolve_operator_root_folder", return_value="root-token"
            ), patch.object(
                operator_workbook_sync, "resolve_master_url", return_value="master-url"
            ), patch.object(
                operator_workbook_sync, "resolve_lark_cli", return_value="fake-cli"
            ), patch.object(
                operator_workbook_sync, "read_table", return_value=master
            ), patch.object(
                operator_workbook_sync,
                "resolve_operator_workbooks",
                return_value=([], [], ["测试主体"]),
            ), patch.object(
                operator_workbook_sync, "load_sources", return_value=([], [])
            ), patch.object(
                operator_workbook_sync, "build_plan", return_value=empty_plan
            ), patch.object(
                operator_workbook_sync,
                "write_append_rows",
                side_effect=AssertionError("unconfirmed run must not append rows"),
            ), patch.object(
                operator_workbook_sync,
                "write_image_copies",
                side_effect=AssertionError("unconfirmed run must not write images"),
            ), patch.object(
                operator_workbook_sync,
                "write_updates",
                side_effect=AssertionError("unconfirmed run must not write cells"),
            ):
                result = operator_workbook_sync.run(args)

            self.assertEqual(result, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
