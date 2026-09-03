import test from 'node:test';
import assert from 'node:assert/strict';
import { detectorProcessArgs } from '../src/paddleTextDetector.js';

test('detector process args include device when configured', () => {
  assert.deepEqual(
    detectorProcessArgs({
      pythonArgs: ['-3.13'],
      detectorScript: 'paddle_text_detector.py',
      minScore: 0.6,
      device: 'gpu:0'
    }),
    ['-3.13', 'paddle_text_detector.py', '--jsonl', '--min-score', '0.6', '--device', 'gpu:0']
  );
});

test('detector process args omit device by default', () => {
  assert.deepEqual(
    detectorProcessArgs({
      pythonArgs: [],
      detectorScript: 'paddle_text_detector.py',
      minScore: 0.6
    }),
    ['paddle_text_detector.py', '--jsonl', '--min-score', '0.6']
  );
});
