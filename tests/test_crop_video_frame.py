from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL / "scripts" / "crop_video_frame.py"
spec = importlib.util.spec_from_file_location("crop_video_frame", MODULE_PATH)
assert spec and spec.loader
crop_video_frame = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crop_video_frame)

HAS_PIL = importlib.util.find_spec("PIL") is not None


class CropVideoFrameTests(unittest.TestCase):
    def test_rejects_crop_box_outside_normalized_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.png", root / "crop.png"
            source.write_bytes(b"synthetic frame")
            with self.assertRaises(ValueError):
                crop_video_frame.crop_image(source, output, (-0.1, 0.2, 0.8, 0.9))

    @unittest.skipUnless(HAS_PIL, "Pillow is installed with the optional video-extract environment")
    def test_crop_records_raw_source_hash_and_pixel_bounds(self) -> None:
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.png", root / "crop.png"
            Image.new("RGB", (100, 80), "white").save(source)

            report = crop_video_frame.crop_image(source, output, (0.1, 0.2, 0.6, 0.7))

            with Image.open(output) as result:
                self.assertEqual(result.size, (50, 40))
            self.assertEqual(report["crop_box_pixels_ltrb"], [10, 16, 60, 56])
            saved_report = json.loads(output.with_suffix(".png.crop.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_report["source_sha256"], report["source_sha256"])
            self.assertEqual(saved_report["output_sha256"], report["output_sha256"])


if __name__ == "__main__":
    unittest.main()
