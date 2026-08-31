import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
import { decodeInfoText, updateLanguageToEnglish } from './infoTxt.js';
import { PaddleOcrTextDetector } from './paddleTextDetector.js';
import { buildTranslatedZip, defaultOutputPath, findInfoEntry, listImageEntries, readZip } from './zipUtils.js';

export const CREDIT_PRICE_USD = 13 / 6000;

function roundCredits(value) {
  return typeof value === 'number' ? Math.round(value * 100) / 100 : undefined;
}

function estimateCostUsd(creditsUsed) {
  return typeof creditsUsed === 'number' ? creditsUsed * CREDIT_PRICE_USD : undefined;
}

async function getCreditsIfAvailable(toriiClient, onProgress, phase) {
  if (!toriiClient) {
    return undefined;
  }
  if (typeof toriiClient.getCredits !== 'function') {
    return undefined;
  }

  try {
    return await toriiClient.getCredits();
  } catch (error) {
    onProgress({ type: 'credits-error', phase, error });
    return undefined;
  }
}

function normalizeTranslateResult(result) {
  if (Buffer.isBuffer(result)) {
    return { imageBuffer: result, creditsRemaining: undefined };
  }

  return {
    imageBuffer: result?.imageBuffer,
    creditsRemaining: result?.creditsRemaining
  };
}

function hasEnglishWordInFilename(filePath) {
  return /\benglish\b/i.test(path.basename(filePath));
}

function isGifImageEntry(entryName) {
  return path.posix.extname(entryName).toLowerCase() === '.gif';
}

function sha256(bufferOrText) {
  return crypto.createHash('sha256').update(bufferOrText).digest('hex');
}

function defaultWorkDir(outputZipPath) {
  return `${outputZipPath}.work`;
}

function sourceSignature(inputZipPath) {
  const stat = fs.statSync(inputZipPath);
  return {
    inputZipPath,
    size: stat.size,
    mtimeMs: stat.mtimeMs
  };
}

function cacheFilename(entryName) {
  const ext = path.posix.extname(entryName) || '.img';
  return `${sha256(entryName)}${ext}`;
}

function manifestPath(workDir) {
  return path.join(workDir, 'manifest.json');
}

function sameSourceSignature(left, right) {
  return left?.inputZipPath === right.inputZipPath
    && left?.size === right.size
    && left?.mtimeMs === right.mtimeMs;
}

function readManifest(workDir, signature) {
  try {
    const manifest = JSON.parse(fs.readFileSync(manifestPath(workDir), 'utf8'));
    if (manifest.version === 1 && sameSourceSignature(manifest.source, signature) && typeof manifest.images === 'object') {
      return normalizeManifest(manifest);
    }
  } catch (error) {
    if (error.code !== 'ENOENT') {
      return null;
    }
  }
  return null;
}

function writeManifest(workDir, manifest) {
  fs.mkdirSync(workDir, { recursive: true });
  fs.writeFileSync(manifestPath(workDir), JSON.stringify(manifest, null, 2), 'utf8');
}

function prepareManifest(workDir, signature) {
  const existing = readManifest(workDir, signature);
  if (existing) {
    return existing;
  }
  fs.rmSync(workDir, { recursive: true, force: true });
  return {
    version: 1,
    source: signature,
    images: {},
    textDetection: {}
  };
}

function cachedImageBuffer(workDir, manifest, entryName, sourceHash) {
  const cacheEntry = manifest.images[entryName];
  if (!cacheEntry || cacheEntry.sourceHash !== sourceHash || typeof cacheEntry.cacheFile !== 'string') {
    return undefined;
  }

  const cachePath = path.join(workDir, cacheEntry.cacheFile);
  try {
    return fs.readFileSync(cachePath);
  } catch (error) {
    if (error.code !== 'ENOENT') {
      throw error;
    }
    return undefined;
  }
}

function writeCachedImage(workDir, manifest, entryName, sourceHash, imageBuffer) {
  const cacheFile = cacheFilename(entryName);
  const cachePath = path.join(workDir, cacheFile);
  fs.mkdirSync(workDir, { recursive: true });
  fs.writeFileSync(cachePath, imageBuffer);
  manifest.images[entryName] = {
    sourceHash,
    cacheFile
  };
  writeManifest(workDir, manifest);
}

function normalizeManifest(manifest) {
  if (!manifest || typeof manifest !== 'object') {
    return manifest;
  }
  if (!manifest.images || typeof manifest.images !== 'object') {
    manifest.images = {};
  }
  if (!manifest.textDetection || typeof manifest.textDetection !== 'object') {
    manifest.textDetection = {};
  }
  return manifest;
}

