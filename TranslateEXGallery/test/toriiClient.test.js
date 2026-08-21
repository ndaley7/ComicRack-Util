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
