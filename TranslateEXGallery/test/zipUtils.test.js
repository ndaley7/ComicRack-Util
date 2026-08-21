import test from 'node:test';
import assert from 'node:assert/strict';
import AdmZip from 'adm-zip';
import { defaultOutputPath, findInfoEntry, isSupportedImageEntry, listImageEntries } from '../src/zipUtils.js';

test('finds nested info.txt and supported image entries', () => {
  const zip = new AdmZip();
  zip.addFile('Gallery/', Buffer.alloc(0));
  zip.addFile('Gallery/MCN_1.webp', Buffer.from('image'));
  zip.addFile('Gallery/notes.md', Buffer.from('notes'));
  zip.addFile('Gallery/info.txt', Buffer.from('Language: Chinese'));

  const entries = zip.getEntries();

  assert.equal(findInfoEntry(entries).entryName, 'Gallery/info.txt');
  assert.deepEqual(listImageEntries(entries).map((entry) => entry.entryName), ['Gallery/MCN_1.webp']);
  assert.equal(isSupportedImageEntry('nested/page.tiff'), true);
  assert.equal(isSupportedImageEntry('nested/page.txt'), false);
});

test('defaults translated output name to original name plus -translatedENG', () => {
  assert.equal(defaultOutputPath('C:\\Comics\\sample.zip'), 'C:\\Comics\\sample-translatedENG.zip');
});
