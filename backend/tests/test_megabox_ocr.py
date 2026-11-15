import hashlib
import json
import subprocess
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from requests.exceptions import Timeout

from crawlers.megabox_ocr import extract_coupon_start_date, extract_goods_start_date


DATE = datetime(2026, 11, 13)
START = "2026-11-13 12:00:00"
TEXT = "- 본 미벤트 쿠폰 다운로드는 11.13(금] 12:00~ 부터 가능합니다."
HTML = r'<div class="event-html-area"><img src="\SharedImg\editorImg\2026\11\banner.jpg"></div>'


def image_response(content=b"banner", status=200):
    response = Mock(status_code=status)
    response.iter_content.return_value = [content]
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    return context


class MegaboxOCRTest(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.cache = Path(folder.name) / "ocr-cache.json"
        self.session = Mock()
        self.session.get.side_effect = lambda *args, **kwargs: image_response()

    def extract(self, html=HTML, date=DATE):
        return extract_goods_start_date(self.session, html, date, self.cache)

    def test_accepts_explicit_download_time_and_repeated_agreement(self):
        for text in [TEXT, TEXT + "\n" + TEXT,
                     "쿠폰 다운로드는 2026.11.13(금) 12:00~",
                     "쿠폰 다운로드는 11월 13일 12:00부터"]:
            with self.subTest(text=text):
                self.assertEqual(START, extract_coupon_start_date(text, DATE))

    def test_rejects_unrelated_ambiguous_or_invalid_times(self):
        for text in [
            "2026.11.13(금) 12:00 ~ 11.19(목)",
            "쿠폰 사용 기간은 11.13(금) 12:00~",
            "쿠폰 다운로드는 11.13(금) ~ 11.19(목) 12:00",
            TEXT + "\n쿠폰 다운로드는 11.13(금) 14:00~",
            TEXT.replace("11.13", "11.14"),
            TEXT.replace("11.13", "2028.11.13"),
            TEXT.replace("11.13", "02.30"),
            TEXT.replace("12:00", "25:00"),
            TEXT.replace("12:00", "12:60"),
        ]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                extract_coupon_start_date(text, DATE)

    @patch("crawlers.megabox_ocr.subprocess.run", return_value=Mock(stdout=TEXT))
    def test_persists_cache_and_reuses_it_for_identical_image(self, run):
        self.assertEqual(START, self.extract())
        self.assertEqual(START, self.extract())
        self.assertEqual(1, run.call_count)
        self.assertEqual([START], list(json.loads(self.cache.read_text()).values()))
        self.assertEqual("https://img.megabox.co.kr/SharedImg/editorImg/2026/11/banner.jpg",
                         self.session.get.call_args.args[0])
        self.assertFalse(self.session.get.call_args.kwargs["allow_redirects"])
        self.assertEqual(30, run.call_args.kwargs["timeout"])

    @patch("crawlers.megabox_ocr.subprocess.run", return_value=Mock(stdout=TEXT))
    def test_changed_image_or_listing_date_runs_ocr_again(self, run):
        self.assertEqual(START, self.extract())
        self.session.get.side_effect = lambda *args, **kwargs: image_response(b"new banner")
        self.assertEqual(START, self.extract())
        run.return_value.stdout = TEXT.replace("11.13", "11.14")
        self.assertEqual("2026-11-14 12:00:00", self.extract(date=datetime(2026, 11, 14)))
        self.assertEqual(3, run.call_count)

    @patch("crawlers.megabox_ocr.subprocess.run", return_value=Mock(stdout="일시 미정"))
    def test_caches_inconclusive_ocr_without_guessing_or_repeating(self, run):
        self.assertIsNone(self.extract())
        self.assertIsNone(self.extract())
        self.assertEqual(1, run.call_count)
        self.assertEqual([None], list(json.loads(self.cache.read_text()).values()))

    @patch("crawlers.megabox_ocr.subprocess.run", return_value=Mock(stdout=TEXT))
    def test_invalid_cache_is_rebuilt(self, run):
        key = f"2026-11-13:{hashlib.sha256(b'banner').hexdigest()}"
        for value in ["broken json", "[]", json.dumps({key: []}),
                      json.dumps({key: "2026-11-14 12:00:00"})]:
            with self.subTest(value=value):
                self.cache.write_text(value, encoding="utf-8")
                self.assertEqual(START, self.extract())
        self.assertEqual(4, run.call_count)

    @patch("crawlers.megabox_ocr.subprocess.run")
    def test_missing_failed_or_timed_out_ocr_remains_retryable(self, run):
        for error in [FileNotFoundError("not installed"),
                      subprocess.TimeoutExpired("tesseract", 30),
                      subprocess.CalledProcessError(1, "tesseract")]:
            with self.subTest(error=error):
                run.side_effect = error
                self.assertIsNone(self.extract())
                self.assertFalse(self.cache.exists())

    @patch("crawlers.megabox_ocr.subprocess.run")
    def test_download_failure_does_not_run_ocr_or_overwrite_cache(self, run):
        self.cache.write_text("{}")
        self.session.get.side_effect = Timeout("image timeout")
        self.assertIsNone(self.extract())
        run.assert_not_called()
        self.assertEqual("{}", self.cache.read_text())

    @patch("crawlers.megabox_ocr.subprocess.run")
    def test_only_official_detail_images_are_processed(self, run):
        for src in ["https://example.com/SharedImg/editorImg/banner.jpg",
                    "https://img.megabox.co.kr.evil.test/SharedImg/editorImg/banner.jpg",
                    "https://img.megabox.co.kr/poster.jpg", "file:///banner.jpg"]:
            with self.subTest(src=src):
                self.assertIsNone(self.extract(f'<div class="event-html-area"><img src="{src}"></div>'))
        self.session.get.assert_not_called()
        run.assert_not_called()

    @patch("crawlers.megabox_ocr.subprocess.run")
    def test_redirect_or_oversized_image_is_rejected(self, run):
        for response in [image_response(status=302), image_response(b"x" * (10 * 1024 * 1024 + 1))]:
            with self.subTest(response=response):
                self.session.get.side_effect = None
                self.session.get.return_value = response
                self.assertIsNone(self.extract())
        run.assert_not_called()

    @patch("crawlers.megabox_ocr.subprocess.run")
    def test_conflicting_banner_times_remain_unknown(self, run):
        html = HTML.replace("</div>", '<img src="/SharedImg/editorImg/second.jpg"></div>')
        self.session.get.side_effect = [image_response(b"first"), image_response(b"second")]
        run.side_effect = [Mock(stdout=TEXT), Mock(stdout=TEXT.replace("12:00", "14:00"))]
        self.assertIsNone(self.extract(html))

    @patch("crawlers.megabox_ocr.subprocess.run", return_value=Mock(stdout=TEXT))
    def test_cache_write_failure_does_not_discard_valid_time(self, run):
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            self.assertEqual(START, self.extract())


if __name__ == "__main__":
    unittest.main()
