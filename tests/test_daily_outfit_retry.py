# -*- coding: utf-8 -*-
"""每日穿搭：图片有效性校验、失败自动重试判定与早上 6 点生成时间门。"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from astrbot_plugin_private_companion.proactive_message import ProactiveMessageMixin

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
_SVG_ERROR_CARD = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="480">'
    "<text>生成失败</text><text>连接超时</text></svg>"
).encode("utf-8")


class _Harness(ProactiveMessageMixin):
    pass


class DailyOutfitImageValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="outfit_validate_")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def _write(self, name: str, data: bytes) -> str:
        path = self.dir / name
        path.write_bytes(data)
        return str(path)

    def test_valid_png_accepted(self) -> None:
        path = self._write("ok.png", _PNG)
        self.assertEqual("", ProactiveMessageMixin._daily_outfit_image_error(path))

    def test_svg_error_card_rejected(self) -> None:
        path = self._write("fail.img", _SVG_ERROR_CARD)
        reason = ProactiveMessageMixin._daily_outfit_image_error(path)
        self.assertIn("占位图", reason)

    def test_missing_file_rejected(self) -> None:
        reason = ProactiveMessageMixin._daily_outfit_image_error(str(self.dir / "nope.png"))
        self.assertIn("不存在", reason)

    def test_empty_path_rejected(self) -> None:
        self.assertEqual("没有图片路径", ProactiveMessageMixin._daily_outfit_image_error(""))

    def test_empty_file_rejected(self) -> None:
        path = self._write("empty.png", b"")
        self.assertIn("为空", ProactiveMessageMixin._daily_outfit_image_error(path))

    def test_tiny_non_image_rejected(self) -> None:
        path = self._write("junk.bin", b"abcd" * 10)
        self.assertIn("过小", ProactiveMessageMixin._daily_outfit_image_error(path))


class DailyOutfitSkipRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="outfit_retry_")
        self.addCleanup(tmp.cleanup)
        self.harness = _Harness()
        self.today = "2026-09-22"
        self.now = datetime(2026, 9, 22, 6, 10).timestamp()
        png = Path(tmp.name) / "ok.png"
        png.write_bytes(_PNG)
        self.png = str(png)
        svg = Path(tmp.name) / "bad.img"
        svg.write_bytes(_SVG_ERROR_CARD)
        self.svg = str(svg)

    def test_valid_success_today_skips(self) -> None:
        record = {
            "date": self.today,
            "path": self.png,
            "error": "",
            "retry_count": 0,
            "generated_at": self.now - 3600,
        }
        self.assertTrue(
            self.harness._daily_outfit_should_skip_existing(record, self.today, self.now)
        )

    def test_invalid_image_record_allows_retry(self) -> None:
        record = {
            "date": self.today,
            "path": self.svg,
            "error": "",
            "retry_count": 0,
            "generated_at": self.now - 3600,
        }
        self.assertFalse(
            self.harness._daily_outfit_should_skip_existing(record, self.today, self.now)
        )

    def test_missing_path_failure_allows_retry(self) -> None:
        record = {
            "date": self.today,
            "path": "",
            "error": "生图失败",
            "retry_count": 1,
            "generated_at": self.now - 3600,
        }
        self.assertFalse(
            self.harness._daily_outfit_should_skip_existing(record, self.today, self.now)
        )

    def test_backoff_blocks_immediate_retry(self) -> None:
        record = {
            "date": self.today,
            "path": "",
            "error": "生图失败",
            "retry_count": 1,
            "generated_at": self.now - 60,
        }
        self.assertTrue(
            self.harness._daily_outfit_should_skip_existing(record, self.today, self.now)
        )

    def test_retry_exhausted_skips(self) -> None:
        record = {
            "date": self.today,
            "path": "",
            "error": "生图失败",
            "retry_count": 5,
            "generated_at": self.now - 3600,
        }
        self.assertTrue(
            self.harness._daily_outfit_should_skip_existing(record, self.today, self.now)
        )

    def test_other_day_never_skips(self) -> None:
        record = {
            "date": "2026-09-21",
            "path": self.png,
            "error": "",
            "retry_count": 0,
            "generated_at": self.now - 86400,
        }
        self.assertFalse(
            self.harness._daily_outfit_should_skip_existing(record, self.today, self.now)
        )

    def test_empty_record_never_skips(self) -> None:
        self.assertFalse(
            self.harness._daily_outfit_should_skip_existing({}, self.today, self.now)
        )


class DailyOutfitTimeGateTests(unittest.TestCase):
    def test_before_6am_blocked(self) -> None:
        ts = datetime(2026, 9, 22, 5, 59).timestamp()
        self.assertFalse(_Harness._daily_outfit_generation_time_reached(ts))

    def test_at_6am_allowed(self) -> None:
        ts = datetime(2026, 9, 22, 6, 0).timestamp()
        self.assertTrue(_Harness._daily_outfit_generation_time_reached(ts))

    def test_afternoon_allowed(self) -> None:
        ts = datetime(2026, 9, 22, 15, 30).timestamp()
        self.assertTrue(_Harness._daily_outfit_generation_time_reached(ts))


if __name__ == "__main__":
    unittest.main()
