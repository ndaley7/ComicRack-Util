import test from 'node:test';
import assert from 'node:assert/strict';
import { parseArgs } from '../src/cli.js';

test('parses paddle OCR CUDA flag', () => {
  const args = parseArgs([
    '--zip',
    'sample.cbz',
    '--out',
    'sample-translatedENG.cbz',
    '--super-saver',
    '--paddle-ocr-cuda'
  ]);

  assert.equal(args.inputZipPath, 'sample.cbz');
  assert.equal(args.outputZipPath, 'sample-translatedENG.cbz');
  assert.equal(args.superSaverMode, true);
  assert.equal(args.paddleOcrCuda, true);
});
