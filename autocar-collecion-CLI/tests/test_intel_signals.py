"""intel 信号映射单元测试"""

import unittest

from clauto.intel.signals import extract_brand_model, make_record_id, miit_to_row, news_to_row


class IntelSignalsTest(unittest.TestCase):
    def test_make_record_id_stable(self):
        a = make_record_id("miit", "https://example.com/a")
        b = make_record_id("miit", "https://example.com/a")
        c = make_record_id("miit", "https://example.com/b")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("clauto:miit:"))
        self.assertNotEqual(a, c)

    def test_extract_brand_model_from_news_title(self):
        brand, model = extract_brand_model("比亚迪海豹2026款正式上市，标配城市NOA")
        self.assertEqual(brand, "比亚迪")
        self.assertIsNotNone(model)
        self.assertIn("海豹", model)

    def test_news_to_row(self):
        row = news_to_row(
            {
                "title": "极氪007新款发布，续航升级",
                "url": "https://news.example/1",
                "date": "2026-06-01",
                "source": "汽车之家",
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["车企"], "极氪")
        self.assertEqual(row["发布类型"], "全新上市")
        self.assertEqual(row["_record_key"], "https://news.example/1")

    def test_miit_to_row_fallback(self):
        row = miit_to_row(
            {
                "title": "工业和信息化部关于发布新能源汽车目录的公告",
                "link": "https://miit.gov.cn/a",
                "date": "2026-06-10",
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["车企"], "待识别")
        self.assertEqual(row["发布类型"], "工信部信号")


if __name__ == "__main__":
    unittest.main()
