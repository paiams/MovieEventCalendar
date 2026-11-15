import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

# 윈도우 환경에서 콘솔 출력(이모지 등) 인코딩 에러 방지
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# 크롤러 모듈 임포트
from crawlers.cgv import get_cgv_coupons
from crawlers.lottecinema import get_lottecinema_moviesadagu
from crawlers.megabox import get_megabox_zero_tickets
from crawlers.models import MovieEvent

# 이벤트 데이터를 저장할 최종 경로 (frontend/public/data/events.json)
# main.py 실행 위치(backend 디렉토리)를 기준으로 상대 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DATA_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "..", "frontend", "public", "data")
)
OUTPUT_FILE = os.path.join(FRONTEND_DATA_DIR, "events.json")
ICS_OUTPUT_FILE = os.path.join(FRONTEND_DATA_DIR, "events.ics")

THEATER_LABELS = {
    "CGV": "CGV",
    "MEGABOX": "메가박스",
    "LOTTECINEMA": "롯데시네마",
}
KST = timezone(timedelta(hours=9), name="KST")


def format_ics_datetime(value):
    return value.strftime("%Y%m%dT%H%M%S")


def escape_ics_text(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def fold_ics_line(value):
    chunks = []
    chunk = ""
    chunk_size = 0
    for char in value:
        char_size = len(char.encode("utf-8"))
        limit = 75 if not chunks else 74
        if chunk and chunk_size + char_size > limit:
            chunks.append(chunk)
            chunk = char
            chunk_size = char_size
        else:
            chunk += char
            chunk_size += char_size
    chunks.append(chunk)
    return "\r\n ".join(chunks)


def load_previous_events():
    try:
        with open(OUTPUT_FILE, encoding="utf-8") as source:
            data = json.load(source)
        if not isinstance(data, list):
            raise ValueError("이벤트 목록이 아닙니다.")
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as error:
        print(f"::warning::이전 이벤트 데이터를 읽을 수 없습니다: {error}")
        return []

    events = []
    for item in data:
        try:
            event = MovieEvent(**item)
            if not all(isinstance(value, str) and value for value in (
                event.id, event.theater, event.title, event.startDate, event.url
            )):
                raise ValueError("필수 이벤트 정보가 올바른 문자열이 아닙니다.")
            if event.theater not in THEATER_LABELS:
                raise ValueError("알 수 없는 영화관입니다.")
            if not isinstance(event.timeUnknown, bool):
                raise ValueError("시간 미확인 표시가 올바르지 않습니다.")
            datetime.strptime(event.startDate, "%Y-%m-%d %H:%M:%S")
            events.append(event)
        except (TypeError, ValueError) as error:
            print(f"::warning::잘못된 이전 이벤트를 건너뜁니다: {error}")
    return events


def fetch_all_events():
    """
    3사 크롤러를 병렬(멀티스레드)로 실행하여 결과를 취합하고 개별 소요 시간을 측정합니다.
    """
    print(
        f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] 3사 영화관 할인 이벤트 크롤링 시작..."
    )
    events = []
    previous_events = load_previous_events()

    # 시간 측정 및 에러 핸들링을 위한 래퍼 함수
    def run_with_timing(target_func, name):
        start_time = time.time()
        try:
            res = target_func()
            duration = time.time() - start_time
            print(f"  ✅ {name} 완료: {len(res)}개 수집 (소요 시간: {duration:.2f}초)")
            return res
        except Exception as error:
            duration = time.time() - start_time
            print(f"::warning::{name} 오류: {error} (소요 시간: {duration:.2f}초)")
            raise

    crawler_specs = (
        ("CGV", "CGV", get_cgv_coupons),
        ("LotteCinema", "LOTTECINEMA", get_lottecinema_moviesadagu),
        ("Megabox", "MEGABOX", lambda: get_megabox_zero_tickets(
            previous_events, os.path.join(FRONTEND_DATA_DIR, "megabox-ocr-cache.json"),
        )),
    )
    failures = []

    # 실패한 영화관만 이전 데이터를 사용하고 정상 수집 결과는 갱신합니다.
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_name = {
            executor.submit(run_with_timing, crawler, name): (name, theater)
            for name, theater, crawler in crawler_specs
        }
        for future in as_completed(future_to_name):
            name, theater = future_to_name[future]
            try:
                events.extend(future.result())
            except Exception as error:
                failures.append(f"{name}: {error}")
                previous = [event for event in previous_events if event.theater == theater]
                events.extend(previous)
                print(f"::warning::{name}: 이전 이벤트 {len(previous)}개 유지")

    if len(failures) == len(crawler_specs):
        raise RuntimeError(
            "모든 크롤러가 실패하여 기존 배포 데이터를 유지합니다: "
            + " | ".join(failures)
        )

    print(
        f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] 총 {len(events)}개의 이벤트를 수집하여 병합 완료."
    )
    return events


