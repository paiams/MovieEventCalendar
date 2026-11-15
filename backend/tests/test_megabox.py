import unittest
from unittest.mock import Mock, patch

from requests.exceptions import HTTPError, Timeout

from crawlers.megabox import extract_event_items, extract_start_date, get_megabox_zero_tickets
from crawlers.models import MovieEvent


DETAIL_HTML = """
<dd class="n2">개봉일 2026.11.25(수)</dd>
<dd class="n3"><span>기간 2026.11.16(월) 11:30 ~ 선착순 예매마감까지</span></dd>
"""


def event_item(event_id, title="[테스트 영화] 선착순 빵원티켓 ➕", date="2026.11.13 ~ 2026.11.19"):
    return f"""<div class="item">
        <a onclick="fn_eventDetail('{event_id}', 'Y', 'N');">
            <p class="title">{title}</p><img data-src="https://example.com/poster.jpg">
            <p class="date">{date}</p>
        </a></div>"""


class MegaboxCrawlerTest(unittest.TestCase):
    def test_distinguishes_empty_list_from_invalid_response(self):
        self.assertEqual([], extract_event_items('<div class="event-list"></div>'))

        with self.assertRaisesRegex(RuntimeError, "event-list"):
            extract_event_items("<html>blocked</html>")

    def test_extracts_valid_start_time_across_tags_and_whitespace(self):
        for html in [
            DETAIL_HTML,
            "<p>기간 <b>2026 . 11 . 16</b> (월)\n<span>11&nbsp;: 30</span></p>",
            "<p>기간 2026.11.16 11:30 ~ 마감까지</p>",
        ]:
            with self.subTest(html=html):
                self.assertEqual("2026-11-16 11:30:00", extract_start_date(html))

    def test_rejects_missing_or_invalid_start_time(self):
        for html in [
            "<p>기간 2026.11.16 ~ 2026.11.24</p><p>고객센터 09:00</p>",
            "<p>기간 2026.02.30(월) 11:30</p>",
            "<p>기간 2026.11.16(월) 25:00</p>",
            "<script>기간 2026.11.16(월) 11:30</script>",
            "<html>blocked</html>",
        ]:
            with self.subTest(html=html), self.assertRaises(ValueError):
                extract_start_date(html)

    @patch("crawlers.megabox.create_retry_session")
    def test_collects_tickets_and_date_only_goods_with_full_product_title(self, create_session):
        session = create_session.return_value.__enter__.return_value
        goods_title = "[블랙 프라이데이] '만달로리안과 그로구 버켓' 선착순 빵원굿즈 ➕"
        session.post.return_value.text = '<div class="event-list">' + (
            event_item("21595", goods_title)
            + event_item("21643")
            + event_item("99999", "빵원쿠폰 안내")
        ) + "</div>"
        session.get.side_effect = [
            Mock(text='<p class="date">2026.11.13 - 2026.11.19</p><img alt="" src="goods.jpg">'),
            Mock(text=DETAIL_HTML),
        ]

        events = get_megabox_zero_tickets()

        self.assertEqual(["mega-21595", "mega-21643"], [event.id for event in events])
        self.assertEqual(["빵원굿즈", "빵원티켓"], [event.category for event in events])
        self.assertEqual(goods_title, events[0].title)
        self.assertEqual("2026-11-13 00:00:00", events[0].startDate)
        self.assertTrue(events[0].timeUnknown)
        self.assertEqual("테스트 영화", events[1].title)
        self.assertEqual("2026-11-16 11:30:00", events[1].startDate)
        self.assertFalse(events[1].timeUnknown)
        self.assertEqual("빵원", session.post.call_args.kwargs["data"]["eventTitle"])
        self.assertEqual(2, session.get.call_count)
        self.assertIn("eventNo=21643", session.get.call_args.args[0])

    @patch("crawlers.megabox.create_retry_session")
    def test_goods_use_exact_start_time_when_available(self, create_session):
        session = create_session.return_value.__enter__.return_value
        session.post.return_value.text = '<div class="event-list">' + event_item(
            "21595", "[블랙 프라이데이] 버켓 선착순 빵원굿즈"
        ) + "</div>"
        session.get.return_value.text = DETAIL_HTML

        events = get_megabox_zero_tickets()

        self.assertEqual("빵원굿즈", events[0].category)
        self.assertEqual("2026-11-16 11:30:00", events[0].startDate)
        self.assertFalse(events[0].timeUnknown)

    @patch("crawlers.megabox.extract_goods_start_date")
    @patch("crawlers.megabox.create_retry_session")
    def test_goods_use_ocr_time_or_remain_unknown_without_affecting_tickets(self, create_session, ocr):
        session = create_session.return_value.__enter__.return_value
        session.post.return_value.text = '<div class="event-list">' + (
            event_item("21595", "버켓 선착순 빵원굿즈") + event_item("21643")
        ) + "</div>"
        for start in ["2026-11-13 12:00:00", None]:
            with self.subTest(start=start):
                session.get.side_effect = [Mock(text="이미지에만 시각 표시"), Mock(text=DETAIL_HTML)]
                ocr.return_value = start
                events = get_megabox_zero_tickets(ocr_cache_path="cache.json")
                self.assertEqual(["mega-21595", "mega-21643"], [e.id for e in events])
                self.assertEqual(start or "2026-11-13 00:00:00", events[0].startDate)
                self.assertEqual(start is None, events[0].timeUnknown)
                self.assertEqual("2026-11-16 11:30:00", events[1].startDate)
                self.assertEqual("cache.json", ocr.call_args.args[3])

    @patch("crawlers.megabox.create_retry_session")
    def test_goods_without_valid_dates_are_skipped_without_losing_tickets(self, create_session):
        session = create_session.return_value.__enter__.return_value
        for date in ["", "invalid", "2026.02.30 ~ 2026.03.01"]:
            with self.subTest(date=date):
                session.post.return_value.text = '<div class="event-list">' + (
                    event_item("21595", "버켓 선착순 빵원굿즈", date)
                    + event_item("21643")
                ) + "</div>"
                session.get.side_effect = [Mock(text="시작 시각 없음"), Mock(text=DETAIL_HTML)]
                events = get_megabox_zero_tickets()
                self.assertEqual(["mega-21643"], [event.id for event in events])

    @patch("crawlers.megabox.create_retry_session")
    def test_detail_failures_use_previous_event_or_skip_and_continue(self, create_session):
        session = create_session.return_value.__enter__.return_value
        session.post.return_value.text = '<div class="event-list">' + "".join(
            event_item(event_id) for event_id in ["1", "2", "3"]
        ) + "</div>"
        previous = MovieEvent(
            id="mega-1", theater="MEGABOX", title="이전 영화",
            startDate="2026-11-16 10:00:00", url="https://example.com/event",
        )

        for failure in [
            Mock(text="시작 시간 없음"),
            Mock(text="기간 2026.02.30(월) 11:30"),
            Mock(raise_for_status=Mock(side_effect=HTTPError("503"))),
            Timeout("timeout"),
        ]:
            with self.subTest(failure=failure):
                session.get.side_effect = [failure, Timeout("timeout"), Mock(text=DETAIL_HTML)]
                events = get_megabox_zero_tickets([previous])
                self.assertEqual(["mega-1", "mega-3"], [event.id for event in events])
                self.assertIs(previous, events[0])
                self.assertEqual("2026-11-16 11:30:00", events[1].startDate)

    @patch("crawlers.megabox.create_retry_session")
    def test_all_failed_details_without_previous_data_report_failure(self, create_session):
        session = create_session.return_value.__enter__.return_value
        session.post.return_value.text = '<div class="event-list">' + event_item("1") + "</div>"
        session.get.return_value.text = "시작 시간 없음"

        with self.assertRaisesRegex(RuntimeError, "메가박스 크롤링에 실패"):
            get_megabox_zero_tickets()


if __name__ == "__main__":
    unittest.main()
