import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import split_by_zhuti  # noqa: E402


class SplitSafetyGateTests(unittest.TestCase):
    def test_default_preview_does_not_create_directories_move_source_or_connect_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "subject-split"
            input_dir = work_dir / "输入"
            input_dir.mkdir(parents=True)
            source = input_dir / "source.xlsx"
            source.write_bytes(b"unchanged")
            before = sorted(str(path.relative_to(work_dir)) for path in work_dir.rglob("*"))
            config = {
                "项目根目录": tmp,
                "工作目录": str(work_dir),
                "默认对接人": ["测试人"],
                "默认": {},
                "特定配置": [],
            }

            with patch.object(split_by_zhuti, "load_config", return_value=config), patch.object(
                split_by_zhuti,
                "load_company_mabiao",
                side_effect=AssertionError("preview must not connect to the company database"),
            ):
                result = split_by_zhuti.main(["--mode", "1", "--person", "测试人"])

            after = sorted(str(path.relative_to(work_dir)) for path in work_dir.rglob("*"))
            self.assertEqual(result, 0)
            self.assertEqual(source.read_bytes(), b"unchanged")
            self.assertEqual(after, before)
            self.assertFalse((work_dir / "输出").exists())
            self.assertFalse((work_dir / "原表存档").exists())

    def test_confirmed_and_dry_run_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            split_by_zhuti.main(["--confirmed", "--dry-run"])


if __name__ == "__main__":
    unittest.main()
