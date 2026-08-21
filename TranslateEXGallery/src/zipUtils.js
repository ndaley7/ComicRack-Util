import path from 'node:path';
import AdmZip from 'adm-zip';

export const SUPPORTED_IMAGE_EXTENSIONS = new Set([
  '.jpg',
  '.jpeg',
  '.png',
  '.webp',
  '.bmp',
  '.gif',
  '.tif',
  '.tiff'
]);

export function isSupportedImageEntry(entryName) {
  return SUPPORTED_IMAGE_EXTENSIONS.has(path.posix.extname(entryName).toLowerCase());
}

export function findInfoEntry(entries) {
  return entries.find((entry) => !entry.isDirectory && path.posix.basename(entry.entryName).toLowerCase() === 'info.txt');
}

export function listImageEntries(entries) {
  return entries.filter((entry) => !entry.isDirectory && isSupportedImageEntry(entry.entryName));
}

export function defaultOutputPath(inputZipPath) {
  const parsed = path.parse(inputZipPath);
  return path.join(parsed.dir, `${parsed.name}-translatedENG${parsed.ext || '.zip'}`);
}

export function readZip(zipPath) {
  return new AdmZip(zipPath);
}

export function buildTranslatedZip(sourceZip, replacements) {
  const outputZip = new AdmZip();

  for (const entry of sourceZip.getEntries()) {
    if (entry.isDirectory) {
      outputZip.addFile(entry.entryName, Buffer.alloc(0));
      continue;
    }

    const replacement = replacements.get(entry.entryName);
    outputZip.addFile(entry.entryName, replacement ?? entry.getData());
  }

  return outputZip;
}
