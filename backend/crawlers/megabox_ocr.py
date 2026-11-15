import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from requests.exceptions import RequestException


def extract_coupon_start_date(text, listing_date):
    candidates = set()
    # shortcut: 명시된 쿠폰 다운로드 문구만 사용하며, 다른 형식은 표본 검증 후 추가한다.
    for match in re.finditer(
        r"쿠폰\s*다운로드는\s*(?:(\d{4})\s*[.년]\s*)?"
        r"(\d{1,2})\s*[.월]\s*(\d{1,2})(?:\s*[.일])?"
        r"(?:\s*[(\[][월화수목금토일][)\]])?\s*(\d{1,2})\s*:\s*(\d{2})",
        text,
    ):
        year, month, day, hour, minute = match.groups()
        candidate = datetime(int(year) if year else listing_date.year,
                             *map(int, (month, day, hour, minute)))
        if candidate.date() != listing_date.date():
            raise ValueError("이미지의 쿠폰 날짜가 목록의 시작 날짜와 다릅니다.")
        candidates.add(candidate.strftime("%Y-%m-%d %H:%M:%S"))
    if len(candidates) != 1:
        raise ValueError("이미지에서 하나의 명확한 쿠폰 다운로드 시각을 찾지 못했습니다.")
    return candidates.pop()


def extract_goods_start_date(session, html, listing_date, cache_path=None):
    cache = {}
    if cache_path is not None:
        cache_path = Path(cache_path)
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if not isinstance(cache, dict):
                raise ValueError("OCR 캐시가 객체가 아닙니다.")
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as error:
            print(f"::warning::[Megabox OCR] 캐시를 읽을 수 없습니다: {error}")
            cache = {}

    urls = []
    for img in BeautifulSoup(html, "html.parser").select(".event-html-area img"):
        src = (img.get("data-src") or img.get("src") or "").replace("\\", "/")
        url = urljoin("https://img.megabox.co.kr/", src)
        parsed = urlsplit(url)
        if (parsed.scheme == "https" and parsed.netloc == "img.megabox.co.kr"
                and parsed.path.startswith("/SharedImg/editorImg/") and url not in urls):
            urls.append(url)
    if not urls or len(urls) > 3:
        return None

    candidates = set()
    changed = False
    try:
        for url in urls:
            with session.get(url, timeout=(5, 10), stream=True, allow_redirects=False) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError("이미지 응답이 200이 아닙니다.")
                content = bytearray()
                for chunk in response.iter_content(65536):
                    content.extend(chunk)
                    if len(content) > 10 * 1024 * 1024:
                        raise ValueError("OCR 이미지가 10MB를 넘습니다.")
            key = f"{listing_date:%Y-%m-%d}:{hashlib.sha256(content).hexdigest()}"
            cached = key in cache
            start = cache.get(key)
            if cached and start is not None:
                try:
                    cached_date = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
                    if cached_date.date() != listing_date.date():
                        raise ValueError("캐시의 시작 날짜가 목록과 다릅니다.")
                except (TypeError, ValueError):
                    cached = False
            if cached:
                print(f"[Megabox OCR] 동일 이미지 캐시 재사용: {start or '시간 미확인'}")
            else:
                with TemporaryDirectory() as folder:
                    image = Path(folder) / "banner"
                    image.write_bytes(content)
                    result = subprocess.run(
                        ["tesseract", str(image), "stdout", "-l", "kor+eng", "--psm", "11"],
                        capture_output=True, text=True, encoding="utf-8", check=True, timeout=30,
                    )
                try:
                    start = extract_coupon_start_date(result.stdout, listing_date)
                except ValueError as error:
                    print(f"::warning::[Megabox OCR] {error}")
                    start = None
                cache[key] = start
                changed = True
                print(f"[Megabox OCR] 이미지 인식 완료: {start or '시간 미확인'}")
            if start is not None:
                candidates.add(start)
    except (RequestException, OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        print(f"::warning::[Megabox OCR] 시간 미확인으로 유지합니다: {error}")
        return None

    if changed and cache_path is not None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(cache_path)
        except OSError as error:
            print(f"::warning::[Megabox OCR] 캐시를 저장할 수 없습니다: {error}")
    return candidates.pop() if len(candidates) == 1 else None
