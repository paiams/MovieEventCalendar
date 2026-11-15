import re
from datetime import datetime

from bs4 import BeautifulSoup
from requests.exceptions import RequestException

from crawlers.megabox_ocr import extract_goods_start_date
from crawlers.models import MovieEvent
from crawlers.network import create_retry_session

LIST_TIMEOUT = 10
DETAIL_TIMEOUT = 5


def extract_event_items(html):
    soup = BeautifulSoup(html, "html.parser")
    event_list = soup.select_one(".event-list")
    if event_list is None:
        raise RuntimeError("목록 응답에서 event-list를 찾을 수 없습니다.")
    return event_list.select(".item")


def extract_start_date(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style"):
        tag.decompose()
    match = re.search(
        r"기간\s*(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})"
        r"\s*\.?\s*(?:\([월화수목금토일]\)\s*)?(\d{1,2})\s*:\s*(\d{2})",
        soup.get_text(" ", strip=True),
    )
    if not match:
        raise ValueError("상세 페이지에서 시작 시간을 찾을 수 없습니다.")
    return datetime(*map(int, match.groups())).strftime("%Y-%m-%d %H:%M:%S")


def get_megabox_zero_tickets(previous_events=(), ocr_cache_path=None):
    """
    메가박스 빵원티켓과 빵원굿즈를 수집합니다.
    굿즈의 HTML에 시각이 없으면 이미지 OCR을 시도하고, 불확실하면 시간 미확인으로 반환합니다.
    """
    url = "https://m.megabox.co.kr/on/oh/ohe/Event/eventMngDiv.do"

    payload = {
        "currentPage": "1",
        # shortcut: 100건 단일 요청, 동시 진행 이벤트가 이를 넘으면 페이지네이션한다.
        "recordCountPerPage": "100",
        "eventTitle": "빵원",
        "eventStatCd": "ONG",
        "orderReqCd": "ONGlist",
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36"
    }

    results = []
    previous_by_id = {event.id: event for event in previous_events}
    failed_details = 0
    with create_retry_session() as session:
        try:
            # 1. 목록 페이지 조회
            response = session.post(
                url,
                data=payload,
                headers=headers,
                timeout=LIST_TIMEOUT,
            )
            response.raise_for_status()

            items = extract_event_items(response.text)

            for item in items:
                a_tag = item.find("a")
                title_tag = item.select_one(".title")
                if not a_tag or not title_tag:
                    continue

                onclick_text = a_tag.get("onclick", "")
                match = re.search(r"fn_eventDetail\('(\d+)'", onclick_text)
                event_id = match.group(1) if match else None
                if not event_id:
                    continue

                raw_title = title_tag.text.strip()
                category_match = re.search(r"빵원(?:티켓|굿즈)", raw_title)
                if not category_match:
                    continue
                category = category_match.group()
                title_match = re.search(r"\[(.*?)\]", raw_title)
                clean_title = (
                    title_match.group(1).strip()
                    if title_match and category == "빵원티켓" else raw_title
                )

                img_tag = item.select_one("img")
                img_url = img_tag.get("data-src", "") if img_tag else ""
                detail_url = f"https://megabox.co.kr/event/detail?eventNo={event_id}"

                # 2. 상세 페이지에서 정확한 시작 시간을 파싱합니다.
                time_unknown = False
                try:
                    detail_res = session.get(
                        detail_url,
                        headers=headers,
                        timeout=DETAIL_TIMEOUT,
                    )
                    detail_res.raise_for_status()
                    try:
                        start_date = extract_start_date(detail_res.text)
                    except ValueError:
                        if category != "빵원굿즈":
                            raise
                        date_tag = item.select_one(".date")
                        date_match = re.match(
                            r"(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})",
                            date_tag.get_text(strip=True) if date_tag else "",
                        )
                        if not date_match:
                            raise ValueError("굿즈 행사 시작 날짜를 찾을 수 없습니다.")
                        listing_date = datetime(*map(int, date_match.groups()))
                        image_start = extract_goods_start_date(
                            session, detail_res.text, listing_date, ocr_cache_path,
                        )
                        start_date = image_start or listing_date.strftime("%Y-%m-%d %H:%M:%S")
                        time_unknown = image_start is None
                except (RequestException, ValueError) as error:
                    failed_details += 1
                    previous = previous_by_id.get(f"mega-{event_id}")
                    if previous is not None:
                        results.append(previous)
                    action = "이전 데이터 유지" if previous is not None else "항목 건너뜀"
                    print(f"::warning::[Megabox] {event_id}: {error} ({action})")
                    continue

                results.append(
                    MovieEvent(
                        id=f"mega-{event_id}",
                        theater="MEGABOX",
                        title=clean_title,
                        startDate=start_date,
                        url=detail_url,
                        imageUrl=img_url,
                        category=category,
                        timeUnknown=time_unknown,
                    )
                )

            if failed_details and not results:
                raise RuntimeError("모든 빵원 이벤트 상세 조회에 실패했습니다.")

        except Exception as error:
            print(f"[Megabox] 빵원 이벤트 크롤링 중 오류 발생: {error}")
            raise RuntimeError("메가박스 크롤링에 실패했습니다.") from error

    return results
