import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_monthly_rebate.py"
SPEC = importlib.util.spec_from_file_location("run_monthly_rebate", SCRIPT_PATH)
rebate = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["run_monthly_rebate"] = rebate
SPEC.loader.exec_module(rebate)


class RebateLogicTest(unittest.TestCase):
    def test_scale_rate_boundaries(self):
        tiers = [
            {"min": 2000, "max": 10000, "rate": 0.003, "name": "0.2万-1万"},
            {"min": 10000, "max": 30000, "rate": 0.005, "name": "1万-3万"},
            {"min": 30000, "max": 60000, "rate": 0.007, "name": "3万-6万"},
            {"min": 60000, "max": 100000, "rate": 0.01, "name": "6万-10万"},
            {"min": 100000, "max": None, "rate": 0.012, "name": "10万+"},
        ]
        self.assertEqual(rebate.scale_rate_for_base(1999, tiers), (0.0, "未达规模阶梯"))
        self.assertEqual(rebate.scale_rate_for_base(2000, tiers), (0.003, "0.2万-1万"))
        self.assertEqual(rebate.scale_rate_for_base(10000, tiers), (0.005, "1万-3万"))
        self.assertEqual(rebate.scale_rate_for_base(30000, tiers), (0.007, "3万-6万"))
        self.assertEqual(rebate.scale_rate_for_base(60000, tiers), (0.01, "6万-10万"))
        self.assertEqual(rebate.scale_rate_for_base(100000, tiers), (0.012, "10万+"))

    def test_scale_basis_uses_operator_daily_completed_orders(self):
        self.assertAlmostEqual(
            rebate.scale_basis_from_completed_orders(
                310000,
                "2026-05",
                {"basis": "operator_daily_completed_orders"},
            ),
            10000,
        )

    def test_youxing_scope_is_excluded_from_travel_orders(self):
        scope_rows = [
            rebate.ScopeRow("拼哒出行", "拼哒出行", "上海市", "雷维亮"),
            rebate.ScopeRow("拼哒出行", "拼哒优行", "海口市", "雷维亮"),
            rebate.ScopeRow("拼哒出行", "逸乘优行", "济南市", "雷维亮"),
        ]
        youxing_targets = {
            "拼哒优行": rebate.YouxingTarget("拼哒优行", [], [], {}),
        }

        result = rebate.exclude_youxing_scope(scope_rows, youxing_targets)

        self.assertEqual(result, [scope_rows[0]])

    def test_monthly_threshold_can_use_operator_daily_orders(self):
        value = rebate.completed_for_threshold_basis(
            "operator_daily_completed_orders",
            completed=896,
            operator_completed=310000,
            month="2026-05",
            target_rules={"completed_target_basis": "daily_average"},
            config_key="monthly_min_orders_basis",
        )

        self.assertEqual(value, 10000)

    def test_rate_delta_from_target_label(self):
        self.assertAlmostEqual(rebate.rate_delta_from_label("T"), 0.0)
        self.assertAlmostEqual(rebate.rate_delta_from_label("-"), 0.0)
        self.assertAlmostEqual(rebate.rate_delta_from_label("T+0.1%"), 0.001)
        self.assertAlmostEqual(rebate.rate_delta_from_label("T-0.3%"), -0.003)
        self.assertAlmostEqual(rebate.rate_delta_from_label("0.5%"), 0.005)

    def test_month_helpers(self):
        self.assertEqual(rebate.month_label("2026-05"), "2026年5月")
        self.assertEqual(rebate.previous_month("2026-05"), "2026-04")
        self.assertEqual(rebate.previous_month("2026-01"), "2025-12")
        self.assertEqual(rebate.days_in_month("2026-05"), 31)
        self.assertAlmostEqual(
            rebate.completed_orders_for_target(3100, "2026-05", {"completed_target_basis": "daily_average"}),
            100,
        )
        self.assertEqual(
            rebate.completed_orders_for_target(3100, "2026-05", {"completed_target_basis": "monthly_total"}),
            3100,
        )

    def test_choose_monthly_delta_uses_highest_hit_tier(self):
        target = rebate.TravelTarget(
            operator="主体",
            brand="品牌",
            first_target=100,
            second_target=200,
            third_target=300,
            first_miss_label="T-0.1%",
            first_hit_label="T",
            second_hit_label="T+0.1%",
            third_hit_label="T+0.3%",
            assessment_mode="",
            process_coefficient=1,
            extra_rate=0,
            raw_payload={},
        )
        self.assertEqual(rebate.choose_monthly_delta(99, target), (-0.001, "一档未达成"))
        self.assertEqual(rebate.choose_monthly_delta(100, target), (0.0, "一档"))
        self.assertEqual(rebate.choose_monthly_delta(250, target), (0.001, "二档"))
        self.assertEqual(rebate.choose_monthly_delta(300, target), (0.003, "三档"))

    def test_billing_filters_apply_after_import_agg(self):
        rules = {
            "billing_base": {
                "exclude_tr_types": ["强制共补"],
                "exclude_channels": ["灵犀PBD"],
            }
        }
        owner = {
            ("品牌A", "上海"): rebate.ScopeRow(
                operator="主体A",
                brand="品牌A",
                city="上海",
                contact_person="雷维亮",
            )
        }
        import_agg = {
            ("Sheet1", "2026-05-01", "品牌A", "上海", "普通", "自然"): rebate.BillingImportAgg(300, 30, 2),
            ("Sheet1", "2026-05-01", "品牌A", "上海", "强制共补", "自然"): rebate.BillingImportAgg(100, 10, 1),
            ("Sheet2", "2026-05-02", "品牌A", "上海", "普通", "灵犀PBD"): rebate.BillingImportAgg(200, 20, 1),
            ("Sheet1", "2026-05-01", "品牌B", "上海", "普通", "自然"): rebate.BillingImportAgg(999, 0, 1),
        }

        by_city, by_pair = rebate.build_billing_from_import_agg(import_agg, rules, owner)

        self.assertEqual(by_city[("品牌A", "上海")].gross_all, 600)
        self.assertEqual(by_pair[("主体A", "品牌A")].gross_all, 600)
        self.assertEqual(by_city[("品牌A", "上海")].gross_receivable, 300)
        self.assertEqual(by_city[("品牌A", "上海")].spring_service_fee, 30)
        self.assertEqual(by_city[("品牌A", "上海")].rebate_base_before_open_city, 270)
        self.assertEqual(by_city[("品牌A", "上海")].rebate_base, 270)
        self.assertEqual(by_city[("品牌A", "上海")].filtered_row_count, 2)

    def test_open_city_period_excludes_billing_base(self):
        rules = {
            "billing_base": {
                "exclude_tr_types": [],
                "exclude_channels": [],
            }
        }
        owner = {
            ("品牌A", "上海"): rebate.ScopeRow("主体A", "品牌A", "上海", "雷维亮"),
        }
        import_agg = {
            ("Sheet1", "2026-05-01", "品牌A", "上海", "普通", "自然"): rebate.BillingImportAgg(100, 10, 1),
            ("Sheet1", "2026-05-20", "品牌A", "上海", "普通", "自然"): rebate.BillingImportAgg(200, 20, 1),
        }
        periods = {("品牌A", "上海"): [(rebate.date(2026, 5, 1), rebate.date(2026, 5, 18))]}

        by_city, by_pair = rebate.build_billing_from_import_agg(import_agg, rules, owner, periods)

        self.assertEqual(by_city[("品牌A", "上海")].rebate_base_before_open_city, 270)
        self.assertEqual(by_city[("品牌A", "上海")].open_city_excluded_base, 90)
        self.assertEqual(by_city[("品牌A", "上海")].rebate_base, 180)
        self.assertEqual(by_pair[("主体A", "品牌A")].rebate_base, 180)

    def test_redline_missing_city_can_pass_with_reason(self):
        redline = {
            "type": "sheet_ratio_all",
            "sheet": "协同指标",
            "brand_column": "品牌",
            "city_column": "城市",
            "value_column": "供需策略参与率",
            "threshold": 1.0,
            "missing_as_pass": True,
        }
        scope_rows = [
            rebate.ScopeRow("主体", "品牌A", "上海", "雷维亮"),
            rebate.ScopeRow("主体", "品牌A", "北京", "雷维亮"),
        ]
        process_rows = {
            "协同指标": [
                {"品牌": "品牌A", "城市": "上海", "供需策略参与率": 1.0},
            ]
        }

        value_text, passed, reason = rebate.evaluate_redline(redline, scope_rows, process_rows)

        self.assertTrue(passed)
        self.assertIn("缺失按100%=1", value_text)
        self.assertIn("无数据按100%通过", reason)

    def test_tsh_growth_uses_daily_average(self):
        metric = {
            "key": "tsh_growth",
            "sheet": "TSH",
            "date_column": "日期(月)",
            "brand_column": "品牌名称",
            "city_column": "城市名称",
            "value_column": "在线时长(小时)",
            "threshold": 0.03,
        }
        scope_rows = [rebate.ScopeRow("主体", "品牌A", "上海市", "雷维亮")]
        process_rows = {
            "TSH": [
                {"日期(月)": "2026-05", "品牌名称": "品牌A", "城市名称": "上海市", "在线时长(小时)": 31 * 110},
                {"日期(月)": "2026-04", "品牌名称": "品牌A", "城市名称": "上海市", "在线时长(小时)": 30 * 100},
            ]
        }

        value_text, passed, growth, reason = rebate.evaluate_tsh_growth(metric, "2026-05", scope_rows, process_rows)

        self.assertEqual(value_text, "10.00%")
        self.assertTrue(passed)
        self.assertAlmostEqual(growth, 0.1)
        self.assertEqual(reason, "")

    def test_zero_denominator_can_pass_as_100_percent(self):
        metric = {
            "sheet": "先锋司机",
            "brand_column": "品牌名称",
            "city_column": "城市",
            "numerator_column": "上线司机",
            "denominator_column": "司机数",
            "zero_denominator_as_pass": True,
        }
        scope_rows = [rebate.ScopeRow("主体", "安安用车", "威海市", "雷维亮")]
        process_rows = {
            "先锋司机": [
                {"品牌名称": "安安用车", "城市": "威海市", "上线司机": 0, "司机数": 0},
            ]
        }

        value_text, passed, ratio, reason = rebate.evaluate_ratio_from_sums(
            metric,
            scope_rows,
            process_rows,
            by_city=True,
        )

        self.assertEqual(value_text, "100.00%")
        self.assertTrue(passed)
        self.assertEqual(ratio, 1.0)
        self.assertIn("分母为0", reason)

    def test_process_metric_matches_brand_alias(self):
        metric = {
            "sheet": "司机客服接起率",
            "brand_column": "商家名称",
            "numerator_column": "接起量",
            "denominator_column": "进线量",
            "threshold": 0.8,
        }
        scope_rows = [rebate.ScopeRow("拼哒出行", "拼哒出行", "上海市", "雷维亮")]
        process_rows = {
            "司机客服接起率": [
                {"商家名称": "拼哒约车", "接起量": 90, "进线量": 100},
            ]
        }
        aliases = rebate.build_brand_alias_groups({"brand_aliases": {"拼哒出行": ["拼哒约车"]}})

        value_text, passed, ratio, reason = rebate.evaluate_ratio_from_sums(
            metric,
            scope_rows,
            process_rows,
            by_city=False,
            brand_alias_groups=aliases,
        )

        self.assertEqual(value_text, "90.00%")
        self.assertTrue(passed)
        self.assertAlmostEqual(ratio, 0.9)
        self.assertEqual(reason, "")

    def test_process_rebate_threshold_uses_operator_total_orders(self):
        process_rules = {
            "redlines": [],
            "metrics": [
                {
                    "key": "driver_service_answer_rate",
                    "name": "司机客服接起率",
                    "type": "ratio_from_sums_by_brand",
                    "sheet": "司机客服接起率",
                    "brand_column": "商家名称",
                    "numerator_column": "接起量",
                    "denominator_column": "进线量",
                    "threshold": 0.8,
                    "rate": 0.001,
                    "apply_coefficient": True,
                }
            ],
        }
        target_rules = {"min_orders_for_process_rebate": 2000}
        scope_rows = [rebate.ScopeRow("拼哒出行", "逸乘出行", "丽水市", "雷维亮")]
        process_rows = {
            "司机客服接起率": [
                {"商家名称": "逸乘特惠", "接起量": 90, "进线量": 100},
            ]
        }
        aliases = rebate.build_brand_alias_groups({"brand_aliases": {"逸乘出行": ["逸乘特惠"]}})

        total_rate, status, details, completion_rate = rebate.evaluate_process(
            "2026-05",
            ("拼哒出行", "逸乘出行"),
            scope_rows,
            completed_orders=896,
            process_threshold_orders=3000,
            process_coefficient=1,
            process_rules=process_rules,
            target_rules=target_rules,
            process_rows=process_rows,
            brand_alias_groups=aliases,
        )

        self.assertEqual(status, "通过")
        self.assertAlmostEqual(total_rate, 0.001)
        self.assertAlmostEqual(completion_rate, 1.0)
        self.assertEqual(details[0].metric_value, "90.00%")
        self.assertEqual(details[0].reason, "")

    def test_process_completion_excludes_pioneer_extra_and_coefficient(self):
        process_rules = {
            "redlines": [],
            "metrics": [
                {"key": "tsh", "name": "TSH", "type": "tsh_growth", "sheet": "TSH", "date_column": "日期(月)", "brand_column": "品牌", "city_column": "城市", "value_column": "TSH", "threshold": 0.03, "rate": 0.002, "apply_coefficient": True},
                {"key": "pioneer", "name": "先锋", "type": "tiered_ratio_from_sums", "sheet": "先锋司机", "brand_column": "品牌", "city_column": "城市", "numerator_column": "上线", "denominator_column": "司机", "zero_denominator_as_pass": True, "tiers": [{"min": 0.8, "max": 0.83, "rate": 0.002}, {"min": 0.83, "max": None, "rate": 0.002, "extra_rate": 0.002, "extra_apply_coefficient": False}]},
                {"key": "service", "name": "客服", "type": "ratio_from_sums_by_brand", "sheet": "客服", "brand_column": "品牌", "numerator_column": "接起", "denominator_column": "进线", "threshold": 0.8, "rate": 0.001, "apply_coefficient": True},
            ],
        }
        scope_rows = [rebate.ScopeRow("主体", "品牌A", "上海市", "雷维亮")]
        process_rows = {
            "TSH": [
                {"日期(月)": "2026-05", "品牌": "品牌A", "城市": "上海市", "TSH": 31 * 90},
                {"日期(月)": "2026-04", "品牌": "品牌A", "城市": "上海市", "TSH": 30 * 100},
            ],
            "先锋司机": [
                {"品牌": "品牌A", "城市": "上海市", "上线": 0, "司机": 0},
            ],
            "客服": [
                {"品牌": "品牌A", "接起": 50, "进线": 100},
            ],
        }

        total_rate, status, details, completion_rate = rebate.evaluate_process(
            "2026-05",
            ("主体", "品牌A"),
            scope_rows,
            completed_orders=3000,
            process_threshold_orders=3000,
            process_coefficient=2,
            process_rules=process_rules,
            target_rules={"min_orders_for_process_rebate": 2000},
            process_rows=process_rows,
        )

        self.assertEqual(status, "通过")
        self.assertAlmostEqual(total_rate, 0.006)
        self.assertAlmostEqual(completion_rate, 0.4)
        self.assertEqual(details[1].metric_value, "100.00%")

    def test_operator_aggregate_target_sums_tiers(self):
        targets = [
            rebate.TravelTarget("易惠出行", "易惠出行", 100, 200, 300, "T-0.1%", "T", "T+0.1%", "T+0.2%", "聚合考核", 1, 0, {}),
            rebate.TravelTarget("易惠出行", "安安用车", 10, 20, 30, "T-0.1%", "T", "T+0.1%", "T+0.2%", "聚合考核", 1, 0, {}),
        ]
        validations = []

        target = rebate.combine_operator_aggregate_target("易惠出行", targets, validations)

        self.assertEqual(target.first_target, 110)
        self.assertEqual(target.second_target, 220)
        self.assertEqual(target.third_target, 330)
        self.assertEqual(validations, [])

    def test_scope_overrides_reassign_and_include_rows(self):
        scope_rows = [
            rebate.ScopeRow("方舟行武汉", "方舟行", "武汉市", "雷维亮"),
        ]
        validations = []
        rules = {
            "scope": {
                "reassign_rows": [
                    {
                        "from_operator_entity": "方舟行武汉",
                        "from_brand_name": "方舟行",
                        "from_city_name": "武汉市",
                        "operator_entity": "江豚出行",
                        "brand_name": "方舟行",
                        "contact_person": "雷维亮",
                    }
                ],
                "include_rows": [
                    {
                        "operator_entity": "江豚出行",
                        "brand_name": "安安用车",
                        "city_name": "威海市",
                        "contact_person": "雷维亮",
                    }
                ],
            }
        }

        result = rebate.apply_scope_overrides(scope_rows, rules, validations)

        self.assertIn(rebate.ScopeRow("江豚出行", "方舟行", "武汉市", "雷维亮"), result)
        self.assertIn(rebate.ScopeRow("江豚出行", "安安用车", "威海市", "雷维亮"), result)
        self.assertNotIn(rebate.ScopeRow("方舟行武汉", "方舟行", "武汉市", "雷维亮"), result)

    def test_open_city_reward_matches_scope(self):
        rows = [
            rebate.OpenCityRow(
                sheet_name="Sheet2",
                brand="品牌A",
                city="上海",
                settlement_type="支出",
                settlement_unit="单位",
                settlement_item="开城奖励",
                open_date="2026-05-01",
                incentive_period="3个月",
                rate=0.03,
                settlement_period="2026-05",
                rebate_basis=1000,
                reward_amount=30,
                remark1="",
                remark2="",
                raw_payload={},
            ),
            rebate.OpenCityRow(
                sheet_name="Sheet2",
                brand="品牌B",
                city="北京",
                settlement_type="支出",
                settlement_unit="单位",
                settlement_item="开城奖励",
                open_date="2026-05-01",
                incentive_period="3个月",
                rate=0.03,
                settlement_period="2026-05",
                rebate_basis=1000,
                reward_amount=50,
                remark1="",
                remark2="",
                raw_payload={},
            ),
            rebate.OpenCityRow(
                sheet_name="Sheet2",
                brand="品牌A",
                city="上海",
                settlement_type="收入",
                settlement_unit="单位",
                settlement_item="开城奖励",
                open_date="2026-05-01",
                incentive_period="3个月",
                rate=0.03,
                settlement_period="2026-05",
                rebate_basis=1000,
                reward_amount=99,
                remark1="",
                remark2="",
                raw_payload={},
            ),
        ]
        owner = {
            ("品牌A", "上海"): rebate.ScopeRow("主体A", "品牌A", "上海", "雷维亮"),
        }
        validations = []
        rules = {
            "open_city_reward": {
                "settlement_type_include": ["支出"],
                "settlement_item_include": ["开城奖励"],
            }
        }

        result = rebate.build_open_city_by_pair(rows, rules, owner, validations)

        self.assertEqual(result[("主体A", "品牌A")], 30)
        self.assertEqual(len(validations), 1)
        self.assertEqual(validations[0].category, "开城奖励无法匹配公司库")

    def test_open_city_period_warns_and_skips_blank_period(self):
        rows = [
            rebate.OpenCityRow(
                sheet_name="Sheet2",
                brand="品牌A",
                city="上海",
                settlement_type="支出",
                settlement_unit="单位",
                settlement_item="开城奖励",
                open_date="2026-05-01",
                incentive_period="3个月",
                rate=0.03,
                settlement_period="2026-05",
                rebate_basis=1000,
                reward_amount=30,
                remark1="",
                remark2="",
                raw_payload={},
            )
        ]
        owner = {
            ("品牌A", "上海"): rebate.ScopeRow("主体A", "品牌A", "上海", "雷维亮"),
        }
        validations = []
        rules = {
            "open_city_reward": {
                "exclude_billing_base": True,
                "period_column": "备注1",
                "invalid_period_policy": "warn",
                "settlement_type_include": ["支出"],
                "settlement_item_include": ["开城奖励"],
            }
        }

        result = rebate.build_open_city_periods(rows, rules, owner, validations)

        self.assertEqual(result, {})
        self.assertEqual(len(validations), 1)
        self.assertEqual(validations[0].category, "开城周期无法解析")


if __name__ == "__main__":
    unittest.main()
