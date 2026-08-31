#!/usr/bin/env python3
"""JSON-lines PaddleOCR text detector for TranslateEXGallery super-saver mode."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")


INSTALL_HELP = (
    "PaddleOCR is required for Super-Saver mode. Install PaddlePaddle for your "
    "platform, then install PaddleOCR. PaddlePaddle currently publishes Windows "
    "wheels for Python 3.9 through 3.13. For CPU on many Windows setups: "
    "py -3.13 -m pip install -r TranslateEXGallery\\requirements-super-saver.txt"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect whether images contain text using PaddleOCR.")
    parser.add_argument("images", nargs="*", help="Image paths to inspect outside JSON-lines mode.")
    parser.add_argument("--jsonl", action="store_true", help="Read requests from stdin and write JSON responses to stdout.")
    parser.add_argument("--min-score", type=float, default=0.6, help="Minimum PaddleOCR box score counted as text.")
    return parser.parse_args()


def import_text_detection() -> Any:
    try:
        from paddleocr import TextDetection
    except Exception as exc:  # pragma: no cover - exercised only when dependency is missing
        python_details = f"Python executable: {sys.executable}\nPython version: {sys.version.split()[0]}"
        raise RuntimeError(f"{INSTALL_HELP}\n{python_details}\nImport error: {exc}") from exc
    return TextDetection


def to_plain(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(item) for item in value]
    if hasattr(value, "res"):
        return to_plain(value.res)
    try:
        return to_plain(dict(value))
    except Exception:
        return value


def numeric_values(value: Any) -> list[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [float(value)]
    if isinstance(value, (list, tuple)):
        values: list[float] = []
        for item in value:
            values.extend(numeric_values(item))
        return values
    return []


def collect_key_values(value: Any, wanted_keys: set[str]) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in wanted_keys:
                found.append(item)
            found.extend(collect_key_values(item, wanted_keys))
    elif isinstance(value, list):
        for item in value:
            found.extend(collect_key_values(item, wanted_keys))
    return found


def count_polys(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    return 0


class PaddleTextDetector:
    def __init__(self, min_score: float) -> None:
        with contextlib.redirect_stdout(sys.stderr):
            TextDetection = import_text_detection()
            self.model = TextDetection(engine="paddle")
        self.min_score = min_score

    def detect(self, image_path: str) -> dict[str, Any]:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Image does not exist: {path}")

        with contextlib.redirect_stdout(sys.stderr):
            output = self.model.predict(str(path))
        plain = to_plain(output)
        score_values: list[float] = []
        for scores in collect_key_values(plain, {"dt_scores", "scores"}):
            score_values.extend(numeric_values(scores))

        box_count = 0
        for polys in collect_key_values(plain, {"dt_polys", "polys", "boxes"}):
            box_count = max(box_count, count_polys(polys))

        if score_values:
            passing_scores = [score for score in score_values if score >= self.min_score]
            has_text = bool(passing_scores)
            box_count = max(box_count, len(passing_scores))
            max_score = max(score_values)
        else:
            has_text = box_count > 0
            max_score = None

        return {
            "has_text": has_text,
            "box_count": box_count if has_text else 0,
            "max_score": max_score,
        }


def jsonl_loop(detector: PaddleTextDetector) -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        request: dict[str, Any] = {}
        try:
            request = json.loads(line)
            response = {"id": request.get("id")}
            response.update(detector.detect(str(request.get("image_path", ""))))
        except Exception as exc:
            response = {"id": request.get("id"), "error": str(exc)}
        print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


def main() -> int:
    args = parse_args()
    detector = PaddleTextDetector(min_score=args.min_score)
    if args.jsonl:
        return jsonl_loop(detector)

    for image_path in args.images:
        response = {"image_path": image_path}
        response.update(detector.detect(image_path))
        print(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
