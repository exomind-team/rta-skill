'''Exercise packaged EPUB projection bindings with synthetic fixtures only.'''
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


SKILL = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL / 'scripts' / 'validate_epub_projection.py'
spec = importlib.util.spec_from_file_location('validate_epub_projection', MODULE_PATH)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


XHTML = 'http://www.w3.org/1999/xhtml'
BODY_IMAGE = b'synthetic body image bytes'
ATLAS_IMAGE = b'synthetic atlas page bytes'


def xhtml_document(body: str) -> bytes:
    return f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="{XHTML}"><head><title>Test fixture</title></head><body>{body}</body></html>'''.encode()


class ValidateEpubProjectionTests(unittest.TestCase):
    '''Check ID/path/hash bindings, not editorial or visual correctness.'''

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.epub = self.root / 'synthetic.epub'
        self.agent_jsonl = self.root / 'agent-readable-current.jsonl'
        self.atlas_manifest = self.root / 'page-atlas-manifest.jsonl'
        self.chapter = xhtml_document(
            '<p id="edited-p001">Synthetic teaching text.</p>'
            '<figure id="figure-ppt-p001" data-source-id="source-a" '
            'data-source-unit-id="lesson-a-p001">'
            '<img src="images/body.png" alt="Synthetic body image." /></figure>'
        )
        self.uncertainties = xhtml_document(
            '<h1>1项未决记录</h1>'
            '<section class="uncertainty-entry" id="u001"><p>Confirm the synthetic term.</p></section>'
        )
        self.atlas = xhtml_document(
            '<section class="atlas-page" id="atlas-p001" data-source-id="source-a" data-page-number="1">'
            '<img src="images/atlas.png" alt="Synthetic atlas page." /></section>'
        )
        self.video_frames = xhtml_document(
            '<section class="atlas-page" id="video-frame-001"><img src="images/atlas.png" '
            'alt="Synthetic video frame." /></section>'
        )
        self.agent_rows = [
            {
                'record_type': 'body_figure',
                'figure_id': 'figure-ppt-p001',
                'chapter_href': 'chapter-001.xhtml',
                'source_id': 'source-a',
                'source_unit_id': 'lesson-a-p001',
                'anchor_id': 'edited-p001',
                'images': [{
                    'image_href': 'images/body.png',
                    'image_sha256': hashlib.sha256(BODY_IMAGE).hexdigest(),
                    'alt_text': 'Synthetic body image.',
                }],
            },
            {
                'record_type': 'uncertainty',
                'uncertainty_id': 'U001',
                'source_locator': 'uncertainties.xhtml#u001',
                'text': 'Confirm the synthetic term.',
            },
        ]
        self.page_rows = [{
            'record_type': 'source_page',
            'source_id': 'source-a',
            'page_number': 1,
            'atlas_document': 'atlas.xhtml',
            'page_anchor': 'atlas-p001',
            'full_page_image_epub_href': 'images/atlas.png',
            'full_page_image_sha256': hashlib.sha256(ATLAS_IMAGE).hexdigest(),
        }]
        self.__write_agent()
        self.__write_manifest()

    def __write_agent(self) -> None:
        self.agent_jsonl.write_text(
            ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in self.agent_rows),
            encoding='utf-8',
        )

    def __write_manifest(self) -> None:
        self.atlas_manifest.write_text(
            ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in self.page_rows),
            encoding='utf-8',
        )

    def __build_epub(self, *, appendix_label: str | None = None, atlas: bytes | None = None) -> None:
        uncertainty_doc = self.uncertainties
        if appendix_label is not None:
            uncertainty_doc = xhtml_document(
                f'<h1>{appendix_label}</h1>'
                '<section class="uncertainty-entry" id="u001"><p>Confirm the synthetic term.</p></section>'
            )
        with zipfile.ZipFile(self.epub, 'w') as package:
            package.writestr('mimetype', b'application/epub+zip', compress_type=zipfile.ZIP_STORED)
            package.writestr('META-INF/container.xml', b'<container/>')
            package.writestr('OEBPS/chapter-001.xhtml', self.chapter)
            package.writestr('OEBPS/uncertainties.xhtml', uncertainty_doc)
            package.writestr('OEBPS/atlas.xhtml', self.atlas if atlas is None else atlas)
            package.writestr('OEBPS/video-frames.xhtml', self.video_frames)
            package.writestr('OEBPS/images/body.png', BODY_IMAGE)
            package.writestr('OEBPS/images/atlas.png', ATLAS_IMAGE)

    def __run(self, external_asset_roots: list[Path] | None = None) -> dict[str, object]:
        return validator.validate_epub_projection(
            self.epub,
            self.agent_jsonl,
            self.atlas_manifest,
            external_asset_roots,
        )

    def test_matching_projection_and_bare_anchor_pass(self) -> None:
        self.__build_epub()
        result = self.__run()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['warnings'], [])
        self.assertRegex(result['validator_sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(result['counts']['agent_body_figure_records'], 1)
        self.assertEqual(result['counts']['atlas_pages_in_manifest'], 1)
        self.assertEqual(result['counts']['atlas_pages_in_xhtml'], 1)
        self.assertTrue(result['checks']['page_atlas_bindings'])

    def test_figure_source_unit_mismatch_fails(self) -> None:
        self.__build_epub()
        with zipfile.ZipFile(self.epub) as source:
            members = {name: source.read(name) for name in source.namelist()}
        members['OEBPS/chapter-001.xhtml'] = xhtml_document(
            '<p id="edited-p001">Synthetic teaching text.</p>'
            '<figure id="figure-ppt-p001" data-source-id="source-a" '
            'data-source-unit-id="wrong-unit"><img src="images/body.png" '
            'alt="Synthetic body image." /></figure>'
        )
        with zipfile.ZipFile(self.epub, 'w') as package:
            for name, data in members.items():
                package.writestr(
                    name,
                    data,
                    compress_type=zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED,
                )
        result = self.__run()
        self.assertIn('body_figure_source_unit_mismatch', {item['code'] for item in result['errors']})

    def test_uncertainty_count_label_must_match_rendered_entries(self) -> None:
        self.__build_epub(appendix_label='2项未决记录')
        result = self.__run()
        self.assertIn('uncertainty_appendix_label_mismatch', {item['code'] for item in result['errors']})

    def test_missing_uncertainty_target_fails(self) -> None:
        self.__build_epub()
        self.agent_rows[1]['source_locator'] = 'uncertainties.xhtml#missing'
        self.__write_agent()
        result = self.__run()
        self.assertIn('uncertainty_target_count_mismatch', {item['code'] for item in result['errors']})

    def test_duplicate_uncertainty_id_and_locator_fail(self) -> None:
        self.__build_epub()
        self.agent_rows.append(dict(self.agent_rows[1]))
        self.__write_agent()
        result = self.__run()
        codes = {item['code'] for item in result['errors']}
        self.assertIn('duplicate_uncertainty_id', codes)
        self.assertIn('duplicate_uncertainty_locator', codes)

    def test_atlas_image_hash_mismatch_fails(self) -> None:
        self.__build_epub()
        self.page_rows[0]['full_page_image_sha256'] = '0' * 64
        self.__write_manifest()
        result = self.__run()
        self.assertIn('atlas_page_display_image_sha256_mismatch', {item['code'] for item in result['errors']})

    def test_external_source_image_hash_is_checked_when_available(self) -> None:
        self.__build_epub()
        external = self.root / 'source-page.png'
        external.write_bytes(ATLAS_IMAGE)
        self.page_rows[0].update({
            'source_image_file': str(external),
            'source_image_sha256': hashlib.sha256(ATLAS_IMAGE).hexdigest(),
        })
        self.__write_manifest()
        result = self.__run()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['counts']['atlas_external_asset_declarations_checked'], 1)
        self.assertEqual(result['counts']['atlas_external_asset_files_hashed'], 1)

    def test_external_source_image_hash_mismatch_fails(self) -> None:
        self.__build_epub()
        external = self.root / 'source-page.png'
        external.write_bytes(ATLAS_IMAGE)
        self.page_rows[0].update({
            'source_image_file': str(external),
            'source_image_sha256': '0' * 64,
        })
        self.__write_manifest()
        result = self.__run()
        self.assertIn('atlas_external_asset_sha256_mismatch', {item['code'] for item in result['errors']})

    def test_relative_source_image_uses_declared_external_root(self) -> None:
        self.__build_epub()
        external_root = self.root / 'source-bundle'
        external = external_root / 'embedded-media' / 'embedded-page-001.jpg'
        external.parent.mkdir(parents=True)
        external.write_bytes(ATLAS_IMAGE)
        self.page_rows[0].update({
            'source_image_file': 'embedded-media/embedded-page-001.jpg',
            'source_image_sha256': hashlib.sha256(ATLAS_IMAGE).hexdigest(),
        })
        self.__write_manifest()
        result = self.__run([external_root])
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['counts']['atlas_external_asset_declarations_checked'], 1)

    def test_full_page_external_file_uses_uncropped_digest_when_path_is_same(self) -> None:
        self.__build_epub()
        external = self.root / 'source-page.png'
        external.write_bytes(ATLAS_IMAGE)
        digest = hashlib.sha256(ATLAS_IMAGE).hexdigest()
        self.page_rows[0].update({
            'full_page_image_file': str(external),
            'uncropped_render_file': str(external),
            'uncropped_render_sha256': digest,
        })
        self.__write_manifest()
        result = self.__run()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['counts']['atlas_external_asset_declarations_checked'], 2)
        self.assertEqual(result['counts']['atlas_external_asset_files_hashed'], 1)

    def test_missing_external_source_image_warns_without_failing_package_check(self) -> None:
        self.__build_epub()
        self.page_rows[0].update({
            'source_image_file': str(self.root / 'not-mounted' / 'source-page.png'),
            'source_image_sha256': hashlib.sha256(ATLAS_IMAGE).hexdigest(),
        })
        self.__write_manifest()
        result = self.__run()
        self.assertEqual(result['status'], 'PASS_WITH_WARNINGS')
        self.assertIn('atlas_external_asset_unavailable', {item['code'] for item in result['warnings']})

    def test_xhtml_atlas_page_without_manifest_row_fails(self) -> None:
        extra_page = self.atlas.replace(
            b'</body></html>',
            b'<section class="atlas-page" id="atlas-p002" data-source-id="source-a" '
            b'data-page-number="2"><img src="images/atlas.png" alt="Second synthetic page." />'
            b'</section></body></html>',
        )
        self.__build_epub(atlas=extra_page)
        result = self.__run()
        self.assertIn('atlas_manifest_page_set_mismatch', {item['code'] for item in result['errors']})

    def test_nested_agent_envelope_is_not_misread_as_empty_projection(self) -> None:
        self.__build_epub()
        self.agent_jsonl.write_text(json.dumps({
            'projection_schema': 'rta-agent-current-envelope/1.0',
            'edition': 'synthetic-edition',
            'projection_scope': 'full_current_edition',
            'source_layer': 'synthetic',
            'record': {'record_id': 'paragraph-1', 'record_type': 'course_paragraph'},
        }) + '\n', encoding='utf-8')
        result = self.__run()
        self.assertEqual(result['status'], 'NOT_APPLICABLE_SCHEMA')
        self.assertFalse(result['agent_projection_contract_supported'])
        self.assertIsNone(result['checks']['body_figure_projection'])
        self.assertIsNone(result['checks']['uncertainty_targets_and_counts'])
        self.assertIn('agent_projection_schema_not_supported', {item['code'] for item in result['warnings']})


if __name__ == '__main__':
    unittest.main()
