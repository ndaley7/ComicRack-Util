import path from 'node:path';
import { resolveToriiApiKey, toriiApiKeyErrorMessage } from './apiKey.js';
import { decodeDataUrl } from './dataUrl.js';

const TORII_UPLOAD_URL = 'https://api.toriitranslate.com/api/v2/upload';
const TORII_CREDITS_URL = 'https://api.toriitranslate.com/api/credits';

const MIME_TYPES = new Map([
  ['.jpg', 'image/jpeg'],
  ['.jpeg', 'image/jpeg'],
  ['.png', 'image/png'],
  ['.webp', 'image/webp'],
  ['.bmp', 'image/bmp'],
  ['.gif', 'image/gif'],
  ['.tif', 'image/tiff'],
  ['.tiff', 'image/tiff']
]);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetryableStatus(status) {
  return status === 429 || status === 503;
}

function isRetryableNetworkError(error) {
  return error instanceof TypeError || ['ECONNRESET', 'ETIMEDOUT', 'ENOTFOUND', 'EAI_AGAIN'].includes(error?.code);
}

function parseCredits(value) {
  if (value === null || value === undefined || value === '') {
    return undefined;
  }

  const credits = Number(value);
  return Number.isFinite(credits) ? credits : undefined;
}

export class ToriiClient {
  constructor({
    apiKey = resolveToriiApiKey(),
    fetchImpl = globalThis.fetch,
    uploadUrl = TORII_UPLOAD_URL,
    creditsUrl = TORII_CREDITS_URL,
    maxAttempts = 4,
    retryBaseMs = 1500,
    minRequestGapMs = 1000
  } = {}) {
    if (!apiKey) {
      throw new Error(toriiApiKeyErrorMessage());
    }

    if (typeof fetchImpl !== 'function') {
      throw new Error('This Node runtime does not provide fetch. Use Node 18 or newer.');
    }

    this.apiKey = apiKey;
    this.fetch = fetchImpl;
    this.uploadUrl = uploadUrl;
    this.creditsUrl = creditsUrl;
    this.maxAttempts = maxAttempts;
    this.retryBaseMs = retryBaseMs;
    this.minRequestGapMs = minRequestGapMs;
    this.lastRequestStartedAt = 0;
  }

  async getCredits() {
    const response = await this.fetch(this.creditsUrl, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${this.apiKey}`
      }
    });

    if (!response.ok) {
      throw new Error(`Torii credits endpoint returned HTTP ${response.status}: ${await response.text()}`);
    }

    const body = await response.json();
    const credits = parseCredits(body.credits);
    if (credits === undefined) {
      throw new Error('Torii credits endpoint did not return a numeric credits value.');
    }

    return credits;
  }

  async translateImage({ filename, imageBuffer, sourceLanguage }) {
    await this.waitForRequestSlot();

    let lastError;
    for (let attempt = 1; attempt <= this.maxAttempts; attempt += 1) {
      try {
        const response = await this.sendTranslateRequest({ filename, imageBuffer, sourceLanguage });
        if (response.ok) {
          const body = await response.json();
          return {
            imageBuffer: decodeDataUrl(body.image).buffer,
            creditsRemaining: parseCredits(response.headers.get('credits'))
          };
        }

        const responseText = await response.text();
        const message = `Torii returned HTTP ${response.status} for ${filename}: ${responseText}`;
        if (!isRetryableStatus(response.status) || attempt === this.maxAttempts) {
          throw new Error(message);
        }
        lastError = new Error(message);
      } catch (error) {
        if (!isRetryableNetworkError(error) || attempt === this.maxAttempts) {
          throw error;
        }
        lastError = error;
      }

      await sleep(this.retryBaseMs * 2 ** (attempt - 1));
    }

    throw lastError;
  }

  async waitForRequestSlot() {
    const now = Date.now();
    const waitMs = Math.max(0, this.lastRequestStartedAt + this.minRequestGapMs - now);
    if (waitMs > 0) {
      await sleep(waitMs);
    }
    this.lastRequestStartedAt = Date.now();
  }

  async sendTranslateRequest({ filename, imageBuffer, sourceLanguage }) {
    const ext = path.extname(filename).toLowerCase();
    const formData = new FormData();
    formData.append('file', new Blob([imageBuffer], { type: MIME_TYPES.get(ext) ?? 'application/octet-stream' }), path.basename(filename));
    formData.append('target_lang', 'en');
    formData.append('translator', 'gemini-3.1-flash-lite');
    formData.append('font', 'wildwords');
    formData.append('text_align', 'auto');
    formData.append('stroke_disabled', 'false');
    formData.append('min_font_size', '6');
    formData.append('bubbles_only', 'false');

    if (sourceLanguage) {
      formData.append('custom_prompt', `Translate from ${sourceLanguage} to English. Preserve names, sound effects, and natural comic dialogue where possible.`);
    }

    return this.fetch(this.uploadUrl, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.apiKey}`
      },
      body: formData
    });
  }
}
