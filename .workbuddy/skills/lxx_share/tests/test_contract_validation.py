import unittest
from pathlib import Path

from lxx_share.contract_validation import ContractValidator


def project_root() -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        if (parent / "contracts" / "schema" / "contract-index.json").exists():
            return parent
    raise RuntimeError("project root not found")


class ContractValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = ContractValidator(project_root())

    def test_hhdata_contract_accepts_exact_headers(self):
        contract = self.validator.source_contract("hhdata__fact_daily_metrics")
        result = self.validator.validate_dataframe(
            "hhdata__fact_daily_metrics",
            contract["expected_headers"],
            file_name="valid.xlsx",
            data_type="hhdata",
        )
        self.assertTrue(result["pass"])

    def test_missing_source_header_fails(self):
        contract = self.validator.source_contract("hhdata__fact_daily_metrics")
        headers = [header for header in contract["expected_headers"] if header != "完单数"]
        result = self.validator.validate_dataframe(
            "hhdata__fact_daily_metrics",
            headers,
            file_name="missing.xlsx",
            data_type="hhdata",
        )
        self.assertFalse(result["pass"])
        self.assertIn("完单数", result["missing_fields"])

    def test_header_order_mismatch_fails(self):
        contract = self.validator.source_contract("hhdata__fact_daily_metrics")
        headers = list(contract["expected_headers"])
        headers[1], headers[2] = headers[2], headers[1]
        result = self.validator.validate_dataframe(
            "hhdata__fact_daily_metrics",
            headers,
            file_name="wrong-order.xlsx",
            data_type="hhdata",
        )
        self.assertFalse(result["pass"])
        self.assertTrue(result["order_mismatches"])

    def test_target_write_column_must_exist_in_table_contract(self):
        result = self.validator.validate_target_columns(
            "hhdata__fact_daily_metrics",
            ["date_day", "brand_name"],
        )
        self.assertFalse(result["pass"])
        self.assertEqual(result["target_missing_columns"], ["brand_name"])

    def test_lxdata_date_alias_uses_explicit_template_version(self):
        contract = self.validator.source_contract("lxdata__fact_orders")
        headers = list(contract["importer_expected_headers"])
        headers[0] = "日期"
        result = self.validator.validate_dataframe(
            "lxdata__fact_orders",
            headers,
            file_name="alias.xlsx",
            data_type="订单数据",
        )
        self.assertTrue(result["pass"])
        self.assertEqual(result["header"]["accepted_version"], "date_alias")
        self.assertEqual(result["header"]["column_aliases"], {"日期": "日期(天)"})

    def test_lxdata_missing_old_online_duration_is_explicitly_filled(self):
        contract = self.validator.source_contract("lxdata__fact_driver_force")
        headers = [
            header for header in contract["importer_expected_headers"]
            if header != "在线时长(旧)(小时)"
        ]
        result = self.validator.validate_dataframe(
            "lxdata__fact_driver_force",
            headers,
            file_name="without_old_duration.xlsx",
            data_type="运力数据",
        )
        self.assertTrue(result["pass"])
        self.assertEqual(result["header"]["accepted_version"], "without_online_duration_old")
        self.assertEqual(result["header"]["fill_missing_headers"], ["在线时长(旧)(小时)"])

    def test_lxdata_order_marketing_flow_platform_subsidy_alias(self):
        contract = self.validator.source_contract("lxdata__fact_order_marketing")
        headers = [
            "流量平台补贴金额(元)" if header == "平台补贴金额(元)" else header
            for header in contract["importer_expected_headers"]
        ]
        result = self.validator.validate_dataframe(
            "lxdata__fact_order_marketing",
            headers,
            file_name="flow_alias.xlsx",
            data_type="活动营销数据",
        )
        self.assertTrue(result["pass"])
        self.assertEqual(result["header"]["accepted_version"], "flow_platform_subsidy_alias")
        self.assertEqual(
            result["header"]["column_aliases"],
            {"流量平台补贴金额(元)": "平台补贴金额(元)"},
        )

    def test_lxdata_coupon_activity_alias_version_is_explicit(self):
        contract = self.validator.source_contract("lxdata__fact_coupon_marketing")
        headers = []
        aliases = {
            "日期(天)": "日期",
            "商品id": "活动id",
            "商品名称": "活动名称",
            "核销订单数": "卡核销的订单数",
            "核销订单GMV（元）": "卡核销的订单GMV（元）",
            "代理商补贴金额（元）": "代理商承担金额（元）",
        }
        for header in contract["importer_expected_headers"]:
            headers.append(aliases.get(header, header))
        result = self.validator.validate_dataframe(
            "lxdata__fact_coupon_marketing",
            headers,
            file_name="coupon_activity_alias.xlsx",
            data_type="卡券营销数据",
        )
        self.assertTrue(result["pass"])
        self.assertEqual(result["header"]["accepted_version"], "activity_coupon_alias")
        self.assertEqual(result["header"]["column_aliases"]["活动id"], "商品id")


if __name__ == "__main__":
    unittest.main()
