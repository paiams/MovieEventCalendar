import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import main as backend_main
from crawlers.lottecinema import normalize_start_date as normalize_lotte_start_date
from crawlers.models import MovieEvent


def sample_event(event_id, theater):
    return MovieEvent(
        id=event_id,
        theater=theater,
        title="테스트 영화",
        startDate="2026-08-01 14:00:00",
        url="https://example.com/event",
        category="테스트",
    )


class MainPipelineTest(unittest.TestCase):
    def setUp(self):
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.output_file = Path(temp_dir.name) / "events.json"
        output_patch = patch.object(backend_main, "OUTPUT_FILE", str(self.output_file))
        output_patch.start()
        self.addCleanup(output_patch.stop)

    def write_previous_events(self, events):
        self.output_file.write_text(
            json.dumps([event.to_dict() for event in events]), encoding="utf-8"
        )

    @patch.object(
        backend_main,
        "get_megabox_zero_tickets",
        return_value=[sample_event("mega-1", "MEGABOX")],
    )
    @patch.object(
        backend_main,
        "get_lottecinema_moviesadagu",
        return_value=[sample_event("lotte-1", "LOTTECINEMA")],
    )
    @patch.object(
        backend_main,
        "get_cgv_coupons",
        return_value=[sample_event("cgv-1", "CGV")],
    )
    def test_fetch_all_events_merges_successful_crawlers(
        self,
        _cgv_mock,
        _lotte_mock,
        _megabox_mock,
    ):
        events = backend_main.fetch_all_events()

        self.assertEqual(
            {"cgv-1", "lotte-1", "mega-1"},
            {event.id for event in events},
        )

    @patch.object(
        backend_main,
        "get_megabox_zero_tickets",
        return_value=[sample_event("mega-1", "MEGABOX")],
    )
    @patch.object(
        backend_main,
        "get_lottecinema_moviesadagu",
        side_effect=RuntimeError("API 구조 변경"),
    )
    @patch.object(
        backend_main,
        "get_cgv_coupons",
        return_value=[sample_event("cgv-1", "CGV")],
    )
    def test_main_keeps_failed_theater_and_exports_successful_ones(
        self,
        _cgv_mock,
        _lotte_mock,
        _megabox_mock,
    ):
        self.write_previous_events([
            sample_event("lotte-old", "LOTTECINEMA"),
            sample_event("cgv-old", "CGV"),
            sample_event("mega-old", "MEGABOX"),
        ])

        ics_file = self.output_file.with_suffix(".ics")
        with (
            patch.object(backend_main, "FRONTEND_DATA_DIR", str(self.output_file.parent)),
            patch.object(backend_main, "ICS_OUTPUT_FILE", str(ics_file)),
        ):
            backend_main.main()
        events = json.loads(self.output_file.read_text(encoding="utf-8"))

        self.assertEqual(
            {"cgv-1", "lotte-old", "mega-1"}, {event["id"] for event in events}
        )
        self.assertIn("BEGIN:VCALENDAR", ics_file.read_text(encoding="utf-8"))
        self.assertEqual(3, len(_megabox_mock.call_args.args[0]))

    def test_missing_or_invalid_previous_data_does_not_block_other_theaters(self):
        for contents in [None, "invalid json", "{}"]:
            with self.subTest(contents=contents):
                if contents is not None:
                    self.output_file.write_text(contents, encoding="utf-8")
                with (
                    patch.object(backend_main, "get_cgv_coupons", side_effect=RuntimeError("403")),
                    patch.object(backend_main, "get_lottecinema_moviesadagu", return_value=[]),
                    patch.object(backend_main, "get_megabox_zero_tickets", return_value=[sample_event("mega-1", "MEGABOX")]),
                ):
                    events = backend_main.fetch_all_events()
                self.assertEqual(["mega-1"], [event.id for event in events])

    def test_load_previous_events_skips_invalid_rows(self):
        previous = sample_event("mega-1", "MEGABOX")
        previous.timeUnknown = True
        invalid_date = {**previous.to_dict(), "startDate": "invalid"}
        invalid_theater = {**previous.to_dict(), "theater": "UNKNOWN"}
        invalid_id = {**previous.to_dict(), "id": []}
        invalid_time_unknown = {**previous.to_dict(), "timeUnknown": "false"}
        self.output_file.write_text(
            json.dumps([
                None, {}, invalid_date, invalid_theater, invalid_id,
                invalid_time_unknown, previous.to_dict(),
            ]),
            encoding="utf-8",
        )
        self.assertEqual([previous], backend_main.load_previous_events())

    def test_successful_empty_results_remove_previous_events(self):
        self.write_previous_events([sample_event("mega-old", "MEGABOX")])
        with (
            patch.object(backend_main, "get_cgv_coupons", return_value=[]),
            patch.object(backend_main, "get_lottecinema_moviesadagu", return_value=[]),
            patch.object(backend_main, "get_megabox_zero_tickets", return_value=[]),
        ):
            self.assertEqual([], backend_main.fetch_all_events())

    def test_all_failed_crawlers_preserve_existing_files(self):
        self.write_previous_events([sample_event("mega-old", "MEGABOX")])
        previous_contents = self.output_file.read_bytes()
        with (
            patch.object(backend_main, "get_cgv_coupons", side_effect=RuntimeError("403")),
            patch.object(backend_main, "get_lottecinema_moviesadagu", side_effect=RuntimeError("timeout")),
            patch.object(backend_main, "get_megabox_zero_tickets", side_effect=RuntimeError("blocked")),
            patch.object(backend_main, "save_events_to_json") as save_json,
            patch.object(backend_main, "save_events_to_ics") as save_ics,
        ):
            with self.assertRaises(SystemExit) as raised:
                backend_main.main()
            self.assertEqual(1, raised.exception.code)
            save_json.assert_not_called()
            save_ics.assert_not_called()
        self.assertEqual(previous_contents, self.output_file.read_bytes())

    def test_ics_uses_utc_stamp_and_escapes_text(self):
        event = sample_event("cgv-1", "CGV")
        event.title = "테스트, 영화; 특별" * 10
        event.startDate = "2099-08-01 14:00:00"

        with TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "events.ics"
            with (
                patch.object(backend_main, "FRONTEND_DATA_DIR", temp_dir),
                patch.object(backend_main, "ICS_OUTPUT_FILE", str(output_file)),
            ):
                backend_main.save_events_to_ics([event.to_dict()])

            contents = output_file.read_bytes().decode("utf-8")

        self.assertIn("DTSTAMP:20990801T050000Z", contents)
        self.assertIn(r"SUMMARY:[CGV] 테스트\, 영화\; 특별", contents)
        self.assertIn("\r\n ", contents)
        self.assertTrue(
            all(len(line.encode("utf-8")) <= 75 for line in contents.split("\r\n"))
        )

    def test_lotte_start_date_is_normalized_or_rejected(self):
        self.assertEqual(
            "2026-07-29 14:00:00",
            normalize_lotte_start_date("2026-07-29", "14:00"),
        )
        self.assertEqual("", normalize_lotte_start_date("2026-07-29", None))

    def test_unknown_time_exports_today_as_all_day_without_time_alarm(self):
        event = sample_event("mega-goods", "MEGABOX")
        event.startDate = "2099-12-31 00:00:00"
        event.category = "빵원굿즈"
        event.timeUnknown = True
        ics_file = self.output_file.with_suffix(".ics")
        with (
            patch.object(backend_main, "datetime", wraps=datetime) as clock,
            patch.object(backend_main, "FRONTEND_DATA_DIR", str(self.output_file.parent)),
            patch.object(backend_main, "ICS_OUTPUT_FILE", str(ics_file)),
        ):
            clock.now.return_value = datetime(2099, 12, 31, 12, tzinfo=backend_main.KST)
            backend_main.save_events_to_ics([event.to_dict()])

        contents = ics_file.read_bytes().decode("utf-8").replace("\r\n ", "")
        self.assertIn("DTSTART;VALUE=DATE:20991231", contents)
        self.assertIn("DTEND;VALUE=DATE:21000101", contents)
        self.assertIn("시간 미확인", contents)
        self.assertNotIn("BEGIN:VALARM", contents)


if __name__ == "__main__":
    unittest.main()
