import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import sync_ids_incremental as sync  # noqa: E402
from run_split_publish import NongfuError, TargetWorkbook  # noqa: E402


class IncrementalCanonicalFieldTests(unittest.TestCase):
    def assert_field_change(self, field, expected_cell):
        changes = sync.diff(
            {("测试品牌", "测试城市"): {field: f"{field}-id"}},
            {"rows": {}},
            {("测试品牌", "测试城市"): 3},
            {("测试品牌", "测试城市"): {}},
            "测试主体",
        )

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].field, field)
        self.assertEqual(changes[0].cell, expected_cell)

    def test_diff_detects_new_banner_id(self):
        self.assert_field_change("banner", "E3")

    def test_diff_detects_new_henglan_id(self):
        self.assert_field_change("henglan", "F3")

    def test_diff_detects_new_kaiping_id(self):
        self.assert_field_change("kaiping", "G3")

    def test_diff_detects_new_sidebar_id(self):
        self.assert_field_change("sidebar", "H3")


class IncrementalDuplicateKeyTests(unittest.TestCase):
    def test_operator_sheet_duplicate_brand_city_key_is_blocking(self):
        class FakeCli:
            def sheets(self, args):
                return {
                    "data": {
                        "annotated_csv": (
                            "测试品牌,测试城市,,,banner-1,,,\n"
                            "测试品牌,测试城市,,,banner-2,,,"
                        )
                    }
                }

        target = TargetWorkbook("LX", "", "operator-token", "")
        with self.assertRaisesRegex(NongfuError, "重复品牌城市键"):
            sync.read_operator_ids(FakeCli(), target, "operator-sheet", "LX")

    def test_master_sheet_duplicate_brand_city_key_is_blocking(self):
        class FakeCli:
            def sheets(self, args):
                return {
                    "data": {
                        "annotated_csv": "测试品牌,测试城市\n测试品牌,测试城市"
                    }
                }

        with self.assertRaisesRegex(NongfuError, "重复品牌城市键"):
            sync.read_master_index(FakeCli(), "master-token", "master-sheet")

    def test_duplicate_brand_city_across_operator_sheets_is_blocking(self):
        targets = {
            operator: TargetWorkbook(
                operator=operator,
                folder_token=f"folder-{operator}",
                spreadsheet_token=f"token-{operator}",
                url=f"https://example.invalid/{operator}",
                existing_sheets={"topic": f"sheet-{operator}"},
            )
            for operator in ("主体A", "主体B")
        }
        with tempfile.TemporaryDirectory() as tmp:
            stderr = io.StringIO()
            stdout = io.StringIO()
            with patch.object(sync, "load_config", return_value={}), patch.object(
                sync, "resolve_lark_cli", return_value=Path("/fake/lark-cli")
            ), patch.object(sync, "LarkCli", return_value=object()), patch.object(
                sync, "choose_master_sheet", return_value=("master-token", "master-sheet")
            ), patch.object(
                sync, "read_master_index", return_value={("测试品牌", "测试城市"): 3}
            ), patch.object(
                sync,
                "read_master_existing_ids",
                return_value={("测试品牌", "测试城市"): {}},
            ), patch.object(sync, "discover_operator_targets", return_value=targets), patch.object(
                sync,
                "read_operator_ids",
                return_value=({("测试品牌", "测试城市"): {"banner": "new-id"}}, "A"),
            ), patch.object(sync, "snapshot_file", return_value=Path(tmp) / "snapshot.json"), patch.object(
                sync, "load_snapshot", return_value={"version": 1, "operators": {}}
            ), contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout), self.assertRaisesRegex(
                NongfuError, "跨主体表重复品牌城市键"
            ):
                sync.main(
                    [
                        "--master-url",
                        "https://example.invalid/master",
                        "--topic-sheet-name",
                        "topic",
                        "--contact-person",
                        "测试人",
                        "--operator-root-folder-token",
                        "root-token",
                        "--no-output-files",
                    ]
                )


