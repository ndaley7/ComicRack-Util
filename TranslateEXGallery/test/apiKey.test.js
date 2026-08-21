import test from 'node:test';
import assert from 'node:assert/strict';
import { readWindowsRegistryEnv, resolveToriiApiKey, toriiApiKeyErrorMessage } from '../src/apiKey.js';

test('resolves TORII_API from process env', () => {
  assert.equal(resolveToriiApiKey({ env: { TORII_API: 'abc123' }, platform: 'linux' }), 'abc123');
});

test('trims quotes around env values', () => {
  assert.equal(resolveToriiApiKey({ env: { TORII_API: '"abc123"' }, platform: 'linux' }), 'abc123');
});

test('supports a literal %TORII_API% env name as a forgiving fallback', () => {
  assert.equal(resolveToriiApiKey({ env: { '%TORII_API%': 'abc123' }, platform: 'linux' }), 'abc123');
});

test('reads TORII_API from Windows registry output', () => {
  const execFileSyncImpl = () => [
    '',
    'HKEY_CURRENT_USER\\Environment',
    '    TORII_API    REG_SZ    abc123',
    ''
  ].join('\r\n');

  assert.equal(readWindowsRegistryEnv('TORII_API', execFileSyncImpl), 'abc123');
});

test('falls back to Windows registry when process env is missing', () => {
  const execFileSyncImpl = () => [
    '',
    'HKEY_CURRENT_USER\\Environment',
    '    TORII_API    REG_EXPAND_SZ    abc123',
    ''
  ].join('\r\n');

  assert.equal(resolveToriiApiKey({ env: {}, platform: 'win32', execFileSyncImpl }), 'abc123');
});

test('error message explains cmd and PowerShell syntax', () => {
  const message = toriiApiKeyErrorMessage();

  assert.match(message, /set TORII_API=your_key/);
  assert.match(message, /\$env:TORII_API="your_key"/);
  assert.match(message, /%TORII_API%/);
});
