import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_split_publish  # noqa: E402
import run_writeback  # noqa: E402
import sync_ids_incremental  # noqa: E402


class NongfuOutputSideEffectGateTests(unittest.TestCase):
    def test_existing_summary_blocks_publish_split_before_cli_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "summary.json"
            output.write_text("keep", encoding="utf-8")
            with patch.object(run_split_publish, "load_config", side_effect=AssertionError("must stop before client work")):
                with self.assertRaisesRegex(run_split_publish.NongfuError, "--overwrite --confirmed"):
                    run_split_publish.main([
                        "--source-url", "https://example.invalid/source", "--output-json", str(output),
                    ])
            self.assertEqual("keep", output.read_text(encoding="utf-8"))

    def test_existing_writeback_summary_blocks_before_cli_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "summary.json"
            output.write_text("keep", encoding="utf-8")
            with patch.object(run_writeback, "load_config", side_effect=AssertionError("must stop before client work")):
                with self.assertRaisesRegex(run_writeback.NongfuError, "--overwrite --confirmed"):
                    run_writeback.main(["--master-url", "https://example.invalid/master", "--output-json", str(output)])
            self.assertEqual("keep", output.read_text(encoding="utf-8"))

    def test_existing_incremental_summary_blocks_before_cli_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "summary.json"
            output.write_text("keep", encoding="utf-8")
            with patch.object(sync_ids_incremental, "load_config", side_effect=AssertionError("must stop before client work")):
                with self.assertRaisesRegex(sync_ids_incremental.NongfuError, "--overwrite --confirmed"):
                    sync_ids_incremental.main([
                        "--master-url", "https://example.invalid/master", "--topic-sheet-name", "topic",
                        "--contact-person", "测试人", "--output-json", str(output),
                    ])
            self.assertEqual("keep", output.read_text(encoding="utf-8"))

    def test_split_publish_unconfirmed_does_not_write_summary_or_notification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "summary.json"
            md_path = root / "notice.md"
            args = run_split_publish.build_parser().parse_args(
                [
                    "--source-url",
                    "https://example.invalid/source",
                    "--output-json",
                    str(json_path),
                    "--output-markdown",
                    str(md_path),
                ]
            )

            result = run_split_publish.write_outputs(
                {"dry_run": True},
                {"demo": "notice"},
                args,
                {},
                "demo",
            )

            self.assertEqual(result, {})
            self.assertFalse(json_path.exists())
            self.assertFalse(md_path.exists())

    def test_writeback_unconfirmed_does_not_write_output_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "writeback.json"
            args = run_writeback.build_parser().parse_args(
                ["--master-url", "https://example.invalid/master", "--output-json", str(output)]
            )

            written = run_writeback.write_output_file({"dry_run": True}, args, "demo")

            self.assertEqual(written, "")
            self.assertFalse(output.exists())

    def test_snapshot_path_lookup_is_side_effect_free_until_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original_root = sync_ids_incremental.PROJECT_ROOT
            try:
                sync_ids_incremental.PROJECT_ROOT = root
                path = sync_ids_incremental.snapshot_file("测试人", "topic")
            finally:
                sync_ids_incremental.PROJECT_ROOT = original_root

            self.assertFalse(path.parent.exists())

    def test_incremental_id_writeback_verifies_each_cell_by_readback(self):
        class FakeCli:
            def __init__(self):
                self.calls = []

            def sheets(self, args):
                self.calls.append(args)
                return {"data": {"annotated_csv": "测试品牌,测试城市,,,new-id\n"}}

        change = sync_ids_incremental.SyncChange(
            operator="测试主体",
            brand="测试品牌",
            city="测试城市",
            field="banner",
            master_row=3,
            cell="E3",
            old_value="(空)",
            new_value="new-id",
        )
        cli = FakeCli()

        checks = sync_ids_incremental.verify_changes(cli, "master-token", "sheet-id", [change])

        self.assertEqual(
            checks,
            [
                {
                    "cell": "E3",
                    "expected_brand": "测试品牌",
                    "actual_brand": "测试品牌",
                    "expected_city": "测试城市",
                    "actual_city": "测试城市",
                    "expected": "new-id",
                    "actual": "new-id",
                    "ok": True,
                }
            ],
        )
        self.assertEqual(cli.calls[0][0], "+csv-get")

    def test_incremental_id_writeback_detects_readback_mismatch(self):
        class FakeCli:
            def sheets(self, args):
                return {"data": {"annotated_csv": "测试品牌,测试城市,,,stale-id\n"}}

        change = sync_ids_incremental.SyncChange(
            operator="测试主体",
            brand="测试品牌",
            city="测试城市",
            field="banner",
            master_row=3,
            cell="E3",
            old_value="(空)",
            new_value="new-id",
        )

        checks = sync_ids_incremental.verify_changes(FakeCli(), "master-token", "sheet-id", [change])

        self.assertFalse(checks[0]["ok"])


if __name__ == "__main__":
    unittest.main()
