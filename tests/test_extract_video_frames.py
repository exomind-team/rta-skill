from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL / "scripts" / "extract_video_frames.py"
spec = importlib.util.spec_from_file_location("extract_video_frames", MODULE_PATH)
assert spec and spec.loader
extract_video_frames = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract_video_frames)


class ExtractVideoFramesTests(unittest.TestCase):
    def test_command_only_exports_png_and_metadata_candidates(self) -> None:
        command = extract_video_frames.build_command(
            "deck-extract", Path("lesson.mp4"), Path("out"), 1.0, 0.9, 2, ["0.7,0,0.3,1"]
        )
        self.assertIn("--no-pdf", command)
        self.assertIn("--no-pptx", command)
        self.assertIn("--no-zip", command)
        self.assertEqual(command.count("--ignore-region"), 1)

    def test_manifest_sorts_mutated_detection_times_without_touching_raw_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [
                {"index": 1, "timestamp_seconds": 30.0, "timestamp_formatted": "00:00:30", "filename": "slide_001.png"},
                {"index": 2, "timestamp_seconds": 21.0, "timestamp_formatted": "00:00:21", "filename": "slide_002.png"},
            ]
            for row in rows:
                (root / row["filename"]).write_bytes(b"fake png")
            raw = {"total_slides": 2, "video_info": {"filename": "synthetic.mp4"}, "slides": rows}
            raw_path = root / "slides_metadata.json"
            raw_path.write_text(json.dumps(raw), encoding="utf-8")

            manifest = extract_video_frames.chronological_manifest(root)

            self.assertFalse(manifest["source_metadata_order_was_chronological"])
            self.assertEqual([row["timestamp_seconds"] for row in manifest["frames"]], [21.0, 30.0])
            self.assertEqual([row["source_detection_index"] for row in manifest["frames"]], [2, 1])
            self.assertEqual(manifest['frames'][0]['size_bytes'], len(b'fake png'))
            self.assertEqual(
                manifest['frames'][0]['sha256'], hashlib.sha256(b'fake png').hexdigest()
            )
            self.assertEqual(json.loads(raw_path.read_text(encoding="utf-8"))["slides"], rows)
            self.assertIn("candidate", manifest["frames"][0]["time_semantics"])

    def test_empty_frame_does_not_produce_completed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'empty.png').write_bytes(b'')
            (root / 'slides_metadata.json').write_text(json.dumps({
                'slides': [{'filename': 'empty.png', 'timestamp_seconds': 1.0}],
            }), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'empty image'):
                extract_video_frames.chronological_manifest(root)


if __name__ == "__main__":
    unittest.main()
