import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import AdmZip from 'adm-zip';
import { translateGalleryZip } from '../src/processor.js';

test('translates image entries, updates info.txt, and leaves source zip unchanged', async () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'translate-ex-gallery-'));
  const inputZipPath = path.join(tempDir, 'sample.zip');
  const outputZipPath = path.join(tempDir, 'sample.translated.zip');

  const inputZip = new AdmZip();
  inputZip.addFile('Gallery/MCN_1.webp', Buffer.from('original-image-1'));
  inputZip.addFile('Gallery/MCN_2.webp', Buffer.from('original-image-2'));
  inputZip.addFile('Gallery/info.txt', Buffer.from('Title\r\nLanguage: Chinese \u00a0\r\n> language: chinese\r\n', 'utf8'));
  inputZip.addFile('Gallery/notes.txt', Buffer.from('keep-me'));
  inputZip.writeZip(inputZipPath);

  const translated = new Map([
    ['Gallery/MCN_1.webp', Buffer.from('translated-image-1')],
    ['Gallery/MCN_2.webp', Buffer.from('translated-image-2')]
  ]);

  const calls = [];
  const creditBalances = [145.25, 142.75];
  const toriiClient = {
    async getCredits() {
      return creditBalances.shift();
    },
    async translateImage({ filename, imageBuffer, sourceLanguage }) {
      calls.push({ filename, imageBuffer: imageBuffer.toString('utf8'), sourceLanguage });
      return {
        imageBuffer: translated.get(filename),
        creditsRemaining: filename.endsWith('MCN_1.webp') ? 144.25 : 143.25
      };
    }
  };

  const events = [];
  const result = await translateGalleryZip({
    inputZipPath,
    outputZipPath,
    toriiClient,
    onProgress: (event) => events.push(event)
  });

  assert.equal(result.sourceLanguage, 'Chinese');
  assert.equal(result.imageCount, 2);
  assert.equal(result.creditsBefore, 145.25);
  assert.equal(result.creditsAfter, 142.75);
  assert.equal(result.creditsUsed, 2.5);
  assert.equal(result.estimatedCostUsd, 2.5 * (13 / 6000));
  assert.equal(events.find((event) => event.type === 'complete').estimatedCostUsd, 2.5 * (13 / 6000));
  assert.deepEqual(
    events.filter((event) => event.type === 'image-complete').map((event) => event.creditsRemaining),
    [144.25, 143.25]
  );
  assert.deepEqual(calls, [
    { filename: 'Gallery/MCN_1.webp', imageBuffer: 'original-image-1', sourceLanguage: 'Chinese' },
    { filename: 'Gallery/MCN_2.webp', imageBuffer: 'original-image-2', sourceLanguage: 'Chinese' }
  ]);

  const outputZip = new AdmZip(outputZipPath);
  assert.equal(outputZip.readAsText('Gallery/info.txt'), 'Title\r\nLanguage: English \u00a0\r\n> language: chinese\r\n');
  assert.equal(outputZip.readFile('Gallery/MCN_1.webp').toString('utf8'), 'translated-image-1');
  assert.equal(outputZip.readFile('Gallery/MCN_2.webp').toString('utf8'), 'translated-image-2');
  assert.equal(outputZip.readFile('Gallery/notes.txt').toString('utf8'), 'keep-me');

  const originalZip = new AdmZip(inputZipPath);
  assert.equal(originalZip.readFile('Gallery/MCN_1.webp').toString('utf8'), 'original-image-1');
  assert.equal(originalZip.readAsText('Gallery/info.txt'), 'Title\r\nLanguage: Chinese \u00a0\r\n> language: chinese\r\n');
});

test('skips without Torii calls when ZIP filename contains the word English', async () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'translate-ex-gallery-'));
  const inputZipPath = path.join(tempDir, 'sample English.zip');

  const inputZip = new AdmZip();
  inputZip.addFile('Gallery/MCN_1.webp', Buffer.from('original-image-1'));
  inputZip.addFile('Gallery/info.txt', Buffer.from('Language: Chinese\r\n', 'utf8'));
  inputZip.writeZip(inputZipPath);

  const events = [];
  const result = await translateGalleryZip({
    inputZipPath,
    createToriiClient: () => {
      throw new Error('Torii client should not be created for skipped archives.');
    },
    onProgress: (event) => events.push(event)
  });

  assert.equal(result.skipped, true);
  assert.match(result.reason, /English/);
  assert.deepEqual(events, [{ type: 'skipped', reason: result.reason }]);
});

test('skips without Torii calls when info.txt is missing', async () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'translate-ex-gallery-'));
  const inputZipPath = path.join(tempDir, 'sample.zip');

  const inputZip = new AdmZip();
  inputZip.addFile('Gallery/MCN_1.webp', Buffer.from('original-image-1'));
  inputZip.writeZip(inputZipPath);

  const events = [];
  const result = await translateGalleryZip({
    inputZipPath,
    createToriiClient: () => {
      throw new Error('Torii client should not be created when info.txt is missing.');
    },
    onProgress: (event) => events.push(event)
  });

  assert.equal(result.skipped, true);
  assert.match(result.reason, /info\.txt/);
  assert.deepEqual(events, [{ type: 'skipped', reason: result.reason }]);
});

test('translates cbz archives with cbz output extension', async () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'translate-ex-gallery-'));
  const inputZipPath = path.join(tempDir, 'sample.cbz');

  const inputZip = new AdmZip();
  inputZip.addFile('Gallery/MCN_1.webp', Buffer.from('original-image-1'));
  inputZip.addFile('Gallery/info.txt', Buffer.from('Language: Chinese\r\n', 'utf8'));
  inputZip.writeZip(inputZipPath);

  const result = await translateGalleryZip({
    inputZipPath,
    toriiClient: {
      async translateImage() {
        return Buffer.from('translated-image-1');
      }
    }
  });

  assert.equal(result.skipped, false);
  assert.equal(path.basename(result.outputZipPath), 'sample-translatedENG.cbz');

  const outputZip = new AdmZip(result.outputZipPath);
  assert.equal(outputZip.readAsText('Gallery/info.txt'), 'Language: English\r\n');
  assert.equal(outputZip.readFile('Gallery/MCN_1.webp').toString('utf8'), 'translated-image-1');
});
