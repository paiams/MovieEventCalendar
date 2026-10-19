# CGV '스피드 쿠폰' 크롤링 기술 분석 및 구현 전략

## 1. 데이터 수집 접근 방식

*   **타겟 URL**: https://cgv.co.kr/tme/itgrSrch?swrd=쿠폰
*   **수집 방식**: **Requests로 통합 검색 API 호출, Actions에서는 Cloudflare Worker를 통해 중계 가능**
*   **배경**: 2026-10-19 확인 시 로컬 직접 요청은 성공했지만 GitHub 호스팅 실행 환경에서는 Requests, Chrome 연결 방식, 실제 Chromium 모두 CGV의 403 차단 응답을 받았습니다. Cloudflare 공식 Playground에서는 같은 공개 API가 HTTP 200과 영화 쿠폰 13개를 반환했습니다. 스피드 쿠폰과 서프라이즈 쿠폰을 함께 수집하도록 검색어는 '쿠폰'을 사용합니다.

## 2. 기술적 특징 및 보안 우회

*   **세션 쿠키 유지**: 검색 페이지와 API 요청에 같은 `requests.Session`을 사용합니다.
*   **Worker 경유**: `CGV_WORKER_URL` 설정 시 검색 페이지 접속 없이 Worker가 반환한 원본 검색 응답을 기존 파서에 전달합니다. 배포 및 변수 등록 절차는 [백엔드 문서](backend/README.md)를 참고합니다.
*   **요청 헤더 설정**: User-Agent, Referer, Accept 헤더를 실제 웹 요청과 맞춥니다.
*   **응답 검증**: HTTP 오류나 `evntLst` 구조 변경 시 실패 처리하여 빈 데이터를 배포하지 않습니다.
*   **중계 범위 제한**: Worker는 코드에 고정된 공개 API만 호출하며 요청자의 URL·쿠키·인증 헤더를 전달하지 않습니다.

## 3. Response 파싱 및 데이터 추출 로직

응답 내부에서 `evntLst`를 찾아 이벤트 목록을 추출합니다.

*   **영화 제목 정규식 추출**: `[영화제목] 스피드 쿠폰` 또는 `[영화제목] 서프라이즈 쿠폰` 형태에서 대괄호 내부의 텍스트만 추출해 온전한 제목을 얻습니다.
*   **이미지 URL 조합**: `mduBanrPhyscFilePathnm`(이미지 경로)과 `mduBanrPhyscFnm`(이미지 파일명) 필드를 결합해 `https://cdn.cgv.co.kr/{이미지경로}/{이미지파일명}` 형태의 CDN 주소를 생성합니다.
*   **카테고리 판별**: 원본 이벤트 제목(evntNm)의 키워드를 판별해 '스피드쿠폰' 혹은 '서프라이즈쿠폰'만 수집합니다.
*   **상세 페이지 URL**: 추출한 `evntNo`로 `https://cgv.co.kr/evt/eventDetail?evntNo={evntNo}`를 조합합니다.
