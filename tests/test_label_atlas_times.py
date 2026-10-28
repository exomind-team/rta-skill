from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET


SKILL = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL / 'scripts' / 'label_atlas_times.py'
spec = importlib.util.spec_from_file_location('label_atlas_times', MODULE_PATH)
assert spec and spec.loader
label_atlas_times = importlib.util.module_from_spec(spec)
spec.loader.exec_module(label_atlas_times)

XHTML = 'http://www.w3.org/1999/xhtml'


def make_epub(path: Path, known_caption: bool = True) -> bytes:
    '''Create a tiny EPUB with one matched and one unmatched synthetic page.'''
    known_caption_text = (
        '视觉复核接受的视频候选采样点 00:01:02；非起点、非区间。'
        if known_caption else '原书页面。'
    )
    atlas = f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="{XHTML}"><body>
<section id="atlas-page-sample-001" class="atlas-page" data-source-id="sample" data-page-number="1"
 data-sample-time="00:01:02" data-time-status="accepted_video_sample_point_only">
 <h2>PPT 源页 001</h2><figure><img src="images/page-001.png"/><figcaption>{known_caption_text}</figcaption></figure>
</section>
<section id="atlas-page-sample-002" class="atlas-page" data-source-id="sample" data-page-number="2"
 data-sample-time="unknown" data-time-status="no_match">
 <h2>PPT 源页 002</h2><figure><img src="images/page-002.png"/><figcaption>原书页面。</figcaption></figure>
