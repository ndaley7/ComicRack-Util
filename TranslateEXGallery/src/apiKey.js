import { execFileSync } from 'node:child_process';

const USER_ENV_KEY = 'HKCU\\Environment';
const MACHINE_ENV_KEY = 'HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment';

function cleanValue(value) {
  const trimmed = String(value ?? '').trim();
  if (!trimmed) {
    return '';
  }

  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1).trim();
  }

  return trimmed;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function readWindowsRegistryEnv(name, execFileSyncImpl = execFileSync) {
  for (const key of [USER_ENV_KEY, MACHINE_ENV_KEY]) {
    try {
      const output = execFileSyncImpl('reg', ['query', key, '/v', name], {
        encoding: 'utf8',
        windowsHide: true
      });

      const pattern = new RegExp(`^\\s*${escapeRegExp(name)}\\s+REG_\\w+\\s+(.+?)\\s*$`, 'im');
      const match = pattern.exec(output);
      const value = cleanValue(match?.[1]);
      if (value) {
        return value;
      }
    } catch {
      // Missing registry values are normal; keep checking other scopes.
    }
  }

  return '';
}

export function resolveToriiApiKey({
  env = process.env,
  platform = process.platform,
  execFileSyncImpl = execFileSync
} = {}) {
  const processValue = cleanValue(env.TORII_API ?? env['%TORII_API%']);
  if (processValue) {
    return processValue;
  }

  if (platform === 'win32') {
    return readWindowsRegistryEnv('TORII_API', execFileSyncImpl);
  }

  return '';
}

export function toriiApiKeyErrorMessage() {
  return [
    'TORII_API is not set for this Node process.',
    '',
    'If you are using cmd.exe, run this in the same terminal before npm start:',
    '  set TORII_API=your_key',
    '',
    'If you are using PowerShell, run this in the same terminal before npm start:',
    '  $env:TORII_API="your_key"',
    '',
    'Note: %TORII_API% is how cmd.exe expands a variable named TORII_API; the actual variable name should be TORII_API.'
  ].join('\n');
}
