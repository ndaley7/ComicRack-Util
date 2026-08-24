import fs from 'node:fs';
import path from 'node:path';
import { decodeInfoText, updateLanguageToEnglish } from './infoTxt.js';
import { buildTranslatedZip, defaultOutputPath, findInfoEntry, listImageEntries, readZip } from './zipUtils.js';

export const CREDIT_PRICE_USD = 13 / 6000;

function roundCredits(value) {
  return typeof value === 'number' ? Math.round(value * 100) / 100 : undefined;
}

function estimateCostUsd(creditsUsed) {
  return typeof creditsUsed === 'number' ? creditsUsed * CREDIT_PRICE_USD : undefined;
}

async function getCreditsIfAvailable(toriiClient, onProgress, phase) {
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

export async function translateGalleryZip({
  inputZipPath,
  outputZipPath = defaultOutputPath(inputZipPath),
  toriiClient,
  createToriiClient,
  onProgress = () => {}
}) {
  if (!inputZipPath) {
    throw new Error('A ZIP or CBZ path is required.');
  }

  const resolvedInputPath = path.resolve(inputZipPath);
  const resolvedOutputPath = path.resolve(outputZipPath);

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
  const activeToriiClient = toriiClient ?? createToriiClient?.();
  if (!activeToriiClient) {
    throw new Error('A Torii client is required to translate images.');
  }

  const creditsBefore = await getCreditsIfAvailable(activeToriiClient, onProgress, 'before');

  onProgress({
    type: 'start',
    sourceLanguage,
    imageCount: imageEntries.length,
    outputZipPath: resolvedOutputPath,
    creditsBefore
  });

  for (let index = 0; index < imageEntries.length; index += 1) {
    const entry = imageEntries[index];
    onProgress({ type: 'image-start', index: index + 1, total: imageEntries.length, filename: entry.entryName });

    const translateResult = normalizeTranslateResult(await activeToriiClient.translateImage({
      filename: entry.entryName,
      imageBuffer: entry.getData(),
      sourceLanguage
    }));

    if (!Buffer.isBuffer(translateResult.imageBuffer)) {
      throw new Error(`Torii did not return translated image bytes for ${entry.entryName}.`);
    }

    replacements.set(entry.entryName, translateResult.imageBuffer);
    onProgress({
      type: 'image-complete',
      index: index + 1,
      total: imageEntries.length,
      filename: entry.entryName,
      creditsRemaining: translateResult.creditsRemaining
    });
  }

  const creditsAfter = await getCreditsIfAvailable(activeToriiClient, onProgress, 'after');
  const creditsUsed = creditsBefore !== undefined && creditsAfter !== undefined
    ? roundCredits(creditsBefore - creditsAfter)
    : undefined;
  const estimatedCostUsd = estimateCostUsd(creditsUsed);
  const outputZip = buildTranslatedZip(sourceZip, replacements);
  outputZip.writeZip(resolvedOutputPath);

  onProgress({ type: 'complete', outputZipPath: resolvedOutputPath, creditsBefore, creditsAfter, creditsUsed, estimatedCostUsd });

  return {
    skipped: false,
    outputZipPath: resolvedOutputPath,
    sourceLanguage,
    imageCount: imageEntries.length,
    creditsBefore,
    creditsAfter,
    creditsUsed,
    estimatedCostUsd
  };
}
