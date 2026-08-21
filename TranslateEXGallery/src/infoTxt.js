const BOM = '\uFEFF';

export function decodeInfoText(buffer) {
  const text = Buffer.isBuffer(buffer) ? buffer.toString('utf8') : String(buffer);
  return text.startsWith(BOM) ? text.slice(1) : text;
}

export function updateLanguageToEnglish(infoText) {
  const languageLinePattern = /^([ \t]*)(Language)([ \t]*[:=][ \t]*)(.*?)([ \t\u00a0]*)(\r?\n|$)/im;
  const match = languageLinePattern.exec(infoText);

  if (!match) {
    throw new Error('Could not find a metadata Language line in info.txt.');
  }

  const [, indent, label, separator, rawLanguage, trailingWhitespace, lineEnding] = match;
  const sourceLanguage = rawLanguage.trim();
  const replacement = `${indent}${label}${separator}English${trailingWhitespace}${lineEnding}`;

  return {
    sourceLanguage,
    updatedText: `${infoText.slice(0, match.index)}${replacement}${infoText.slice(match.index + match[0].length)}`
  };
}
