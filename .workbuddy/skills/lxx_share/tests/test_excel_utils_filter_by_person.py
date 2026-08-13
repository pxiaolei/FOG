import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lxx_share.excel_utils import filter_by_person


class FilterByPersonTests(unittest.TestCase):
    def test_filters_operator_brand_rows_by_brand_city_person(self):
        mapping = {
            "city_to_zhuti": {},
            "brand_to_zhuti": {},
            "brand_city_to_zhuti": {},
            "zhuti_to_person": {},
            "all_zhuti": [],
            "all_cities": [],
            "all_brands": [],
            "all_persons": ["雷维亮", "薛银"],
            "operator_brand_rows": [
                {
                    "operator": "幸福千万家",
                    "brand": "幸福千万家",
                    "city": "福州市",
                    "contact_person": "雷维亮",
                },
                {
                    "operator": "幸福千万家",
                    "brand": "幸福千万家",
                    "city": "太原市",
                    "contact_person": "薛银",
                },
                {
                    "operator": "幸福千万家",
                    "brand": "幸福千万家",
                    "city": "重庆市",
                    "contact_person": "薛银",
                },
            ],
        }

        filtered, person_list = filter_by_person(mapping, ["雷维亮"])

        self.assertEqual(person_list, ["雷维亮"])
        self.assertEqual(filtered["all_zhuti"], ["幸福千万家"])
        self.assertEqual(
            filtered["brand_city_to_zhuti"][("幸福千万家", "福州市")],
            ["幸福千万家"],
        )
        self.assertEqual(
            filtered["brand_city_to_zhuti"][("幸福千万家", "太原市")],
            [],
        )
        self.assertEqual(
            filtered["brand_city_to_zhuti"][("幸福千万家", "重庆市")],
            [],
        )
        self.assertEqual(filtered["operator_brand_rows"], [
            {
                "operator": "幸福千万家",
                "brand": "幸福千万家",
                "city": "福州市",
                "contact_person": "雷维亮",
            }
        ])


if __name__ == "__main__":
    unittest.main()
