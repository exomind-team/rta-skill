from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile


SKILL = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL / "scripts" / "insert_video_figures.py"
spec = importlib.util.spec_from_file_location("insert_video_figures", MODULE_PATH)
assert spec and spec.loader
insert_video_figures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(insert_video_figures)

X = "http://www.w3.org/1999/xhtml"
OPF = "http://www.idpf.org/2007/opf"


def make_epub(path: Path) -> None:
    files = {
        "mimetype": b"application/epub+zip",
        "META-INF/container.xml": (
            b'<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            b'<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>'
        ),
        "OEBPS/content.opf": (
            b'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            b'<manifest><item id="chapter" href="chapter-001.xhtml" media-type="application/xhtml+xml"/>'
            b'<item id="sources" href="sources.xhtml" media-type="application/xhtml+xml"/>'
            b'<item id="css" href="style.css" media-type="text/css"/></manifest><spine/></package>'
        ),
        "OEBPS/chapter-001.xhtml": (
            f'<html xmlns="{X}"><body><p id="edited-p001" class="proofread">Edited text</p>'
            '<details id="p001"><summary>Original</summary></details><p id="p002">Next</p></body></html>'
        ).encode(),
        "OEBPS/sources.xhtml": f'<html xmlns="{X}"><body><h1>Sources</h1></body></html>'.encode(),
        "OEBPS/style.css": b"body { color: black; }\n",
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)


def add_atlas_page(path: Path, video: Path, atlas_image: bytes) -> None:
    with zipfile.ZipFile(path) as source:
        files = {name: source.read(name) for name in source.namelist() if name != "mimetype"}
    package = ET.fromstring(files["OEBPS/content.opf"])
    manifest = package.find(f"{{{OPF}}}manifest")
    assert manifest is not None
    ET.SubElement(manifest, f"{{{OPF}}}item", {
        "id": "atlas", "href": "atlas-ppt-001.xhtml", "media-type": "application/xhtml+xml",
    })
    ET.SubElement(manifest, f"{{{OPF}}}item", {
        "id": "page-image", "href": "images/page.png", "media-type": "image/png",
    })
    files["OEBPS/content.opf"] = ET.tostring(package, encoding="utf-8", xml_declaration=True)
    files["OEBPS/atlas-ppt-001.xhtml"] = (
        f'<html xmlns="{X}"><body><section id="atlas-page-001-001" class="atlas-page" '
        'data-source-id="001" data-page-number="1" data-sample-time="unknown" '
        'data-time-status="unknown_no_accepted_mapping"><h2>PPT源页001</h2>'
        '<p class="atlas-time-status small">视频采样时间：未知</p>'
        '<figure><img src="images/page.png" alt="Synthetic atlas image"/></figure></section></body></html>'
    ).encode()
    files["OEBPS/images/page.png"] = atlas_image
    files["OEBPS/sources.xhtml"] = (
        f'<html xmlns="{X}"><body><section id="src001">'
        f'<p id="video-source-001">源视频：{video}</p></section></body></html>'
    ).encode()
    with zipfile.ZipFile(path, "w") as target:
        target.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            target.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)


