import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "TranslateEXGallery" / "scripts" / "paddle_text_detector.py"


def load_detector_module():
    spec = importlib.util.spec_from_file_location("paddle_text_detector", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PaddleTextDetectorTests(unittest.TestCase):
    def test_parse_args_accepts_cuda_device_without_importing_paddleocr(self) -> None:
        module = load_detector_module()

        args = module.parse_args(["--jsonl", "--min-score", "0.7", "--device", "gpu:0"])

        self.assertTrue(args.jsonl)
        self.assertEqual(args.min_score, 0.7)
        self.assertEqual(args.device, "gpu:0")


if __name__ == "__main__":
    unittest.main()
