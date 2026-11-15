# 🎬 MovieEventCalender - Backend

CGV, 메가박스, 롯데시네마 3사의 선착순 할인 이벤트를 자동으로 수집하는 파이프라인입니다.

## 주요 기능

- **3사 병렬 크롤링** — `ThreadPoolExecutor`를 활용한 멀티스레드 기반 동시 수집
- **통합 데이터 모델** — `MovieEvent` 데이터클래스로 3사 데이터를 단일 포맷으로 정규화
- **이중 출력** — 정적 JSON (`events.json`)과 ICS 캘린더 파일 (`events.ics`)을 동시에 생성
- **GitHub Actions 자동화** — 2시간 주기 스케줄링으로 자동 실행

## 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.10+ |
| HTTP 요청 | Requests |
| HTML 파싱 | BeautifulSoup4 |
| CGV 요청 중계 | Cloudflare Workers (무료 플랜) |
| 자동화 | GitHub Actions (cron) |

## 프로젝트 구조

```
backend/
├── main.py                  # 통합 파이프라인 엔트리 포인트
├── requirements.txt         # Python 의존성
└── crawlers/
    ├── models.py            # MovieEvent 공통 데이터 모델
    ├── network.py           # 공통 HTTP 재시도 세션
    ├── cgv.py               # CGV 스피드쿠폰 크롤러
    ├── megabox.py           # 메가박스 빵원티켓·빵원굿즈 크롤러
    ├── megabox_ocr.py       # 굿즈 이미지의 쿠폰 시작 시각 인식·캐시
    └── lottecinema.py       # 롯데시네마 무비싸다구 크롤러
```

## 실행 방법

### 사전 요구사항

- Python 3.10+

### 로컬 실행

```bash
# 가상환경 생성 및 활성화
conda create -n MovieEventCalender python=3.10
conda activate MovieEventCalender

# 의존성 설치
pip install -r requirements.txt

# 크롤러 실행
python main.py
```

### 테스트

외부 사이트에 접속하지 않는 파서·파이프라인 테스트를 실행합니다.

```bash
python -m unittest discover -s tests -v
```

### GitHub Actions에서 CGV가 403으로 차단될 때

`workers/cgv/worker.mjs`는 고정된 CGV 공개 검색 API만 중계합니다. 실패 시 CGV의 이전 데이터를 유지하고 다른 영화관의 갱신은 계속합니다.

저장소 루트에서 Cloudflare 무료 계정에 Worker를 배포한 뒤, 출력된 `workers.dev` 주소를 GitHub 저장소의 Actions 변수 `CGV_WORKER_URL`로 등록합니다. `wrangler.jsonc`의 `placement.region`은 서울 인근(`aws:ap-northeast-2`)에서 API를 호출하도록 설정합니다.

```bash
npx wrangler@4 deploy --config workers/cgv/wrangler.jsonc
gh variable set CGV_WORKER_URL --repo paiams/MovieEventCalendar --body https://movie-event-cgv.YOUR_SUBDOMAIN.workers.dev
node --test workers/cgv/worker.test.mjs
```

로컬에서는 환경 변수 `CGV_WORKER_URL`에 같은 주소를 지정할 수 있습니다. 변수가 없으면 기존 직접 수집 방식을 사용합니다. 이 주소는 공개 피드이므로 비밀 키가 아닙니다. 다른 URL이나 클라이언트 인증 헤더를 중계하지 않습니다.

