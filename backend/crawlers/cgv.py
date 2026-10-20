import os
import re
from datetime import datetime

from crawlers.models import MovieEvent
from crawlers.network import create_retry_session

RELEVANT_COUPON_CATEGORIES = (
    ("스피드", "스피드쿠폰"),
    ("서프라이즈", "서프라이즈쿠폰"),
)


def extract_event_search_payload(data):
    """통합 검색 응답의 이벤트 목록을 반환합니다."""
    try:
        event_list = data["data"]["evntInfo"]["evntLst"]
    except (KeyError, TypeError):
        return None
    return (
        [event for event in event_list if isinstance(event, dict)]
        if isinstance(event_list, list)
        else None
    )


def normalize_start_date(value):
    """
    CGV 날짜 값을 프론트엔드 공통 형식으로 정규화합니다.
    """
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y%m%d%H%M%S",
        "%Y%m%d",
    )
    for date_format in formats:
        try:
            parsed = datetime.strptime(raw_value, date_format)
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    return ""


def build_movie_events(raw_events):
    """
    통합 검색 결과 중 영화 선착순 쿠폰만 MovieEvent로 변환합니다.
    """
    results = []
    seen_ids = set()

    for event in raw_events:
        raw_title = str(event.get("evntNm", "")).strip()
        category_name = next(
            (
                category
                for keyword, category in RELEVANT_COUPON_CATEGORIES
                if keyword in raw_title and "쿠폰" in raw_title
            ),
            None,
        )
        if not category_name:
            continue

        event_id = str(event.get("evntNo", "")).strip()
        if not event_id or event_id in seen_ids:
            continue

        start_date = normalize_start_date(event.get("evntStartDt"))
        if not start_date:
            print(f"[CGV] 시작일 형식을 해석할 수 없어 제외합니다 (ID: {event_id})")
            continue

        seen_ids.add(event_id)

        title_match = re.search(r"\[(.*?)\]", raw_title)
        movie_title = title_match.group(1).strip() if title_match else raw_title

        img_path = str(event.get("mduBanrPhyscFilePathnm", "")).strip("/")
        img_file = str(event.get("mduBanrPhyscFnm", "")).strip("/")
        image_url = ""
        if img_path and img_file:
            image_url = f"https://cdn.cgv.co.kr/{img_path}/{img_file}"

        results.append(
            MovieEvent(
                id=f"cgv-{event_id}",
                theater="CGV",
                title=movie_title,
                startDate=start_date,
                url=f"https://cgv.co.kr/evt/eventDetail?evntNo={event_id}",
                imageUrl=image_url,
                category=category_name,
            )
        )

    return results


def get_cgv_coupons():
    print("[CGV] 통합 검색 API를 호출합니다...")
    worker_url = os.environ.get("CGV_WORKER_URL")
    page_url = "https://cgv.co.kr/tme/itgrSrch"
    api_url = "https://cgv.co.kr/api/v1/common/timeline/more/itgrSrch/searchItgrSrchAll"

    with create_retry_session() as session:
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ko-KR,ko;q=0.9",
            }
        )
        if worker_url:
            api_response = session.get(worker_url, timeout=(5, 20))
        else:
            page_response = session.get(
                page_url,
                params={"swrd": "쿠폰"},
                timeout=(5, 20),
            )
            page_response.raise_for_status()
            api_response = session.get(
                api_url,
                params={"coCd": "A420", "swrd": "쿠폰"},
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Referer": page_response.url,
                },
                timeout=(5, 20),
            )
        api_response.raise_for_status()

    raw_events = extract_event_search_payload(api_response.json())
    if raw_events is None:
        raise RuntimeError("CGV 통합 검색 API 응답에 evntLst가 없습니다.")

    results = build_movie_events(raw_events)
    print(f"[CGV] 검색 결과에서 영화 쿠폰 {len(results)}개를 선별했습니다.")
    return results
