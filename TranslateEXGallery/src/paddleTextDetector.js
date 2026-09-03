import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_DETECTOR_SCRIPT = path.resolve(MODULE_DIR, '..', 'scripts', 'paddle_text_detector.py');

function defaultPythonCommand() {
  if (process.env.PADDLEOCR_PYTHON) {
    return [process.env.PADDLEOCR_PYTHON];
  }
  if (process.platform === 'win32') {
    const localPython313 = process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, 'Programs', 'Python', 'Python313', 'python.exe')
      : '';
    if (localPython313 && fs.existsSync(localPython313)) {
      return [localPython313];
    }
    return ['py', '-3.13'];
  }
  if (process.env.PYTHON) {
    return [process.env.PYTHON];
  }
  return ['python3'];
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function detectionImagePath(workDir, filename, imageBuffer, sourceHash) {
  const ext = path.extname(filename) || '.img';
  const basename = sourceHash || sha256(imageBuffer);
  return path.join(workDir, 'text-detection', `${basename}${ext}`);
}

export function detectorProcessArgs({ pythonArgs = [], detectorScript, minScore, device }) {
  const args = [
    ...pythonArgs,
    detectorScript,
    '--jsonl',
    '--min-score',
    String(minScore)
  ];
  if (device) {
    args.push('--device', device);
  }
  return args;
}

export class PaddleOcrTextDetector {
  constructor({
    pythonCommand,
    pythonExecutable,
    detectorScript = DEFAULT_DETECTOR_SCRIPT,
    device,
    minScore = 0.6,
    timeoutMs = 180000
  } = {}) {
    this.pythonCommand = pythonCommand ?? (pythonExecutable ? [pythonExecutable] : defaultPythonCommand());
    this.detectorScript = detectorScript;
    this.device = device;
    this.minScore = minScore;
    this.timeoutMs = timeoutMs;
    this.process = null;
    this.pending = new Map();
    this.nextId = 1;
    this.stdoutBuffer = '';
    this.stderrBuffer = '';
  }

  async hasText({ filename, imageBuffer, workDir, sourceHash }) {
    if (!Buffer.isBuffer(imageBuffer)) {
      throw new Error(`Cannot run PaddleOCR text detection for ${filename}: imageBuffer must be a Buffer.`);
    }

    const imagePath = detectionImagePath(workDir, filename, imageBuffer, sourceHash);
    fs.mkdirSync(path.dirname(imagePath), { recursive: true });
    if (!fs.existsSync(imagePath)) {
      fs.writeFileSync(imagePath, imageBuffer);
    }

    const response = await this.request({ image_path: imagePath, filename });
    return {
      hasText: Boolean(response.has_text),
      boxCount: Number.isInteger(response.box_count) ? response.box_count : 0,
      maxScore: typeof response.max_score === 'number' ? response.max_score : undefined
    };
  }

  request(payload) {
    this.ensureStarted();
    const id = String(this.nextId);
    this.nextId += 1;

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`PaddleOCR text detection timed out after ${this.timeoutMs} ms for ${payload.filename}.`));
      }, this.timeoutMs);

      this.pending.set(id, { resolve, reject, timer });
      this.process.stdin.write(`${JSON.stringify({ id, ...payload })}\n`, (error) => {
        if (!error) {
          return;
        }
        clearTimeout(timer);
        this.pending.delete(id);
        reject(error);
      });
    });
  }

  ensureStarted() {
    if (this.process) {
      return;
    }

    const [pythonExecutableName, ...pythonArgs] = this.pythonCommand;
    this.process = spawn(pythonExecutableName, detectorProcessArgs({
      pythonArgs,
      detectorScript: this.detectorScript,
      minScore: this.minScore,
      device: this.device
    }), {
      stdio: ['pipe', 'pipe', 'pipe']
    });

    this.process.stdout.setEncoding('utf8');
    this.process.stdout.on('data', (chunk) => this.handleStdout(chunk));
    this.process.stderr.setEncoding('utf8');
    this.process.stderr.on('data', (chunk) => {
      this.stderrBuffer += chunk;
    });
    this.process.on('error', (error) => this.rejectAll(error));
    this.process.on('exit', (code, signal) => {
      const detail = this.stderrBuffer.trim();
      const suffix = detail ? `\n${detail}` : '';
      this.rejectAll(new Error(`PaddleOCR text detector exited with code ${code ?? 'unknown'}${signal ? ` and signal ${signal}` : ''}.${suffix}`));
      this.process = null;
    });
  }

  handleStdout(chunk) {
    this.stdoutBuffer += chunk;
    while (true) {
      const newline = this.stdoutBuffer.indexOf('\n');
      if (newline < 0) {
        break;
      }

      const line = this.stdoutBuffer.slice(0, newline).trim();
      this.stdoutBuffer = this.stdoutBuffer.slice(newline + 1);
      if (line) {
        this.handleLine(line);
      }
    }
  }

  handleLine(line) {
    let message;
    try {
      message = JSON.parse(line);
    } catch (error) {
      this.rejectAll(new Error(`PaddleOCR text detector returned invalid JSON: ${line}`));
      return;
    }

    const pending = this.pending.get(String(message.id));
    if (!pending) {
      return;
    }

    clearTimeout(pending.timer);
    this.pending.delete(String(message.id));
    if (message.error) {
      pending.reject(new Error(message.error));
    } else {
      pending.resolve(message);
    }
  }

  rejectAll(error) {
    for (const [id, pending] of this.pending.entries()) {
      clearTimeout(pending.timer);
      this.pending.delete(id);
      pending.reject(error);
    }
  }

  async close() {
    if (!this.process) {
      return;
    }

    const processToClose = this.process;
    await new Promise((resolve) => {
      processToClose.once('exit', resolve);
      processToClose.stdin.end();
      setTimeout(() => {
        if (!processToClose.killed) {
          processToClose.kill();
        }
      }, 1000).unref();
    });
  }
}