def save_events_to_json(events):
    """
    수집된 이벤트를 프론트엔드 정적 파일 경로(public/data)에 JSON으로 저장합니다.
    """
    # 저장할 디렉토리가 없으면 생성 (예: frontend/public/data)
    os.makedirs(FRONTEND_DATA_DIR, exist_ok=True)

    # 중간 파일을 완성한 뒤 교체하여 불완전한 JSON 노출을 방지합니다.
    temp_output_file = f"{OUTPUT_FILE}.tmp"
    with open(temp_output_file, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
    os.replace(temp_output_file, OUTPUT_FILE)

    print(f"[{datetime.now(KST)}] 데이터가 성공적으로 저장되었습니다: {OUTPUT_FILE}")


def save_events_to_ics(events):
    """
    수집된 이벤트를 ICS(iCalendar) 형식으로 변환하여 저장합니다.
    사용자가 이 파일을 구독하면 캘린더에 이벤트가 자동으로 추가됩니다.
    이미 지난 이벤트는 파일에 포함하지 않습니다.
    """
    os.makedirs(FRONTEND_DATA_DIR, exist_ok=True)

    # 시스템 시간대와 무관하게 KST 기준으로 비교합니다.
    now_kst = datetime.now(KST)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MovieEventCalendar//KR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:영화 할인 이벤트",
        "X-WR-TIMEZONE:Asia/Seoul",
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Seoul",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+0900",
        "TZOFFSETTO:+0900",
        "TZNAME:KST",
        "DTSTART:19700101T000000",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

    for event in events:
        try:
            start_dt = datetime.strptime(
                event["startDate"],
                "%Y-%m-%d %H:%M:%S",
            ).replace(tzinfo=KST)
        except (ValueError, KeyError):
            continue

        time_unknown = event.get("timeUnknown", False)
        is_past = start_dt.date() < now_kst.date() if time_unknown else start_dt < now_kst
        if is_past:
            continue

        end_dt = start_dt + (timedelta(days=1) if time_unknown else timedelta(minutes=30))
        start_time_str = start_dt.strftime("%Y%m%dT%H%M%S")
        uid = f"{event['id']}-{start_time_str}@movieeventcalendar"
        theater_label = THEATER_LABELS.get(
            event.get("theater", ""), event.get("theater", "")
        )
        summary = escape_ics_text(
            f"[{theater_label}] {event.get('title', '')} - {event.get('category', '')}"
        )

        # DTSTAMP가 매번 변경되는 것을 방지하기 위해 이벤트 시작 시간을 기준으로 고정값을 사용합니다.
        stable_stamp = start_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        description = f"예매 링크: {event.get('url', '')}"
        if time_unknown:
            description += "\n시작 시간 미확인 — 상세 페이지를 확인하세요."
        description = escape_ics_text(description)
        location = escape_ics_text(theater_label)

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{stable_stamp}",
                f"DTSTART;VALUE=DATE:{start_dt:%Y%m%d}" if time_unknown
                else f"DTSTART;TZID=Asia/Seoul:{format_ics_datetime(start_dt)}",
                f"DTEND;VALUE=DATE:{end_dt:%Y%m%d}" if time_unknown
                else f"DTEND;TZID=Asia/Seoul:{format_ics_datetime(end_dt)}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                f"URL:{event.get('url', '')}",
                f"LOCATION:{location}",
                "SEQUENCE:0",
                "STATUS:CONFIRMED",
                "TRANSP:TRANSPARENT",
            ]
        )
        if not time_unknown:
            lines.extend([
                "BEGIN:VALARM",
                "TRIGGER:-PT10M",
                "ACTION:DISPLAY",
                "DESCRIPTION:이벤트 10분 전 알림",
                "END:VALARM",
            ])
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    temp_ics_output_file = f"{ICS_OUTPUT_FILE}.tmp"
    with open(temp_ics_output_file, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(fold_ics_line(line) for line in lines) + "\r\n")
    os.replace(temp_ics_output_file, ICS_OUTPUT_FILE)

    print(
        f"[{now_kst}] ICS 파일이 성공적으로 저장되었습니다 (지난 이벤트 제외): {ICS_OUTPUT_FILE}"
    )


def main():
    try:
        events = fetch_all_events()

        # 시작 시간(startDate)을 기준으로 오름차순 정렬
        # (MovieEvent 객체이므로 속성 접근 방식 사용)
        events.sort(key=lambda x: x.startDate if x.startDate else "9999-12-31")

        # JSON 저장을 위해 객체를 딕셔너리 리스트로 변환
        event_dicts = [event.to_dict() for event in events]

        save_events_to_json(event_dicts)
        save_events_to_ics(event_dicts)
    except Exception as e:
        print(f"크롤링 통합 파이프라인 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
