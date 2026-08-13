import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "feishu_sheets.py"
SPEC = importlib.util.spec_from_file_location("feishu_sheets", SCRIPT_PATH)
feishu = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["feishu_sheets"] = feishu
SPEC.loader.exec_module(feishu)


class FakeClient:
    def __init__(self):
        self.create_calls = []
        self.put_calls = []
        self.status_calls = 0
        self.get_calls = []
        self.info_calls = []
        self.inspect_calls = []
        self.info_result = {"sheets": [{"sheet_id": "sheet-id-1", "title": "Sheet1"}]}
        self.inspect_result = None
        self.get_result = None

    def status(self):
        self.status_calls += 1
        return {"ok": True, "identity": "user"}

    def workbook_create(self, title, **kwargs):
        self.create_calls.append((title, kwargs))
        return {"spreadsheet_token": "new-workbook"}

    def csv_put(self, **kwargs):
        self.put_calls.append(kwargs)
        return {"ok": True}

    def workbook_info(self, **kwargs):
        self.info_calls.append(kwargs)
        return self.info_result

    def workbook_inspect(self, **kwargs):
        self.inspect_calls.append(kwargs)
        if self.inspect_result is not None:
            return self.inspect_result
        title = self.create_calls[-1][0] if self.create_calls else ""
        return {"type": "sheet", "token": "new-workbook", "title": title}

    def csv_get(self, **kwargs):
        self.get_calls.append(kwargs)
        if self.get_result is not None:
            return self.get_result
        csv_text = self.put_calls[-1]["csv_text"] if self.put_calls else ""
        return {"csv": csv_text}

    @staticmethod
    def spreadsheet_token(result):
        return result["spreadsheet_token"]

    @staticmethod
    def sheet_properties(result):
        return result["sheets"]

    @staticmethod
    def csv_rows(result):
        return [row.split(",") for row in result["csv"].splitlines()]


