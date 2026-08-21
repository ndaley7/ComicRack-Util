export function decodeDataUrl(dataUrl) {
  if (typeof dataUrl !== 'string') {
    throw new Error('Torii response did not include an image data URL.');
  }

  const match = /^data:([^;,]+)?(;base64)?,(.*)$/s.exec(dataUrl);
  if (!match) {
    throw new Error('Torii response image was not a valid data URL.');
  }

  const [, mimeType = 'application/octet-stream', base64Flag, payload] = match;
  const buffer = base64Flag
    ? Buffer.from(payload, 'base64')
    : Buffer.from(decodeURIComponent(payload), 'utf8');

  if (buffer.length === 0) {
    throw new Error('Torii response image data URL was empty.');
  }

  return { buffer, mimeType };
}
