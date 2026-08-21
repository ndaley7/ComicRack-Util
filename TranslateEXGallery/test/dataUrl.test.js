import test from 'node:test';
import assert from 'node:assert/strict';
import { decodeDataUrl } from '../src/dataUrl.js';

test('decodes base64 image data URLs', () => {
  const result = decodeDataUrl('data:image/png;base64,aGVsbG8=');

  assert.equal(result.mimeType, 'image/png');
  assert.equal(result.buffer.toString('utf8'), 'hello');
});

test('rejects invalid data URLs', () => {
  assert.throws(() => decodeDataUrl('not a data url'), /valid data URL/);
});
