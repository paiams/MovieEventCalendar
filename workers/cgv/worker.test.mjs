import assert from 'node:assert/strict';
import { mock, test } from 'node:test';
import worker from './worker.mjs';

test('only fetches the fixed CGV feed and preserves upstream failures', async () => {
  const fetch = mock.method(globalThis, 'fetch');
  try {
    for (const status of [200, 403, 503]) {
      const upstream = new Response(status === 200 ? '{"data":{}}' : 'Blocked', { status });
      fetch.mock.mockImplementation(async () => upstream);
      const response = await worker.fetch(new Request('https://worker.example/?url=https://other.example', {
        headers: { Authorization: 'private-client-token' },
      }));
      assert.equal(response, upstream);
      const [url, options] = fetch.mock.calls.at(-1).arguments;
      assert.equal(new URL(url).hostname, 'cgv.co.kr');
      assert.equal(new URL(url).searchParams.get('swrd'), '쿠폰');
      assert.equal(options.headers.Authorization, undefined);
    }

    fetch.mock.mockImplementation(async () => { throw new Error('Upstream unavailable'); });
    await assert.rejects(worker.fetch(), /Upstream unavailable/);
  } finally {
    fetch.mock.restore();
  }
});
