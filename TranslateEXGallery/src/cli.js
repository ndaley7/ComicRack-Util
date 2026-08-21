#!/usr/bin/env node
import path from 'node:path';
import { createInterface } from 'node:readline/promises';
import { stdin as input, stdout as output } from 'node:process';
import { translateGalleryZip } from './processor.js';
import { ToriiClient } from './toriiClient.js';
import { defaultOutputPath } from './zipUtils.js';

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--zip' || arg === '-z') {
      args.inputZipPath = argv[index + 1];
      index += 1;
    } else if (arg === '--out' || arg === '-o') {
      args.outputZipPath = argv[index + 1];
      index += 1;
    } else if (!args.inputZipPath) {
      args.inputZipPath = arg;
    }
  }
  return args;
}

function printProgress(event) {
  if (event.type === 'start') {
    console.log(`Found ${event.imageCount} image(s). Source language: ${event.sourceLanguage || 'unknown'}.`);
    if (event.creditsBefore !== undefined) {
      console.log(`Credits before: ${event.creditsBefore}`);
    }
  } else if (event.type === 'image-start') {
    console.log(`[${event.index}/${event.total}] Translating ${event.filename}`);
  } else if (event.type === 'image-complete') {
    const creditsText = event.creditsRemaining !== undefined ? ` Credits remaining: ${event.creditsRemaining}` : '';
    console.log(`[${event.index}/${event.total}] Done ${event.filename}.${creditsText}`);
  } else if (event.type === 'credits-error') {
    console.warn(`Could not read Torii credits ${event.phase} translation: ${event.error.message}`);
  } else if (event.type === 'skipped') {
    console.log(`Skipped: ${event.reason}`);
  } else if (event.type === 'complete') {
    console.log(`Wrote translated ZIP: ${event.outputZipPath}`);
    if (event.creditsAfter !== undefined) {
      console.log(`Credits after: ${event.creditsAfter}`);
    }
    if (event.creditsUsed !== undefined) {
      console.log(`Credits used: ${event.creditsUsed}`);
    }
  }
}

async function promptForMissingArgs(args) {
  const rl = createInterface({ input, output });
  try {
    if (!args.inputZipPath) {
      args.inputZipPath = (await rl.question('ZIP file path: ')).trim();
    }

    if (!args.outputZipPath) {
      const suggestedOutput = defaultOutputPath(args.inputZipPath);
      const answer = (await rl.question(`Output ZIP path [${suggestedOutput}]: `)).trim();
      args.outputZipPath = answer || suggestedOutput;
    }
  } finally {
    rl.close();
  }

  return args;
}

async function main() {
  const args = await promptForMissingArgs(parseArgs(process.argv.slice(2)));

  const result = await translateGalleryZip({
    inputZipPath: path.resolve(args.inputZipPath),
    outputZipPath: path.resolve(args.outputZipPath),
    createToriiClient: () => new ToriiClient(),
    onProgress: printProgress
  });

  if (result.skipped) {
    console.log('No translation was attempted.');
    return;
  }

  console.log(`Translated ${result.imageCount} image(s) from ${result.sourceLanguage || 'the detected language'} to English.`);
  if (result.creditsBefore !== undefined || result.creditsAfter !== undefined || result.creditsUsed !== undefined) {
    console.log(`Credit summary: before=${result.creditsBefore ?? 'unknown'}, after=${result.creditsAfter ?? 'unknown'}, used=${result.creditsUsed ?? 'unknown'}`);
  }
}

main().catch((error) => {
  console.error(`Error: ${error.message}`);
  process.exitCode = 1;
});