class InsertVideoFiguresTests(unittest.TestCase):
    def test_reuses_atlas_asset_and_applies_direct_page_sample_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.epub", root / "output.epub"
            raw_frame, video = root / "raw-frame.png", root / "lesson.mp4"
            atlas_image = b"synthetic atlas page bytes"
            raw_frame.write_bytes(b"synthetic video frame bytes")
            video.write_bytes(b"synthetic video bytes")
            make_epub(source)
            add_atlas_page(source, video, atlas_image)
            mapping = root / "mapping.json"
            mapping.write_text(json.dumps({
                "figures": [{
                    "figure_id": "fig-video-page-reuse",
                    "chapter_id": "src001",
                    "chapter_path": "OEBPS/chapter-001.xhtml",
                    "source_id": "video-source-001",
                    "existing_source_id": "video-source-001",
                    "existing_source_section_id": "src001",
                    "existing_source_video": str(video),
                    "anchor_id": "edited-p001",
                    "caption": "A directly matched slide sample.",
                    "atlas_page_href": "atlas-ppt-001.xhtml#atlas-page-001-001",
                    "atlas_page_link_text": "查看PPT源页001",
                    "atlas_return_link_text": "返回正文视频画面 00:00:01",
                    "frames": [{
                        "reuse_epub_asset": "images/page.png",
                        "reuse_epub_asset_sha256": hashlib.sha256(atlas_image).hexdigest(),
                        "source_frame": str(raw_frame),
                        "source_frame_sha256": hashlib.sha256(raw_frame.read_bytes()).hexdigest(),
                        "timestamp": "00:00:01",
                        "label": "Matched page",
                        "alt": "The same tree state shown in PPT page 001.",
                    }],
                }],
                "page_time_matches": [{
                    "atlas_page_href": "atlas-ppt-001.xhtml#atlas-page-001-001",
                    "source_id": "001",
                    "page_number": "1",
                    "sample_time": "00:00:01",
                    "source_video": str(video),
                    "source_video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                    "source_frame": str(raw_frame),
                    "source_frame_sha256": hashlib.sha256(raw_frame.read_bytes()).hexdigest(),
                    "evidence": "direct_visual_match_synthetic_test",
                }],
            }), encoding="utf-8")

            report = insert_video_figures.insert_figures(source, output, mapping)

            self.assertEqual(report["frames"], 1)
            self.assertTrue(report["inserted"][0]["reused_epub_asset"])
            self.assertEqual(report["inserted"][0]["epub_asset"], "OEBPS/images/page.png")
            self.assertEqual(report["page_time_matches"][0]["sample_time"], "00:00:01")
            with zipfile.ZipFile(source) as original:
                original_members = set(original.namelist())
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), original_members)
                self.assertEqual(hashlib.sha256(archive.read("OEBPS/images/page.png")).hexdigest(),
                                 hashlib.sha256(atlas_image).hexdigest())
                chapter = ET.fromstring(archive.read("OEBPS/chapter-001.xhtml"))
                figure = next(node for node in chapter.iter(f"{{{X}}}figure")
                              if node.attrib.get("id") == "fig-video-page-reuse")
                image = next(figure.iter(f"{{{X}}}img"))
                self.assertEqual(image.attrib["src"], "images/page.png")
                links = {node.attrib.get("href") for node in figure.iter(f"{{{X}}}a")}
                self.assertIn("atlas-ppt-001.xhtml#atlas-page-001-001", links)
                atlas = ET.fromstring(archive.read("OEBPS/atlas-ppt-001.xhtml"))
                page = next(node for node in atlas.iter(f"{{{X}}}section")
                            if node.attrib.get("id") == "atlas-page-001-001")
                self.assertEqual(page.attrib["data-sample-time"], "00:00:01")
                self.assertEqual(page.attrib["data-time-status"], "accepted_video_sample_point_only")
                self.assertIn("视频采样点：00:00:01", "".join(page.itertext()))
                self.assertTrue(any(node.attrib.get("href") == "chapter-001.xhtml#fig-video-page-reuse"
                                    for node in page.iter(f"{{{X}}}a")))

    def test_inserts_group_after_original_disclosure_and_records_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.epub"
            output = root / "output.epub"
            frame_a, frame_b, raw_frame, video = root / "a.png", root / "b.png", root / "raw.png", root / "lesson.mp4"
            frame_a.write_bytes(b"frame-a")
            frame_b.write_bytes(b"frame-b")
            raw_frame.write_bytes(b"raw full screenshot")
            video.write_bytes(b"synthetic video")
            mapping = root / "mapping.json"
            mapping.write_text(json.dumps({
                "figures": [{
                    "figure_id": "fig-video-src001-p001",
                    "chapter_id": "lesson-with-semantic-id",
                    "chapter_path": "OEBPS/chapter-001.xhtml",
                    "source_id": "video-frame-source-src001",
                    "chapter_title": "Synthetic lesson",
                    "anchor_id": "edited-p001",
                    "caption": "Two complementary frames.",
                    "source_video": str(video),
                    "source_video_sha256": "a" * 64,
                    "frames": [
                        {"image": str(frame_a), "source_frame": str(raw_frame),
                         "crop_box_normalized_ltrb": [0.1, 0.1, 0.9, 0.9],
                         "timestamp": "00:01:00", "label": "A", "alt": "Frame A"},
                        {"image": str(frame_b), "timestamp_seconds": 63, "label": "B", "alt": "Frame B"},
                    ],
                }]
            }), encoding="utf-8")
            make_epub(source)

            report = insert_video_figures.insert_figures(source, output, mapping)

            self.assertEqual(report["figure_groups"], 1)
            self.assertEqual(report["frames"], 2)
            self.assertGreater(report["checked_local_references"], 0)
            self.assertEqual(report["inserted"][0]["source_frame"], str(raw_frame.resolve()))
            self.assertEqual(report["inserted"][0]["crop_box_normalized_ltrb"], [0.1, 0.1, 0.9, 0.9])
            self.assertTrue(report["sha256"])
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist()[0], "mimetype")
                self.assertEqual(archive.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
                chapter = ET.fromstring(archive.read("OEBPS/chapter-001.xhtml"))
                body = chapter.find(f"{{{X}}}body")
                ids = [node.attrib.get("id") for node in list(body)]
                self.assertEqual(ids[:3], ["edited-p001", "p001", "fig-video-src001-p001"])
                figure = next(node for node in chapter.iter(f"{{{X}}}figure"))
                self.assertEqual(len(list(figure.iter(f"{{{X}}}img"))), 2)
                labels = [node.text for node in figure.iter(f"{{{X}}}p")
                          if "video-frame-label" in node.attrib.get("class", "").split()]
                self.assertEqual(labels, ["A · 00:01:00（候选采样点）", "B · 00:01:03（候选采样点）"])
                figure_link = next(node for node in figure.iter(f"{{{X}}}a"))
                self.assertEqual(figure_link.attrib["href"], "sources.xhtml#video-frame-source-src001")
                sources = ET.fromstring(archive.read("OEBPS/sources.xhtml"))
                self.assertTrue(any(node.attrib.get("id") == "video-frame-source-src001" for node in sources.iter()))
                source_link = next(node for node in sources.iter(f"{{{X}}}a"))
                self.assertEqual(source_link.attrib["href"], "chapter-001.xhtml#fig-video-src001-p001")
                stylesheet = archive.read("OEBPS/style.css").decode()
                self.assertIn("source-mapped video frame groups", stylesheet)
                self.assertEqual(sum(node.tag == f"{{{X}}}script" for node in chapter.iter()), 0)
                self.assertIsNone(archive.testzip())

    def test_original_first_layout_does_not_skip_the_next_paragraph_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.epub", root / "output.epub"
            frame, video = root / "frame.png", root / "lesson.mp4"
            frame.write_bytes(b"frame")
            video.write_bytes(b"video")
            make_epub(source)
            with zipfile.ZipFile(source) as archive:
                files = {name: archive.read(name) for name in archive.namelist() if name != "mimetype"}
            files["OEBPS/chapter-001.xhtml"] = (
                f'<html xmlns="{X}"><body>'
                '<details id="p001" class="source-comparison"><summary>Original one</summary></details>'
                '<p id="edited-p001" class="proofread">Edited one</p>'
                '<details id="p002" class="source-comparison"><summary>Original two</summary></details>'
                '<p id="edited-p002" class="proofread">Edited two</p>'
                '</body></html>'
            ).encode()
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
                for name, data in files.items():
                    archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
            mapping = root / "mapping.json"
            mapping.write_text(json.dumps({"figures": [{
                "figure_id": "fig-video-original-first",
                "chapter_id": "lesson-src001",
                "chapter_path": "OEBPS/chapter-001.xhtml",
                "anchor_id": "edited-p001",
                "source_unit_id": "src001-p001",
                "source_video": str(video),
                "caption": "A figure for the first edited paragraph.",
                "frames": [{"image": str(frame), "timestamp": "00:00:01", "alt": "A frame"}],
            }]}), encoding="utf-8")

            insert_video_figures.insert_figures(source, output, mapping)

            with zipfile.ZipFile(output) as archive:
                chapter = ET.fromstring(archive.read("OEBPS/chapter-001.xhtml"))
                body = chapter.find(f"{{{X}}}body")
                self.assertIsNotNone(body)
                ids = [node.attrib.get("id") for node in list(body)]
                self.assertEqual(ids, [
                    "p001", "edited-p001", "fig-video-original-first",
                    "p002", "edited-p002",
                ])

    def test_refuses_to_overwrite_input_or_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.epub", root / "output.epub"
            frame, video = root / "frame.png", root / "lesson.mp4"
            frame.write_bytes(b"frame")
            video.write_bytes(b"video")
            mapping = root / "mapping.json"
            mapping.write_text(json.dumps({"figures": []}), encoding="utf-8")
            make_epub(source)
            with self.assertRaises(ValueError):
                insert_video_figures.insert_figures(source, source, mapping)
            output.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                insert_video_figures.insert_figures(source, output, mapping)

    def test_reuses_existing_video_source_paragraph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.epub", root / "output.epub"
            frame, video = root / "frame.png", str(root / "lesson.mp4")
            frame.write_bytes(b"frame")
            make_epub(source)
            with zipfile.ZipFile(source) as archive:
                files = {name: archive.read(name) for name in archive.namelist() if name != "mimetype"}
            files["OEBPS/sources.xhtml"] = (
                f'<html xmlns="{X}"><body><h1>Sources</h1><p>源视频：{video}</p></body></html>'.encode()
            )
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
                for name, data in files.items():
                    archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
            mapping = root / "mapping.json"
            mapping.write_text(json.dumps({"figures": [{
                "figure_id": "fig-video-reuse",
                "chapter_id": "src001",
                "anchor_id": "edited-p001",
                "source_id": "video-frame-source-src001-existing",
                "existing_source_id": "video-frame-source-src001-existing",
                "existing_source_section_id": "source-entry-src001",
                "existing_source_video": video,
                "caption": "A linked frame.",
                "frames": [{"image": str(frame), "timestamp": "00:00:01", "alt": "A frame"}],
            }]}), encoding="utf-8")

            # Bind the known video paragraph to a specific source section.
            with zipfile.ZipFile(source) as archive:
                files = {name: archive.read(name) for name in archive.namelist() if name != "mimetype"}
            files["OEBPS/sources.xhtml"] = (
                f'<html xmlns="{X}"><body><section id="source-entry-src001">'
                f'<p id="video-frame-source-src001-existing">源视频：{video}</p>'
                '</section></body></html>'
            ).encode()
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
                for name, data in files.items():
                    archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

            report = insert_video_figures.insert_figures(source, output, mapping)

            self.assertEqual(report["source_videos"], 0)
            with zipfile.ZipFile(output) as archive:
                sources = ET.fromstring(archive.read("OEBPS/sources.xhtml"))
                path_rows = [node for node in sources.iter(f"{{{X}}}p") if video in "".join(node.itertext())]
                self.assertEqual(len(path_rows), 1)
                self.assertEqual(path_rows[0].attrib.get("id"), "video-frame-source-src001-existing")
                self.assertTrue(any(
                    node.tag == f"{{{X}}}a" and node.attrib.get("href") == "chapter-001.xhtml#fig-video-reuse"
                    for node in path_rows[0]
                ))
                chapter = ET.fromstring(archive.read("OEBPS/chapter-001.xhtml"))
                label = next(node for node in chapter.iter(f"{{{X}}}p")
                             if "video-frame-label" in node.attrib.get("class", "").split())
                self.assertEqual(label.text, "视频画面 · 00:00:01（候选采样点）")


    def test_reuses_existing_source_section_by_id_when_video_path_is_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.epub", root / "output.epub"
            frame = root / "frame.png"
            video = str(root / "lesson.mp4")
            frame.write_bytes(b"frame")
            make_epub(source)
            with zipfile.ZipFile(source) as archive:
                files = {name: archive.read(name) for name in archive.namelist() if name != "mimetype"}
            files["OEBPS/sources.xhtml"] = (
                f'<html xmlns="{X}"><body>'
                f'<section id="video-source-existing"><p>视频原件：{video}</p></section>'
                f'<section><p>重复的源视频路径：{video}</p></section>'
                '</body></html>'
            ).encode()
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
                for name, data in files.items():
                    archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
            mapping = root / "mapping.json"
            mapping.write_text(json.dumps({"figures": [{
                "figure_id": "fig-video-existing-section",
                "chapter_id": "src001",
                "anchor_id": "edited-p001",
                "source_id": "video-source-existing",
                "existing_source_id": "video-source-existing",
                "existing_source_section_id": "video-source-existing",
                "existing_source_video": video,
                "caption": "Another linked frame.",
                "frames": [{"image": str(frame), "timestamp": "00:00:02", "alt": "A frame"}],
            }]}), encoding="utf-8")

            report = insert_video_figures.insert_figures(source, output, mapping)

            self.assertEqual(report["source_videos"], 0)
            with zipfile.ZipFile(output) as archive:
                sources = ET.fromstring(archive.read("OEBPS/sources.xhtml"))
                sections = [node for node in sources.iter(f"{{{X}}}section")
                            if node.attrib.get("id") == "video-source-existing"]
                self.assertEqual(len(sections), 1)
                self.assertEqual(sum(node.attrib.get("id") == "video-source-existing" for node in sources.iter()), 1)
                self.assertTrue(any(
                    node.tag == f"{{{X}}}a" and node.attrib.get("href") == "chapter-001.xhtml#fig-video-existing-section"
                    for node in sections[0].iter()
                ))
                self.assertEqual(sum("重复的源视频路径" in "".join(node.itertext())
                                     for node in sources.iter(f"{{{X}}}p")), 1)

    def test_existing_video_reuse_is_scoped_to_the_requested_source_section(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.epub", root / "output.epub"
            frame, video = root / "frame.png", str(root / "lesson.mp4")
            frame.write_bytes(b"frame")
            make_epub(source)
            with zipfile.ZipFile(source) as archive:
                files = {name: archive.read(name) for name in archive.namelist() if name != "mimetype"}
            files["OEBPS/sources.xhtml"] = (
                f'<html xmlns="{X}"><body><section id="wrong-source"><p>源视频：{video}</p></section>'
                '<section id="expected-source"></section></body></html>'
            ).encode()
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
                for name, data in files.items():
                    archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
            mapping = root / "mapping.json"
            mapping.write_text(json.dumps({"figures": [{
                "figure_id": "fig-video-wrong-source",
                "chapter_id": "src001",
                "anchor_id": "edited-p001",
                "source_id": "video-source-src001",
                "existing_source_section_id": "expected-source",
                "existing_source_video": video,
                "frames": [{"image": str(frame), "timestamp": "00:00:01", "alt": "A frame"}],
            }]}), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "inside section 'expected-source'"):
                insert_video_figures.insert_figures(source, output, mapping)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