class IncrementalReadbackTests(unittest.TestCase):
    def change(self):
        return sync.SyncChange(
            operator="测试主体",
            brand="测试品牌",
            city="测试城市",
            field="banner",
            master_row=3,
            cell="E3",
            old_value="(空)",
            new_value="new-id",
        )

    def test_verify_changes_requires_stable_brand_city_and_value(self):
        class FakeCli:
            def sheets(self, args):
                requested_range = args[args.index("--range") + 1]
                if requested_range == "E3":
                    return {"data": {"annotated_csv": "new-id"}}
                return {"data": {"annotated_csv": "错误品牌,测试城市,,,new-id"}}

        checks = sync.verify_changes(FakeCli(), "master-token", "master-sheet", [self.change()])

        self.assertFalse(checks[0]["ok"])

    def test_write_api_failure_has_no_success_log_or_snapshot_update(self):
        target = TargetWorkbook(
            operator="测试主体",
            folder_token="folder",
            spreadsheet_token="operator-token",
            url="https://example.invalid/operator",
            existing_sheets={"topic": "operator-sheet"},
        )
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_path = Path(tmp) / "snapshot.json"
            stderr = io.StringIO()
            with patch.object(sync, "load_config", return_value={}), patch.object(
                sync, "resolve_lark_cli", return_value=Path("/fake/lark-cli")
            ), patch.object(sync, "LarkCli", return_value=object()), patch.object(
                sync, "choose_master_sheet", return_value=("master-token", "master-sheet")
            ), patch.object(
                sync, "read_master_index", return_value={("测试品牌", "测试城市"): 3}
            ), patch.object(
                sync,
                "read_master_existing_ids",
                return_value={("测试品牌", "测试城市"): {}},
            ), patch.object(
                sync, "discover_operator_targets", return_value={"测试主体": target}
            ), patch.object(
                sync,
                "read_operator_ids",
                return_value=({("测试品牌", "测试城市"): {"banner": "new-id"}}, "A"),
            ), patch.object(sync, "snapshot_file", return_value=snapshot_path), patch.object(
                sync, "load_snapshot", return_value={"version": 1, "operators": {}}
            ), patch.object(
                sync, "write_changes", return_value=[{"cell": "E3", "value": "new-id", "ok": False}]
            ), patch.object(
                sync, "verify_changes", side_effect=AssertionError("readback must not run after write failure")
            ), contextlib.redirect_stderr(stderr), self.assertRaisesRegex(NongfuError, "写入返回失败"):
                sync.main(
                    [
                        "--master-url",
                        "https://example.invalid/master",
                        "--topic-sheet-name",
                        "topic",
                        "--contact-person",
                        "测试人",
                        "--operator-root-folder-token",
                        "root-token",
                        "--confirmed",
                        "--no-output-files",
                    ]
                )

            self.assertNotIn("成功", stderr.getvalue())
            self.assertNotIn("写入完成", stderr.getvalue())
            self.assertFalse(snapshot_path.exists())

    def test_readback_mismatch_has_no_success_log_or_snapshot_update(self):
        target = TargetWorkbook(
            operator="测试主体",
            folder_token="folder",
            spreadsheet_token="operator-token",
            url="https://example.invalid/operator",
            existing_sheets={"topic": "operator-sheet"},
        )
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_path = Path(tmp) / "snapshot.json"
            stderr = io.StringIO()
            with patch.object(sync, "load_config", return_value={}), patch.object(
                sync, "resolve_lark_cli", return_value=Path("/fake/lark-cli")
            ), patch.object(sync, "LarkCli", return_value=object()), patch.object(
                sync, "choose_master_sheet", return_value=("master-token", "master-sheet")
            ), patch.object(
                sync, "read_master_index", return_value={("测试品牌", "测试城市"): 3}
            ), patch.object(
                sync,
                "read_master_existing_ids",
                return_value={("测试品牌", "测试城市"): {}},
            ), patch.object(
                sync, "discover_operator_targets", return_value={"测试主体": target}
            ), patch.object(
                sync,
                "read_operator_ids",
                return_value=({("测试品牌", "测试城市"): {"banner": "new-id"}}, "A"),
            ), patch.object(sync, "snapshot_file", return_value=snapshot_path), patch.object(
                sync, "load_snapshot", return_value={"version": 1, "operators": {}}
            ), patch.object(
                sync, "write_changes", return_value=[{"cell": "E3", "value": "new-id", "ok": True}]
            ), patch.object(
                sync,
                "verify_changes",
                return_value=[{"cell": "E3", "expected": "new-id", "actual": "stale", "ok": False}],
            ), contextlib.redirect_stderr(stderr), self.assertRaisesRegex(NongfuError, "写后验证失败"):
                sync.main(
                    [
                        "--master-url",
                        "https://example.invalid/master",
                        "--topic-sheet-name",
                        "topic",
                        "--contact-person",
                        "测试人",
                        "--operator-root-folder-token",
                        "root-token",
                        "--confirmed",
                        "--no-output-files",
                    ]
                )

            self.assertNotIn("成功", stderr.getvalue())
            self.assertNotIn("写入完成", stderr.getvalue())
            self.assertFalse(snapshot_path.exists())


if __name__ == "__main__":
    unittest.main()
