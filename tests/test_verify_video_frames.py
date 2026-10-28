from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SKILL = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL / "scripts" / "verify_video_frames.py"
spec = importlib.util.spec_from_file_location("verify_video_frames", MODULE_PATH)
assert spec and spec.loader
verify_video_frames = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_video_frames)


class VerifyVideoFramesTests(unittest.TestCase):
    def test_timestamp_parsing_and_neighbor_window(self) -> None:
        self.assertEqual(verify_video_frames.parse_timestamp("01:02:03"), 3723)
        self.assertEqual(verify_video_frames.parse_timestamp("02:03"), 123)
        self.assertEqual(verify_video_frames.neighboring_times(1, 2), {"before": None, "after": 3})
        self.assertEqual(verify_video_frames.neighboring_times(20, 2), {"before": 18, "after": 22})

    def test_ffmpeg_extraction_command_uses_a_fixed_sample_and_png_output(self) -> None:
        command = verify_video_frames.build_ffmpeg_command(
            "ffmpeg", Path("lesson.mp4"), 42, Path("sample.png")
        )
        self.assertLess(command.index("-ss"), command.index("-i"))
        self.assertIn("42", command)
        self.assertEqual(command[command.index("-frames:v") + 1], "1")
        self.assertEqual(command[-1], "sample.png")


if __name__ == "__main__":
    unittest.main()
