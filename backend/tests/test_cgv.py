import unittest
from unittest.mock import patch

from requests.exceptions import HTTPError

from crawlers.cgv import (
    build_movie_events,
    extract_event_search_payload,
    get_cgv_coupons,
    normalize_start_date,
)


class CgvCrawlerTest(unittest.TestCase):
    @patch.dict("os.environ", {"CGV_WORKER_URL": "https://cgv.example.workers.dev"})
    @patch("crawlers.cgv.create_retry_session")
    def test_worker_preserves_parsing_and_rejects_failed_responses(self, create_session):
        session = create_session.return_value.__enter__.return_value
        response = session.get.return_value
        response.json.return_value = {
            "data": {"evntInfo": {"evntLst": [{
                "evntNo": "101",
                "evntNm": "[테스트] 스피드 쿠폰",
                "evntStartDt": "20261020140000",
            }]}}
        }

        events = get_cgv_coupons()
        self.assertEqual(["cgv-101"], [event.id for event in events])
        self.assertEqual("2026-10-20 14:00:00", events[0].startDate)
        session.get.assert_called_once_with(
            "https://cgv.example.workers.dev", timeout=(5, 20)
        )

        response.json.return_value = {"data": {}}
        with self.assertRaisesRegex(RuntimeError, "evntLst"):
            get_cgv_coupons()

        response.json.return_value = {"data": {"evntInfo": {"evntLst": []}}}
        self.assertEqual([], get_cgv_coupons())

        response.raise_for_status.side_effect = HTTPError("403 Forbidden")
        with self.assertRaises(HTTPError):
            get_cgv_coupons()

    @patch.dict("os.environ", {"CGV_WORKER_URL": ""})
    @patch("crawlers.cgv.create_retry_session")
    def test_direct_access_still_initializes_the_search_session(self, create_session):
        session = create_session.return_value.__enter__.return_value
        session.get.return_value.json.return_value = {
            "data": {"evntInfo": {"evntLst": []}}
        }

        self.assertEqual([], get_cgv_coupons())
        self.assertEqual(2, session.get.call_count)
        self.assertEqual(
            "https://cgv.co.kr/tme/itgrSrch", session.get.call_args_list[0].args[0]
        )

    def test_extracts_event_list_and_distinguishes_empty_result(self):
        payload = {
            "statusCode": 0,
            "data": {
                "evntInfo": {
                    "totalCnt": 1,
                    "evntLst": [
                        {
                            "evntNo": "100",
                            "evntNm": "[테스트] 스피드 쿠폰",
                        }
                    ],
                }
            },
        }

        events = extract_event_search_payload(payload)
        self.assertEqual(["100"], [event["evntNo"] for event in events])

        self.assertEqual(
            [],
            extract_event_search_payload({"data": {"evntInfo": {"evntLst": []}}}),
        )
        self.assertIsNone(extract_event_search_payload({"data": {}}))

    def test_builds_only_movie_coupon_events_and_deduplicates(self):
        raw_events = [
            {
                "evntNo": "101",
                "evntNm": "[산양들] 서프라이즈 쿠폰",
                "evntStartDt": "20260727",
                "mduBanrPhyscFilePathnm": "/cgvpomscontent/ips/evnt/2026/0724/",
                "mduBanrPhyscFnm": "/banner.jpg",
            },
            {
                "evntNo": "102",
                "evntNm": "[호프] 스피드 쿠폰",
                "evntStartDt": "2026-07-24",
            },
            {
                "evntNo": "101",
                "evntNm": "[산양들] 서프라이즈 쿠폰",
                "evntStartDt": "20260727",
            },
            {
                "evntNo": "103",
                "evntNm": "내 차 보험료 조회하고 영화 할인쿠폰 받기",
                "evntStartDt": "20260101",
            },
        ]

        events = build_movie_events(raw_events)

        self.assertEqual(["cgv-101", "cgv-102"], [event.id for event in events])
        self.assertEqual(["산양들", "호프"], [event.title for event in events])
        self.assertEqual(
            ["서프라이즈쿠폰", "스피드쿠폰"],
            [event.category for event in events],
        )
        self.assertEqual("2026-07-27 00:00:00", events[0].startDate)
        self.assertEqual(
            "https://cdn.cgv.co.kr/cgvpomscontent/ips/evnt/2026/0724/banner.jpg",
            events[0].imageUrl,
        )

    def test_normalizes_supported_date_formats(self):
        self.assertEqual(
            "2026-07-29 14:00:00",
            normalize_start_date("20260729140000"),
        )
        self.assertEqual(
            "2026-07-29 00:00:00",
            normalize_start_date("2026.07.29"),
        )
        self.assertEqual("", normalize_start_date("not-a-date"))


if __name__ == "__main__":
    unittest.main()