class FeishuSheetsWriteGateTests(unittest.TestCase):
    def run_main(self, argv, client):
        output = io.StringIO()
        with (
            patch.object(sys, "argv", [str(SCRIPT_PATH), *argv]),
            patch.object(feishu, "_client", return_value=client),
            contextlib.redirect_stdout(output),
        ):
            feishu.main()
        return json.loads(output.getvalue())

    def test_status_remains_available_without_write_confirmation(self):
        client = FakeClient()

        result = self.run_main(["status"], client)

        self.assertEqual(client.status_calls, 1)
        self.assertEqual(result, {"ok": True, "identity": "user"})

    def test_csv_get_remains_available_without_write_confirmation(self):
        client = FakeClient()

        self.run_main(
            [
                "csv-get",
                "--spreadsheet-token",
                "sheet-token-1",
                "--sheet-id",
                "sheet-id-1",
                "--range",
                "A1:B2",
            ],
            client,
        )

        self.assertEqual(client.get_calls, [{"spreadsheet_token": "sheet-token-1", "url": "", "sheet_id": "sheet-id-1", "sheet_name": "", "range_text": "A1:B2"}])

    def test_create_workbook_without_confirmation_only_previews_and_keeps_target_unchanged(self):
        client = FakeClient()

        result = self.run_main(
            [
                "create-workbook",
                "--title",
                "每周运营表",
                "--folder-token",
                "folder-1",
                "--headers-json",
                '["城市", "完单"]',
            ],
            client,
        )

        self.assertEqual(client.create_calls, [])
        self.assertEqual(client.put_calls, [])
        self.assertEqual(result["title"], "每周运营表")
        self.assertEqual(result["headers"], ["城市", "完单"])

    def test_csv_put_dry_run_only_previews_and_keeps_target_unchanged(self):
        client = FakeClient()

        result = self.run_main(
            [
                "csv-put",
                "--spreadsheet-token",
                "sheet-token-1",
                "--sheet-id",
                "sheet-id-1",
                "--start-cell",
                "C5",
                "--csv",
                "城市,完单\\n上海,10",
                "--dry-run",
            ],
            client,
        )

        self.assertEqual(client.create_calls, [])
        self.assertEqual(client.put_calls, [])
        self.assertEqual(result["spreadsheet_token"], "sheet-token-1")
        self.assertEqual(result["sheet_id"], "sheet-id-1")
        self.assertEqual(result["start_cell"], "C5")

    def test_smoke_without_confirmation_only_previews_and_keeps_target_unchanged(self):
        client = FakeClient()

        result = self.run_main(
            ["smoke", "--title", "安全 smoke", "--folder-token", "folder-2"],
            client,
        )

        self.assertEqual(client.create_calls, [])
        self.assertEqual(client.put_calls, [])
        self.assertEqual(result["title"], "安全 smoke")
        self.assertEqual(result["start_cell"], "A1")

    def test_confirmed_create_workbook_calls_write_with_original_target(self):
        client = FakeClient()

        result = self.run_main(
            [
                "create-workbook",
                "--title",
                "每周运营表",
                "--folder-token",
                "folder-1",
                "--confirmed",
            ],
            client,
        )

        self.assertEqual(client.create_calls, [("每周运营表", {"folder_token": "folder-1", "headers": None, "values": None})])
        self.assertEqual(client.info_calls, [{"spreadsheet_token": "new-workbook"}])
        self.assertEqual(client.inspect_calls, [{"spreadsheet_token": "new-workbook"}])
        self.assertEqual(
            result["readback"],
            {
                "folder_readback": "API不提供创建后folder读回",
                "requested_folder_token": "[hidden]",
                "sheet_count": 1,
                "spreadsheet_token": "new-workbook",
                "title": "每周运营表",
                "type": "sheet",
            },
        )

    def test_confirmed_create_workbook_fails_when_workbook_info_cannot_read_created_token(self):
        client = FakeClient()
        client.info_result = {"sheets": []}

        with self.assertRaisesRegex(feishu.FeishuSheetsError, "缺少 sheet 列表"):
            self.run_main(
                ["create-workbook", "--title", "每周运营表", "--confirmed"],
                client,
            )

    def test_confirmed_create_workbook_reads_back_the_complete_initial_matrix(self):
        client = FakeClient()
        client.get_result = {"csv": "城市,完单\n上海,10"}

        result = self.run_main(
            [
                "create-workbook",
                "--title",
                "每周运营表",
                "--headers-json",
                '["城市", "完单"]',
                "--values-json",
                '[["上海", 10]]',
                "--confirmed",
            ],
            client,
        )

        self.assertEqual(
            client.get_calls,
            [
                {
                    "spreadsheet_token": "new-workbook",
                    "url": "",
                    "sheet_id": "sheet-id-1",
                    "sheet_name": "",
                    "range_text": "A1:B2",
                }
            ],
        )
        self.assertEqual(
            result["readback"]["initial_matrix"]["rows"],
            [["城市", "完单"], ["上海", "10"]],
        )

    def test_confirmed_create_workbook_rejects_initial_matrix_mismatch(self):
        client = FakeClient()
        client.get_result = {"csv": "城市,完单\n上海,9"}

        with self.assertRaisesRegex(feishu.FeishuSheetsError, "B2"):
            self.run_main(
                [
                    "create-workbook",
                    "--title",
                    "每周运营表",
                    "--headers-json",
                    '["城市", "完单"]',
                    "--values-json",
                    '[["上海", 10]]',
                    "--confirmed",
                ],
                client,
            )

    def test_confirmed_create_workbook_rejects_inspect_token_title_or_type_mismatch(self):
        cases = [
            ({"type": "sheet", "token": "other-workbook", "title": "每周运营表"}, "token"),
            ({"type": "sheet", "token": "new-workbook", "title": "错误标题"}, "标题"),
            ({"type": "docx", "token": "new-workbook", "title": "每周运营表"}, "类型"),
        ]

        for inspect_result, message in cases:
            with self.subTest(inspect_result=inspect_result):
                client = FakeClient()
                client.inspect_result = inspect_result
                with self.assertRaisesRegex(feishu.FeishuSheetsError, message):
                    self.run_main(
                        ["create-workbook", "--title", "每周运营表", "--confirmed"],
                        client,
                    )

    def test_confirmed_csv_put_calls_write_with_original_target(self):
        client = FakeClient()

        result = self.run_main(
            [
                "csv-put",
                "--spreadsheet-token",
                "sheet-token-1",
                "--sheet-id",
                "sheet-id-1",
                "--start-cell",
                "C5",
                "--csv",
                "城市,完单\n上海,10",
                "--confirmed",
            ],
            client,
        )

        self.assertEqual(client.put_calls[0]["spreadsheet_token"], "sheet-token-1")
        self.assertEqual(client.put_calls[0]["sheet_id"], "sheet-id-1")
        self.assertEqual(client.put_calls[0]["start_cell"], "C5")
        self.assertEqual(
            client.get_calls,
            [
                {
                    "spreadsheet_token": "sheet-token-1",
                    "url": "",
                    "sheet_id": "sheet-id-1",
                    "sheet_name": "",
                    "range_text": "C5:D6",
                }
            ],
        )
        self.assertEqual(result["readback"]["range"], "C5:D6")
        self.assertEqual(result["readback"]["rows"], [["城市", "完单"], ["上海", "10"]])

    def test_confirmed_csv_put_calculates_range_across_column_z(self):
        client = FakeClient()

        result = self.run_main(
            [
                "csv-put",
                "--url",
                "https://example.feishu.cn/sheets/sht1",
                "--sheet-name",
                "数据",
                "--start-cell",
                "Z9",
                "--csv",
                "A,B\n1,2",
                "--confirmed",
            ],
            client,
        )

        self.assertEqual(client.get_calls[0]["range_text"], "Z9:AA10")
        self.assertEqual(result["readback"]["range"], "Z9:AA10")

    def test_confirmed_csv_put_fails_when_any_readback_cell_mismatches(self):
        client = FakeClient()
        client.get_result = {"csv": "城市,完单\n上海,9"}

        with self.assertRaisesRegex(feishu.FeishuSheetsError, "D6"):
            self.run_main(
                [
                    "csv-put",
                    "--spreadsheet-token",
                    "sheet-token-1",
                    "--sheet-id",
                    "sheet-id-1",
                    "--start-cell",
                    "C5",
                    "--csv",
                    "城市,完单\n上海,10",
                    "--confirmed",
                ],
                client,
            )

    def test_confirmed_csv_put_rejects_unbound_or_ambiguous_target_before_write(self):
        cases = [
            ["csv-put", "--sheet-id", "sheet-id-1", "--csv", "a", "--confirmed"],
            [
                "csv-put",
                "--spreadsheet-token",
                "sheet-token-1",
                "--url",
                "https://example.feishu.cn/sheets/sht1",
                "--sheet-id",
                "sheet-id-1",
                "--csv",
                "a",
                "--confirmed",
            ],
            ["csv-put", "--spreadsheet-token", "sheet-token-1", "--csv", "a", "--confirmed"],
            [
                "csv-put",
                "--spreadsheet-token",
                "sheet-token-1",
                "--sheet-id",
                "sheet-id-1",
                "--sheet-name",
                "数据",
                "--csv",
                "a",
                "--confirmed",
            ],
        ]

        for argv in cases:
            with self.subTest(argv=argv):
                client = FakeClient()
                with self.assertRaisesRegex(feishu.FeishuSheetsError, "必须且只能提供"):
                    self.run_main(argv, client)
                self.assertEqual(client.put_calls, [])
                self.assertEqual(client.get_calls, [])

    def test_confirmed_smoke_keeps_create_write_and_readback_chain(self):
        client = FakeClient()

        result = self.run_main(["smoke", "--title", "安全 smoke", "--confirmed"], client)

        self.assertEqual(client.create_calls[0][0], "安全 smoke")
        self.assertEqual(client.put_calls[0]["spreadsheet_token"], "new-workbook")
        self.assertEqual(client.inspect_calls, [{"spreadsheet_token": "new-workbook"}])
        self.assertEqual(client.get_calls[0]["range_text"], "A1:B2")
        self.assertEqual(result["read_rows"], [["检查项", "结果"], ["普通表格写入", "ok"]])

    def test_confirmed_smoke_does_not_report_success_on_readback_mismatch(self):
        client = FakeClient()
        client.get_result = {"csv": "检查项,结果\n普通表格写入,failed"}

        with self.assertRaisesRegex(feishu.FeishuSheetsError, "B2"):
            self.run_main(["smoke", "--title", "安全 smoke", "--confirmed"], client)

    def test_write_flags_are_mutually_exclusive(self):
        commands = [
            ["create-workbook", "--title", "表", "--dry-run", "--confirmed"],
            ["csv-put", "--csv", "a", "--dry-run", "--confirmed"],
            ["smoke", "--dry-run", "--confirmed"],
        ]

        for argv in commands:
            with self.subTest(argv=argv), patch.object(sys, "argv", [str(SCRIPT_PATH), *argv]):
                with self.assertRaises(SystemExit) as exit_context:
                    feishu.build_parser().parse_args()
                self.assertEqual(exit_context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
