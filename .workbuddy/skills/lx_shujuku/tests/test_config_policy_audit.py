import sys
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import SimpleNamespace


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lx_shujuku.client import DataReportingClient, _parse_allowed_table_names
from lx_shujuku.query_policy import ensure_readonly_sql


class ConfigParsingTests(unittest.TestCase):
    def test_inline_comments_are_not_part_of_values(self):
        config = DataReportingClient._parse_simple_yaml(
            """
api:
  base_url: "http://example.test"  # internal host
  username: "alice"     # account name
  password: 'secret#value'  # hash inside quotes is value
timeout: 45  # seconds
default_limit: 25
max_limit: 200
"""
        )

        self.assertEqual(config["base_url"], "http://example.test")
        self.assertEqual(config["username"], "alice")
        self.assertEqual(config["password"], "secret#value")
        self.assertEqual(config["timeout"], 45)
        self.assertEqual(config["default_limit"], 25)
        self.assertEqual(config["max_limit"], 200)

    def test_configured_timeout_and_limits_are_respected(self):
        with NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
            f.write(
                """
api:
  base_url: "http://example.test"
  username: "alice"
  password: "secret"
timeout: 45
default_limit: 25
max_limit: 200
"""
            )
            config_path = f.name

        try:
            client = DataReportingClient(config_path=config_path)
        finally:
            Path(config_path).unlink(missing_ok=True)

        self.assertEqual(client.timeout, 45)
        self.assertEqual(client.default_limit, 25)
        self.assertEqual(client.max_limit, 200)


class QueryPolicyTests(unittest.TestCase):
    def test_select_gets_default_limit_and_uses_known_tables_only(self):
        sql = ensure_readonly_sql(
            "SELECT city_name FROM honghu_order_data",
            default_limit=100,
            max_limit=1000,
            allowed_tables={"honghu_order_data"},
        )

        self.assertEqual(sql, "SELECT city_name FROM honghu_order_data LIMIT 100")

    def test_unknown_table_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "表不在 schema 白名单中"):
            ensure_readonly_sql(
                "SELECT * FROM unknown_table LIMIT 10",
                default_limit=100,
                max_limit=1000,
                allowed_tables={"honghu_order_data"},
            )

    def test_select_into_outfile_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "禁止关键字"):
            ensure_readonly_sql(
                "SELECT * FROM honghu_order_data INTO OUTFILE '/tmp/x' LIMIT 1",
                default_limit=100,
                max_limit=1000,
                allowed_tables={"honghu_order_data"},
            )

    def test_show_is_limited_to_table_metadata(self):
        with self.assertRaisesRegex(RuntimeError, "SHOW 仅允许"):
            ensure_readonly_sql(
                "SHOW VARIABLES",
                default_limit=100,
                max_limit=1000,
                allowed_tables={"honghu_order_data"},
            )

    def test_backtick_identifier_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "反引号"):
            ensure_readonly_sql(
                "SELECT * FROM `unknown_table` LIMIT 10",
                default_limit=100,
                max_limit=1000,
                allowed_tables={"honghu_order_data"},
            )

    def test_comma_join_unknown_table_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "表不在 schema 白名单中"):
            ensure_readonly_sql(
                "SELECT * FROM honghu_order_data, unknown_table LIMIT 10",
                default_limit=100,
                max_limit=1000,
                allowed_tables={"honghu_order_data"},
            )


class AuditPackageTests(unittest.TestCase):
    def test_execute_audited_returns_reproducible_evidence(self):
        class FakeClient(DataReportingClient):
            def __init__(self):
                self.base_url = "http://example.test"
                self.default_limit = 100
                self.max_limit = 1000
                self.schema = SimpleNamespace(table_names={"honghu_order_data"})

            def _execute_prepared_sql(self, safe_sql):
                self.seen_sql = safe_sql
                return [{"city_name": "上海市", "completed_order_count": 1}]

        client = FakeClient()
        audit = client.execute_audited(
            "SELECT city_name, completed_order_count FROM honghu_order_data",
            question="查完单",
            metric="brand_city_daily_completed_orders",
        )

        self.assertEqual(audit["type"], "lx_shujuku.query_run")
        self.assertEqual(audit["question"], "查完单")
        self.assertEqual(audit["metric"], "brand_city_daily_completed_orders")
        self.assertEqual(audit["safe_sql"], client.seen_sql)
        self.assertTrue(audit["safe_sql"].endswith("LIMIT 100"))
        self.assertEqual(audit["row_count"], 1)
        self.assertEqual(audit["rows"][0]["city_name"], "上海市")


class TableDiscoveryTests(unittest.TestCase):
    def test_parse_allowed_table_names_from_server_error(self):
        message = (
            "查询失败: 表 [missing_table] 不在允许查询的范围内，"
            "仅支持以下表: [card_data, honghu_profit_data, operator_brand]"
        )

        self.assertEqual(
            _parse_allowed_table_names(message),
            ["card_data", "honghu_profit_data", "operator_brand"],
        )

    def test_list_tables_merges_show_tables_and_server_allowed_tables(self):
        class FakeClient(DataReportingClient):
            def __init__(self):
                self.schema = SimpleNamespace(table_names={"old_table"})

            def execute(self, sql, enforce_table_whitelist=True):
                if sql == "SHOW TABLES":
                    return [
                        {
                            "Tables_in_datareporting": "old_table",
                            "TABLE_COMMENT": "旧表",
                        }
                    ]
                if "lx_shujuku_table_probe_missing" in sql:
                    raise RuntimeError(
                        "查询失败: 表 [lx_shujuku_table_probe_missing] "
                        "不在允许查询的范围内，仅支持以下表: [old_table, new_table]"
                    )
                return []

        self.assertEqual(
            FakeClient().list_tables(),
            [
                {"name": "new_table", "comment": ""},
                {"name": "old_table", "comment": "旧表"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
