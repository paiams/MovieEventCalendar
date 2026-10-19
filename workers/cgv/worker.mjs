const CGV_API_URL = 'https://cgv.co.kr/api/v1/common/timeline/more/itgrSrch/searchItgrSrchAll?coCd=A420&swrd=%EC%BF%A0%ED%8F%B0';

export default {
  async fetch() {
    // Only forward this public feed; callers cannot choose an upstream URL or headers.
    return fetch(CGV_API_URL, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': 'https://cgv.co.kr/',
      },
      signal: AbortSignal.timeout(20000),
    });
  },
};
