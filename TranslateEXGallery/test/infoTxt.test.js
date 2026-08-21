import test from 'node:test';
import assert from 'node:assert/strict';
import { updateLanguageToEnglish } from '../src/infoTxt.js';

test('updates only the main Language metadata line', () => {
  const input = [
    'Title',
    'Language: Chinese \u00a0',
    '',
    'Tags:',
    '> language: chinese',
    ''
  ].join('\r\n');

  const result = updateLanguageToEnglish(input);

  assert.equal(result.sourceLanguage, 'Chinese');
  assert.match(result.updatedText, /Language: English \u00a0\r\n/);
  assert.match(result.updatedText, /> language: chinese\r\n/);
});

test('supports equals separators and mixed case labels', () => {
  const result = updateLanguageToEnglish('LANGUAGE = Japanese\n');

  assert.equal(result.sourceLanguage, 'Japanese');
  assert.equal(result.updatedText, 'LANGUAGE = English\n');
});

test('throws when no metadata language line is found', () => {
  assert.throws(() => updateLanguageToEnglish('> language: chinese\n'), /Language line/);
});