function cachedTextDetection(manifest, entryName, sourceHash) {
  const cacheEntry = manifest.textDetection?.[entryName];
  if (!cacheEntry || cacheEntry.sourceHash !== sourceHash || typeof cacheEntry.hasText !== 'boolean') {
    return undefined;
  }

  return {
    hasText: cacheEntry.hasText,
    boxCount: Number.isInteger(cacheEntry.boxCount) ? cacheEntry.boxCount : 0,
    maxScore: typeof cacheEntry.maxScore === 'number' ? cacheEntry.maxScore : undefined,
    cached: true
  };
}

function writeCachedTextDetection(workDir, manifest, entryName, sourceHash, detection) {
  manifest.textDetection[entryName] = {
    sourceHash,
    hasText: Boolean(detection.hasText),
    boxCount: Number.isInteger(detection.boxCount) ? detection.boxCount : 0,
    maxScore: typeof detection.maxScore === 'number' ? detection.maxScore : undefined
  };
  writeManifest(workDir, manifest);
}

export async function translateGalleryZip({
  inputZipPath,
  outputZipPath = defaultOutputPath(inputZipPath),
  workDir,
  toriiClient,
  createToriiClient,
  superSaverMode = false,
  textDetector,
  createTextDetector,
  onProgress = () => {}
}) {
  if (!inputZipPath) {
    throw new Error('A ZIP or CBZ path is required.');
  }

  const resolvedInputPath = path.resolve(inputZipPath);
  const resolvedOutputPath = path.resolve(outputZipPath);
  const resolvedWorkDir = path.resolve(workDir ?? defaultWorkDir(resolvedOutputPath));

  if (!fs.existsSync(resolvedInputPath)) {
    throw new Error(`ZIP or CBZ file does not exist: ${resolvedInputPath}`);
  }

  if (hasEnglishWordInFilename(resolvedInputPath)) {
    const reason = 'Archive filename contains the word English.';
    onProgress({ type: 'skipped', reason });
    return {
      skipped: true,
      reason,
      inputZipPath: resolvedInputPath,
      imageCount: 0
    };
  }

  if (resolvedInputPath.toLowerCase() === resolvedOutputPath.toLowerCase()) {
    throw new Error('Output archive path must be different from the input archive path.');
  }

  const sourceZip = readZip(resolvedInputPath);
  const entries = sourceZip.getEntries();
  const infoEntry = findInfoEntry(entries);
  if (!infoEntry) {
    const reason = 'Could not find info.txt anywhere in the archive.';
    onProgress({ type: 'skipped', reason });
    return {
      skipped: true,
      reason,
      inputZipPath: resolvedInputPath,
      imageCount: 0
    };
  }

  const imageEntries = listImageEntries(entries);
  if (imageEntries.length === 0) {
    throw new Error('The archive does not contain any supported image files.');
  }

  const infoText = decodeInfoText(infoEntry.getData());
  const { sourceLanguage, updatedText } = updateLanguageToEnglish(infoText);
  const replacements = new Map([[infoEntry.entryName, Buffer.from(updatedText, 'utf8')]]);
  const signature = sourceSignature(resolvedInputPath);
  const manifest = prepareManifest(resolvedWorkDir, signature);
  let pendingImageCount = 0;
  let translatedImageCount = 0;
  let skippedNoTextImageCount = 0;
  let keptOriginalImageCount = 0;

  for (const entry of imageEntries) {
    if (isGifImageEntry(entry.entryName)) {
      continue;
    }

    const sourceBuffer = entry.getData();
    const sourceHash = sha256(sourceBuffer);
    const cachedBuffer = cachedImageBuffer(resolvedWorkDir, manifest, entry.entryName, sourceHash);
    if (cachedBuffer) {
      replacements.set(entry.entryName, cachedBuffer);
    } else {
      pendingImageCount += 1;
    }
  }

  let activeToriiClient;
  if (pendingImageCount > 0 && !superSaverMode) {
    activeToriiClient = toriiClient ?? createToriiClient?.();
    if (!activeToriiClient) {
      throw new Error('A Torii client is required to translate images.');
    }
  }

  let creditsBefore = await getCreditsIfAvailable(activeToriiClient, onProgress, 'before');

  onProgress({
    type: 'start',
    sourceLanguage,
    imageCount: imageEntries.length,
    outputZipPath: resolvedOutputPath,
    creditsBefore
  });

  let activeTextDetector = textDetector;
  let createdTextDetector;
  try {
    if (pendingImageCount > 0 && superSaverMode && !activeTextDetector) {
      createdTextDetector = createTextDetector?.() ?? new PaddleOcrTextDetector();
      activeTextDetector = createdTextDetector;
    }
    if (pendingImageCount > 0 && superSaverMode && !activeTextDetector) {
      throw new Error('A PaddleOCR text detector is required for Super-Saver mode.');
    }

    for (let index = 0; index < imageEntries.length; index += 1) {
      const entry = imageEntries[index];
      const imageBuffer = entry.getData();
      const sourceHash = sha256(imageBuffer);
      if (isGifImageEntry(entry.entryName)) {
        keptOriginalImageCount += 1;
        onProgress({
          type: 'image-original',
          index: index + 1,
          total: imageEntries.length,
          filename: entry.entryName,
          reason: 'GIF files are copied without translation.'
        });
        continue;
      }

      if (replacements.has(entry.entryName)) {
        translatedImageCount += 1;
        onProgress({ type: 'image-cached', index: index + 1, total: imageEntries.length, filename: entry.entryName });
        continue;
      }

      if (superSaverMode) {
        let detection = cachedTextDetection(manifest, entry.entryName, sourceHash);
        let detectionFailed = false;
        if (!detection) {
          onProgress({ type: 'image-text-start', index: index + 1, total: imageEntries.length, filename: entry.entryName });
          try {
            detection = await activeTextDetector.hasText({
              filename: entry.entryName,
              imageBuffer,
              workDir: resolvedWorkDir,
              sourceHash
            });
            writeCachedTextDetection(resolvedWorkDir, manifest, entry.entryName, sourceHash, detection);
          } catch (error) {
            detectionFailed = true;
            detection = { hasText: true, boxCount: 0, maxScore: undefined };
            onProgress({
              type: 'image-text-error',
              index: index + 1,
              total: imageEntries.length,
              filename: entry.entryName,
              error
            });
          }
        }

        if (!detection.hasText) {
          skippedNoTextImageCount += 1;
          onProgress({
            type: 'image-no-text',
            index: index + 1,
            total: imageEntries.length,
            filename: entry.entryName,
            boxCount: detection.boxCount,
            maxScore: detection.maxScore,
            cached: detection.cached === true
          });
          continue;
        }

        if (!detectionFailed) {
          onProgress({
            type: 'image-text-detected',
            index: index + 1,
            total: imageEntries.length,
            filename: entry.entryName,
            boxCount: detection.boxCount,
            maxScore: detection.maxScore,
            cached: detection.cached === true
          });
        }
      }

      if (!activeToriiClient) {
        activeToriiClient = toriiClient ?? createToriiClient?.();
        if (!activeToriiClient) {
          throw new Error('A Torii client is required to translate images.');
        }
        if (creditsBefore === undefined) {
          creditsBefore = await getCreditsIfAvailable(activeToriiClient, onProgress, 'before');
        }
      }

      onProgress({ type: 'image-start', index: index + 1, total: imageEntries.length, filename: entry.entryName });

      const translateResult = normalizeTranslateResult(await activeToriiClient.translateImage({
        filename: entry.entryName,
        imageBuffer,
        sourceLanguage
      }));

      if (!Buffer.isBuffer(translateResult.imageBuffer)) {
        throw new Error(`Torii did not return translated image bytes for ${entry.entryName}.`);
      }

      translatedImageCount += 1;
      replacements.set(entry.entryName, translateResult.imageBuffer);
      writeCachedImage(resolvedWorkDir, manifest, entry.entryName, sourceHash, translateResult.imageBuffer);
      onProgress({
        type: 'image-complete',
        index: index + 1,
        total: imageEntries.length,
        filename: entry.entryName,
        creditsRemaining: translateResult.creditsRemaining
      });
    }
  } finally {
    await createdTextDetector?.close?.();
  }

  const creditsAfter = await getCreditsIfAvailable(activeToriiClient, onProgress, 'after');
  const creditsUsed = creditsBefore !== undefined && creditsAfter !== undefined
    ? roundCredits(creditsBefore - creditsAfter)
    : undefined;
  const estimatedCostUsd = estimateCostUsd(creditsUsed);
  const outputZip = buildTranslatedZip(sourceZip, replacements);
  outputZip.writeZip(resolvedOutputPath);
  fs.rmSync(resolvedWorkDir, { recursive: true, force: true });

  onProgress({
    type: 'complete',
    outputZipPath: resolvedOutputPath,
    creditsBefore,
    creditsAfter,
    creditsUsed,
    estimatedCostUsd,
    translatedImageCount,
    skippedNoTextImageCount,
    keptOriginalImageCount
  });

  return {
    skipped: false,
    outputZipPath: resolvedOutputPath,
    sourceLanguage,
    imageCount: imageEntries.length,
    translatedImageCount,
    skippedNoTextImageCount,
    keptOriginalImageCount,
    creditsBefore,
    creditsAfter,
    creditsUsed,
    estimatedCostUsd
  };
}
