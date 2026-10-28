from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL / "scripts" / "extract_video_batch.py"
spec = importlib.util.spec_from_file_location("extract_video_batch", MODULE_PATH)
assert spec and spec.loader
extract_video_batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract_video_batch)


class ExtractVideoBatchTests(unittest.TestCase):
    def make_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        video = root / "lesson.mp4"
        video.write_bytes(b"synthetic input")
        fake_extractor = root / "fake_extractor.py"
        fake_extractor.write_text(
            "import hashlib, json, pathlib, sys\n"
            "video, output = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])\n"
            "args = sys.argv[3:]\n"
            "fps = float(args[args.index('--fps') + 1])\n"
            "threshold = float(args[args.index('--threshold') + 1])\n"
            "debounce = int(args[args.index('--debounce') + 1])\n"
            "output.mkdir(parents=True, exist_ok=True)\n"
            "(output / 'slide_001.png').write_bytes(b'png')\n"
            "stat = video.stat()\n"
            "manifest = {'source_video': str(video.resolve()), 'source_video_size_bytes': stat.st_size, "
            "'source_video_mtime_ns': stat.st_mtime_ns, 'sample_fps': fps, "
            "'similarity_threshold': threshold, 'debounce_samples': debounce, "
            "'ignore_regions': [], 'detected_frame_count': 1, 'frames': [{'filename': 'slide_001.png', "
            "'size_bytes': 3, 'sha256': hashlib.sha256(b'png').hexdigest()}]}\n"
            "(output / 'slides_chronological.json').write_text(json.dumps(manifest), encoding='utf-8')\n",
            encoding="utf-8",
        )
        inventory = root / "inventory.json"
        inventory.write_text(json.dumps([{"chapter_id": "src001", "video": str(video)}]), encoding="utf-8")
        return video, fake_extractor, inventory

    def make_args(self, root: Path, extractor: Path, inventory: Path):
        return type("Args", (), {
            "manifest": inventory,
            "output_root": root / "out",
            "extractor_script": extractor,
            "tool": "deck-extract",
            "fps": 1.0,
            "threshold": 0.9,
            "debounce": 2,
            "ignore_region": [],
        })()

    def test_batch_is_resumable_and_skips_verified_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, extractor, inventory = self.make_fixture(root)
            args = self.make_args(root, extractor, inventory)

            self.assertEqual(extract_video_batch.run(args), 0)
            self.assertTrue((args.output_root / "src001" / "slide_001.png").is_file())
            self.assertEqual(extract_video_batch.run(args), 0)
            status = json.loads((args.output_root / "batch_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["jobs"]["src001"]["status"], "complete")
            self.assertTrue(status["jobs"]["src001"]["skipped"])
            self.assertEqual(status['jobs']['src001']['frame_verification'], 'sha256')

    def test_interrupted_stage_is_archived_before_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, extractor, inventory = self.make_fixture(root)
            args = self.make_args(root, extractor, inventory)
            stage = args.output_root / ".src001.partial"
            stage.mkdir(parents=True)
            (stage / "partial.bin").write_bytes(b"partial")

            self.assertEqual(extract_video_batch.run(args), 0)
            self.assertTrue((args.output_root / "src001" / "slide_001.png").is_file())
            archives = list(args.output_root.glob(".src001.partial-*"))
            self.assertEqual(len(archives), 1)
            self.assertTrue((archives[0] / "partial.bin").is_file())

    def test_changed_source_video_is_not_silently_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, extractor, inventory = self.make_fixture(root)
            args = self.make_args(root, extractor, inventory)
            self.assertEqual(extract_video_batch.run(args), 0)
            video.write_bytes(b"changed synthetic input")
            with self.assertRaises(FileExistsError):
                extract_video_batch.run(args)

    def test_missing_or_modified_frame_is_not_silently_skipped(self) -> None:
        for altered in (None, b'PNG', b''):
            with self.subTest(altered=altered), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, extractor, inventory = self.make_fixture(root)
                args = self.make_args(root, extractor, inventory)
                self.assertEqual(extract_video_batch.run(args), 0)
                frame = args.output_root / 'src001' / 'slide_001.png'
                if altered is None:
                    frame.unlink()
                else:
                    frame.write_bytes(altered)
                with self.assertRaises(FileExistsError):
                    extract_video_batch.run(args)
                status = json.loads((args.output_root / 'batch_status.json').read_text('utf-8'))
                self.assertEqual(status['jobs']['src001']['status'], 'needs_inspection')
                self.assertTrue(frame.parent.is_dir())
                if altered is not None:
                    self.assertEqual(frame.read_bytes(), altered)

    def test_legacy_manifest_checks_existence_without_claiming_hash_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, extractor, inventory = self.make_fixture(root)
            args = self.make_args(root, extractor, inventory)
            self.assertEqual(extract_video_batch.run(args), 0)
            folder = args.output_root / 'src001'
            path = folder / 'slides_chronological.json'
            manifest = json.loads(path.read_text(encoding='utf-8'))
            manifest['frames'] = [{'filename': 'slide_001.png'}]
            path.write_text(json.dumps(manifest), encoding='utf-8')
            self.assertEqual(extract_video_batch.run(args), 0)
            status = json.loads((args.output_root / 'batch_status.json').read_text('utf-8'))
            self.assertEqual(status['jobs']['src001']['frame_verification'], 'existence_only')
            (folder / 'slide_001.png').unlink()
            with self.assertRaises(FileExistsError):
                extract_video_batch.run(args)

    def test_unsafe_frame_reference_cannot_authorize_skip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, extractor, inventory = self.make_fixture(root)
            args = self.make_args(root, extractor, inventory)
            self.assertEqual(extract_video_batch.run(args), 0)
            folder = args.output_root / 'src001'
            path = folder / 'slides_chronological.json'
            manifest = json.loads(path.read_text(encoding='utf-8'))
            for filename in ('../outside.png', '..\\outside.png', '.', 'missing.png'):
                with self.subTest(filename=filename):
                    manifest['frames'] = [{'filename': filename}]
                    path.write_text(json.dumps(manifest), encoding='utf-8')
                    self.assertFalse(extract_video_batch.completed_matches(
                        folder, str(video), 1.0, 0.9, 2, [],
                    ))


if __name__ == "__main__":
    unittest.main()