</section>
</body></html>'''.encode('utf-8')
    entries = {
        'mimetype': b'application/epub+zip',
        'META-INF/container.xml': b'<container/>',
        'OEBPS/atlas-ppt-sample.xhtml': atlas,
        'OEBPS/chapter-001.xhtml': f'<html xmlns="{XHTML}"><body><p>Lesson.</p></body></html>'.encode(),
        'OEBPS/images/page-001.png': b'synthetic-page-one',
        'OEBPS/images/page-002.png': b'synthetic-page-two',
    }
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', entries.pop('mimetype'), compress_type=zipfile.ZIP_STORED)
        for name, content in entries.items():
            archive.writestr(name, content, compress_type=zipfile.ZIP_DEFLATED)
    return hashlib.sha256(b'synthetic-page-one').digest()


class LabelAtlasTimesTests(unittest.TestCase):
    def test_labels_unknown_page_and_preserves_assets_and_known_caption(self) -> None:
        '''Unknown pages get a visible label; accepted captions stay single.'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.epub'
            output = root / 'labeled.epub'
            image_hash = make_epub(source)

            report = label_atlas_times.label_epub(source, output)

            self.assertEqual(report['pages'], 2)
            self.assertEqual(report['known_sample_points'], 1)
            self.assertEqual(report['unknown_time_pages'], 1)
            self.assertEqual(report['labels_added_or_updated'], 1)
            self.assertEqual(label_atlas_times.check_epub(output)['missing_visible_labels'], 0)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist()[0], 'mimetype')
                self.assertEqual(archive.getinfo('mimetype').compress_type, zipfile.ZIP_STORED)
                self.assertIsNone(archive.testzip())
                self.assertEqual(
                    hashlib.sha256(archive.read('OEBPS/images/page-001.png')).digest(),
                    image_hash,
                )
                self.assertEqual(
                    archive.read('OEBPS/images/page-002.png'),
                    b'synthetic-page-two',
                )
                root_xhtml = ET.fromstring(archive.read('OEBPS/atlas-ppt-sample.xhtml'))
                text = ''.join(root_xhtml.itertext())
                self.assertIn('00:01:02', text)
                self.assertIn('非起点、非区间', text)
                self.assertIn('视频采样时间：未知', text)
                self.assertEqual(text.count('采样点'), 1)
                self.assertEqual(text.count('视频采样时间：未知'), 1)
                with zipfile.ZipFile(source) as source_archive:
                    original = ET.fromstring(
                        source_archive.read('OEBPS/atlas-ppt-sample.xhtml')
                    )
                for label in list(root_xhtml.iter(f'{{{XHTML}}}p')):
                    if 'atlas-time-status' in label.attrib.get('class', '').split():
                        parent = next(
                            node for node in root_xhtml.iter()
                            if label in list(node)
                        )
                        parent.remove(label)
                self.assertEqual(
                    ET.tostring(root_xhtml),
                    ET.tostring(original),
                    'timestamp labels must not alter other atlas content',
                )

    def test_labels_known_page_when_no_visible_time_exists(self) -> None:
        '''An accepted timestamp is made visible if its caption omits it.'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.epub'
            output = root / 'labeled.epub'
            make_epub(source, known_caption=False)

            report = label_atlas_times.label_epub(source, output)

            self.assertEqual(report['labels_added_or_updated'], 2)
            with zipfile.ZipFile(output) as archive:
                content = ET.fromstring(archive.read('OEBPS/atlas-ppt-sample.xhtml'))
            text = ''.join(content.itertext())
            self.assertIn('视频采样点：00:01:02', text)
            self.assertIn('视频采样时间：未知', text)

    def test_check_detects_missing_unknown_label(self) -> None:
        '''Check mode reports missing labels without changing the EPUB.'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.epub'
            make_epub(source)

            report = label_atlas_times.check_epub(source)
            self.assertEqual(report['status'], 'fail')
            self.assertEqual(report['missing_visible_labels'], 1)

    def test_time_status_and_value_must_agree(self) -> None:
        '''Contradictory metadata must not be presented as accepted time.'''
        bad_pages = (
            ('00:01:02', 'no_match'),
            ('unknown', 'accepted_video_sample_point_only'),
            ('00:1:02', 'accepted_video_sample_point_only'),
        )
        for sample_time, status in bad_pages:
            with self.subTest(sample_time=sample_time, status=status):
                content = f'''<html xmlns="{XHTML}"><body>
<section id="atlas-page-test-001" class="atlas-page" data-source-id="test" data-page-number="1"
 data-sample-time="{sample_time}" data-time-status="{status}"><h2>Page</h2></section>
</body></html>'''.encode('utf-8')
                with self.assertRaises(ValueError):
                    label_atlas_times.label_atlas_document(content, 'atlas.xhtml')

    def test_collapsed_or_hidden_text_does_not_satisfy_visible_unknown_label(self) -> None:
        '''A timestamp hidden in details cannot pass the visible-page check.'''
        content = f'''<html xmlns="{XHTML}"><body>
<section id="atlas-page-test-001" class="atlas-page" data-source-id="test"
 data-page-number="1" data-sample-time="unknown" data-time-status="no_match">
 <h2>PPT 源页 001</h2><details><summary>来源说明</summary>
 <p>视频采样时间：未知</p></details><figure><img src="page.png"/></figure>
</section></body></html>'''.encode('utf-8')

        labeled, report = label_atlas_times.label_atlas_document(content, 'atlas.xhtml')

        self.assertEqual(report['labels_changed'], 1)
        tree = ET.fromstring(labeled)
        visible_label = next(
            node for node in tree.iter(f'{{{XHTML}}}p')
            if 'atlas-time-status' in node.attrib.get('class', '').split()
        )
        self.assertEqual(visible_label.text, '视频采样时间：未知')

    def test_labeling_is_idempotent_and_refuses_overwrite(self) -> None:
        '''A verified output is stable and an existing path is preserved.'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.epub'
            output = root / 'labeled.epub'
            make_epub(source)
            label_atlas_times.label_epub(source, output)

            report = label_atlas_times.check_epub(output)
            self.assertEqual(report['missing_visible_labels'], 0)
            with self.assertRaises(FileExistsError):
                label_atlas_times.label_epub(source, output)


if __name__ == '__main__':
    unittest.main()
