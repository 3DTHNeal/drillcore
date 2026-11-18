"""Tests for reading the figures a page in Chinese counts in 万 and 亿."""
import unittest

import support  # noqa: F401

from drillcore import cjk


class InDigits(unittest.TestCase):
    def test_a_number_against_its_unit_is_written_out_in_full(self):
        for text, read in (("营收突破37亿元", "营收突破 3700000000 元"), ("出货260万台", "出货 2600000 台"),
                           ("净利润912.56万元", "净利润 9125600 元"), ("营业收入 48,210.35 万元", "营业收入 482103500 元"),
                           ("收入7.25亿元、7.31亿元", "收入 725000000 元、731000000 元"), ("融资3千万元", "融资 30000000 元"),
                           ("营收100万亿韩元", "营收 100000000000000 韩元"), ("接近 30 亿元", "接近 3000000000 元")):
            with self.subTest(text):
                self.assertEqual(cjk.in_digits(text), read)

    def test_a_range_may_give_its_unit_once(self):
        self.assertEqual(cjk.in_digits("营收预计达到 46-52 亿元"), "营收预计达到 4600000000-5200000000 元")
        self.assertEqual(cjk.in_digits("营收46亿至52亿元"), "营收 4600000000 至 5200000000 元")
        # A run of years isn't a range of amounts: the unit stands against neither of them.
        self.assertEqual(cjk.in_digits("2023-2024年收入从19亿增长到34亿"), "2023-2024 年收入从 1900000000 增长到 3400000000")

    def test_a_round_amount_with_no_digits_is_read_only_where_it_can_be_nothing_else(self):
        self.assertEqual(cjk.in_digits("成立8年营收破百亿"), "成立 8 年营收破 10000000000")
        self.assertEqual(cjk.in_digits("市值千亿"), "市值 100000000000")
        # Thirty billion, several tens of billions, and "be sure to" are left as they're written.
        for text in ("营收三百亿", "投入数十亿", "千万不要忘记"):
            with self.subTest(text):
                self.assertEqual(cjk.in_digits(text), text)

    def test_chinese_is_set_apart_from_the_digits_and_letters_it_touches(self):
        self.assertEqual(cjk.in_digits("工业级3D打印设备，市占率18%，排名第一"), "工业级 3D 打印设备，市占率 18%，排名第一")
        self.assertEqual(cjk.in_digits("估值80亿美元（约合568.24亿元）"), "估值 8000000000 美元（约合 56824000000 元）")

    def test_text_with_no_chinese_comes_back_as_it_was(self):
        for text in ("Revenue of 551,102 in thousands.", "", "RMB 3.7bn, up 40%"):
            with self.subTest(text):
                self.assertIs(cjk.in_digits(text), text)

    def test_a_number_with_no_unit_against_it_is_left_alone(self):
        self.assertEqual(cjk.in_digits("2025年出口642台，同比增长12.5%"), "2025 年出口 642 台，同比增长 12.5%")


if __name__ == "__main__":
    unittest.main()
