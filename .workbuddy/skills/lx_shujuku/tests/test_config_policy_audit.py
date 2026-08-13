import re
import sys
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import SimpleNamespace


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lx_shujuku.client import DataReportingClient, _parse_allowed_table_names
from lx_shujuku.query_policy import analyze_query_shape, ensure_readonly_sql


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

    def test_limit_inside_string_does_not_replace_top_level_limit(self):
        sql = ensure_readonly_sql(
            "SELECT city_name FROM honghu_order_data WHERE city_name = 'limit 999'",
            default_limit=50,
            max_limit=1000,
            allowed_tables={"honghu_order_data"},
        )

        self.assertTrue(sql.endswith("LIMIT 50"))

    def test_limit_inside_subquery_does_not_replace_top_level_limit(self):
        sql = ensure_readonly_sql(
            "SELECT * FROM (SELECT * FROM honghu_order_data LIMIT 5) t",
            default_limit=50,
            max_limit=1000,
            allowed_tables={"honghu_order_data"},
        )

        self.assertTrue(sql.endswith("LIMIT 50"))

    def test_query_shape_only_reports_top_level_clauses(self):
        shape = analyze_query_shape(
            "SELECT * FROM (SELECT * FROM honghu_order_data LIMIT 5) t "
            "ORDER BY city_name LIMIT 20 OFFSET 40"
        )

        self.assertEqual(shape["top_level_limit"], 20)
        self.assertEqual(shape["top_level_offset"], 40)
        self.assertTrue(shape["has_top_level_order_by"])


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
        self.assertEqual(audit["version"], 2)
        self.assertEqual(audit["question"], "查完单")
        self.assertEqual(audit["metric"], "brand_city_daily_completed_orders")
        self.assertEqual(audit["safe_sql"], client.seen_sql)
        self.assertTrue(audit["safe_sql"].endswith("LIMIT 100"))
        self.assertEqual(audit["row_count"], 1)
        self.assertTrue(audit["is_complete"])
        self.assertFalse(audit["possible_truncation"])
        self.assertEqual(len(audit["result_sha256"]), 64)
        self.assertEqual(
            audit["metric_contract"]["id"],
            "brand_city_daily_completed_orders",
        )
        self.assertEqual(audit["rows"][0]["city_name"], "上海市")

    def test_limit_boundary_is_not_reported_as_complete(self):
        class FakeClient(DataReportingClient):
            def __init__(self):
                self.base_url = "http://example.test"
                self.default_limit = 1
                self.max_limit = 1000
                self.schema = SimpleNamespace(table_names={"honghu_order_data"})

            def _execute_prepared_sql(self, safe_sql):
                return [{"city_name": "上海市"}]

        audit = FakeClient().execute_audited(
            "SELECT city_name FROM honghu_order_data"
        )

        self.assertIsNone(audit["is_complete"])
        self.assertTrue(audit["possible_truncation"])
        self.assertIn("可能被截断", " ".join(audit["warnings"]))

    def test_unknown_metric_is_rejected_before_query(self):
        class FakeClient(DataReportingClient):
            def __init__(self):
                self.base_url = "http://example.test"
                self.default_limit = 100
                self.max_limit = 1000
                self.schema = SimpleNamespace(table_names={"honghu_order_data"})

            def _execute_prepared_sql(self, safe_sql):
                self.fail("未知指标不应执行查询")

        with self.assertRaisesRegex(RuntimeError, "未知指标口径 ID"):
            FakeClient().execute_audited(
                "SELECT city_name FROM honghu_order_data",
                metric="not_a_metric",
            )

    def test_full_query_uses_double_read_and_count_verification(self):
        class FakeClient(DataReportingClient):
            def __init__(self):
                self.base_url = "http://example.test"
                self.default_limit = 100
                self.max_limit = 1000
                self.schema = SimpleNamespace(table_names={"honghu_order_data"})
                self.data = [
                    {"id": 1, "city_name": "上海市"},
                    {"id": 2, "city_name": "杭州市"},
                    {"id": 3, "city_name": "南京市"},
                ]

            def _execute_prepared_sql(self, safe_sql):
                if "__lx_total_rows" in safe_sql:
                    return [{"__lx_total_rows": len(self.data)}]
                match = re.search(r"LIMIT (\d+) OFFSET (\d+)$", safe_sql)
                if match is None:
                    raise AssertionError(f"未识别分页 SQL: {safe_sql}")
                size, offset = (int(value) for value in match.groups())
                return self.data[offset:offset + size]

        audit = FakeClient().execute_full_audited(
            "SELECT id, city_name FROM honghu_order_data ORDER BY id",
            page_size=2,
            max_rows=10,
        )

        self.assertEqual(audit["result_mode"], "full")
        self.assertTrue(audit["is_complete"])
        self.assertEqual(audit["total_rows"], 3)
        self.assertEqual(audit["verification"]["verification_passes"], 2)
        self.assertEqual(audit["verification"]["pages_per_pass"], 2)
        self.assertEqual(
            audit["verification"]["method"],
            "ordered_double_read_with_count",
        )
        self.assertEqual(audit["order_columns"], ["id"])

    def test_full_query_rejects_non_unique_order(self):
        class FakeClient(DataReportingClient):
            def __init__(self):
                self.base_url = "http://example.test"
                self.default_limit = 100
                self.max_limit = 1000
                self.schema = SimpleNamespace(table_names={"honghu_order_data"})

            def _execute_prepared_sql(self, safe_sql):
                if "__lx_total_rows" in safe_sql:
                    return [{"__lx_total_rows": 2}]
                return [
                    {"city_name": "上海市"},
                    {"city_name": "上海市"},
                ]

        with self.assertRaisesRegex(RuntimeError, "字段组合不唯一"):
            FakeClient().execute_full_audited(
                "SELECT city_name FROM honghu_order_data ORDER BY city_name",
                page_size=10,
                max_rows=10,
            )

    def test_full_single_row_aggregate_does_not_require_order_by(self):
        class FakeClient(DataReportingClient):
            def __init__(self):
                self.base_url = "http://example.test"
                self.default_limit = 100
                self.max_limit = 1000
                self.schema = SimpleNamespace(table_names={"honghu_order_data"})

            def _execute_prepared_sql(self, safe_sql):
                if "__lx_total_rows" in safe_sql:
                    return [{"__lx_total_rows": 1}]
                return [{"completed_order_count": 3}]

        audit = FakeClient().execute_full_audited(
            "SELECT SUM(completed_order_count) AS completed_order_count "
            "FROM honghu_order_data",
            page_size=10,
            max_rows=10,
        )

        self.assertTrue(audit["is_complete"])
        self.assertFalse(audit["order_by_present"])
        self.assertEqual(audit["order_columns"], [])
        self.assertEqual(
            audit["verification"]["method"],
            "single_row_double_read_with_count",
        )


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
