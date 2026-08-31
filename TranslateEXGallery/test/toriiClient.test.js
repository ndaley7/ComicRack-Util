import test from 'node:test';
import assert from 'node:assert/strict';
import { ToriiClient } from '../src/toriiClient.js';

test('gets credits from Torii credits endpoint', async () => {
  const calls = [];
  const client = new ToriiClient({
    apiKey: 'key',
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return Response.json({ credits: 145.25 });
    }
  });

  assert.equal(await client.getCredits(), 145.25);
  assert.equal(calls[0].url, 'https://api.toriitranslate.com/api/credits');
  assert.equal(calls[0].options.headers.Authorization, 'Bearer key');
});

test('returns translated bytes and remaining credits from upload response header', async () => {
  const client = new ToriiClient({
    apiKey: 'key',
    minRequestGapMs: 0,
    fetchImpl: async () => Response.json(
      { image: 'data:image/png;base64,aGVsbG8=' },
      { headers: { credits: '144.25' } }
    )
  });

  const result = await client.translateImage({
    filename: 'page.webp',
    imageBuffer: Buffer.from('image'),
    sourceLanguage: 'Chinese'
  });

  assert.equal(result.imageBuffer.toString('utf8'), 'hello');
  assert.equal(result.creditsRemaining, 144.25);
});

test('retries transient Torii HTTP 520 responses', async () => {
  const calls = [];
  const client = new ToriiClient({
    apiKey: 'key',
    maxAttempts: 2,
    retryBaseMs: 0,
    minRequestGapMs: 0,
    fetchImpl: async () => {
      calls.push(true);
      if (calls.length === 1) {
        return new Response('<!DOCTYPE html><html><body>cloudflare issue</body></html>', { status: 520 });
      }
      return Response.json({ image: 'data:image/png;base64,aGVsbG8=' });
    }
  });

  const result = await client.translateImage({
    filename: 'page.jpg',
    imageBuffer: Buffer.from('image'),
    sourceLanguage: 'Korean'
  });

  assert.equal(calls.length, 2);
  assert.equal(result.imageBuffer.toString('utf8'), 'hello');
});

test('summarizes HTML error pages from Torii', async () => {
  const client = new ToriiClient({
    apiKey: 'key',
    maxAttempts: 1,
    minRequestGapMs: 0,
    fetchImpl: async () => new Response('<!DOCTYPE html><html><head><title>Error</title></head></html>', { status: 520 })
  });

  await assert.rejects(
    () => client.translateImage({
      filename: 'page.jpg',
      imageBuffer: Buffer.from('image'),
      sourceLanguage: 'Korean'
    }),
    (error) => {
      assert.match(error.message, /Torii returned HTTP 520 for page\.jpg: HTML error page returned by upstream service/);
      assert.doesNotMatch(error.message, /<!DOCTYPE html>/i);
      return true;
    }
  );
});
