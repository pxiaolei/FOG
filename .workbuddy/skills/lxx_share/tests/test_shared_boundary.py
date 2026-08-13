import unittest
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[4]


class SharedBoundaryTests(unittest.TestCase):
    def test_private_skills_and_rds_entrypoints_are_absent(self):
        forbidden_skill_dirs = (
            "lx-zhoubao",
            "lx-hhbbu",
            "lx-dapanribao",
            "lx-celuehuodong",
            "lx-yuedufandian",
        )
        skills_root = PROJECT_ROOT / ".workbuddy" / "skills"
        for name in forbidden_skill_dirs:
            self.assertFalse((skills_root / name).exists(), name)

        lxx_share = skills_root / "lxx_share"
        for name in (
            "database.py",
            "query_builder.py",
            "hhdata_metrics.py",
            "metric_definitions.py",
            "contract_validation.py",
            "formatters.py",
            "config.py",
        ):
            self.assertFalse((lxx_share / name).exists(), name)

        public_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                lxx_share / "__init__.py",
                lxx_share / "SKILL.md",
                lxx_share / "agents" / "openai.yaml",
                PROJECT_ROOT / "tools" / "fog.py",
            )
        )
        for forbidden in ("DatabaseConnector", "MySQL RDS", "lx_hhbbu", "lx_dapanribao", "hhgongbu"):
            self.assertNotIn(forbidden, public_text)

        config = yaml.safe_load(
            (PROJECT_ROOT / "config" / "fog_config.yaml.example").read_text(encoding="utf-8")
        )
        self.assertNotIn("database", config)
        for key in ("lx_hhbbu", "lx_dapanribao", "lx_zhoubao"):
            self.assertNotIn(key, config.get("enabled_skills", {}))
            self.assertNotIn(key, config)


if __name__ == "__main__":
    unittest.main()