Workers Free 플랜은 [일 100,000회 요청](https://developers.cloudflare.com/workers/platform/pricing/)을 제공하며, 현재 2시간 주기 수집은 일 12회입니다. 무료 한도 초과나 CGV의 추가 차단 시에는 수집이 실패하고 이전 배포 데이터를 유지합니다. 배포 후에는 GitHub Actions에서도 실제 수집을 확인해야 합니다.

`--temporary`로 배포한 계정은 60분 안에 소유권을 등록하지 않으면 삭제되므로, 운영에는 일반 무료 계정을 사용하세요. 현재 운영 Worker는 `https://movie-event-cgv.kbh1933.workers.dev`입니다.

2026-10-20 [GitHub Actions 실수집 검증](https://github.com/paiams/MovieEventCalendar/actions/runs/39226948478/attempts/2)에서 `cf-placement: remote-ICN`, HTTP 200, CGV 쿠폰 14개와 3사 통합 이벤트 38개를 확인했습니다.

### GitHub Actions (자동)

`.github/workflows/update_events.yml` 워크플로우가 **2시간 간격**으로 자동 실행됩니다.

- `push` (main 브랜치) 시에도 자동으로 작동
- `workflow_dispatch`를 통해 수동으로 실행할 수 있음
- `gh-pages`의 이전 이벤트를 복원한 뒤 영화관별로 수집하며, 실패한 영화관만 이전 데이터를 유지
- 메가박스는 빵원티켓과 빵원굿즈를 수집하고, 개별 상세 조회 실패 시 이전 이벤트를 사용하거나 해당 항목만 건너뜀
- HTML에 시작 시각이 없는 빵원굿즈는 한국어 Tesseract로 상세 이미지를 인식. 명시된 쿠폰 다운로드 날짜가 목록과 일치하고 시각이 하나일 때만 사용
- 이미지 내용의 SHA-256과 목록 날짜로 OCR 결과를 캐시하고 다음 배포에서 복원. 같은 이미지는 다시 인식하지 않으며 이미지가 바뀌면 다시 확인
- OCR 설치·인식 실패나 모호한 안내는 `시간 미확인`으로 유지. 캘린더에는 시간 알림 없는 종일 일정으로 등록하며 다른 이벤트 수집은 계속
- 이전 데이터가 없는 실패 항목은 경고를 남기고 제외하며, 정상적으로 조회된 빈 목록은 그대로 반영
- 전체 영화관이 모두 실패하면 배포를 중단하고 기존 배포 데이터를 유지
- 재시도와 이전 데이터 사용은 자동으로 처리하며 Actions 경고에 기록. 사이트 구조 변경 자체는 코드 수정이 필요

## 데이터 모델 (`MovieEvent`)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | `str` | 고유 식별자 (예: `cgv-12345`) |
| `theater` | `str` | 영화관 코드 (`CGV`, `MEGABOX`, `LOTTECINEMA`) |
| `title` | `str` | 이벤트 제목 |
| `startDate` | `str` | 시작 일시 (`YYYY-MM-DD HH:MM:SS`) |
| `url` | `str` | 상세 페이지 URL |
| `imageUrl` | `str?` | 이미지 URL (선택 사항) |
| `category` | `str?` | 카테고리 (선택 사항) |
| `timeUnknown` | `bool` | 시작 시각 미확인 여부. 기본값 `false`, `true`이면 `startDate`의 날짜만 사용 |

## 출력 파일

크롤링 결과는 `frontend/public/data/` 디렉토리에 저장합니다.

- **`events.json`** — 프론트엔드에서 가져와(Fetch) 렌더링할 이벤트 데이터
- **`events.ics`** — 사용자가 캘린더에 구독할 수 있는 ICS 파일 (10분 전 알림 포함)
- **`megabox-ocr-cache.json`** — 동일 이미지의 OCR 결과 재사용. 로컬에서 OCR을 사용하려면 `tesseract`와 `kor`, `eng` 언어 데이터를 설치

## 관련 문서

- [기획서](../영화%20할인%20통합%20대시보드%20기획서.md) — 서비스 기획 및 핵심 컨셉
- [CGV 크롤링 분석](../CGV%20스피드쿠폰%20크롤링%20분석.md)
- [메가박스 크롤링 분석](../메가박스%20빵원티켓%20크롤링%20분석.md)
- [롯데시네마 크롤링 분석](../롯데시네마%20무비싸다구%20크롤링%20분석.md)
