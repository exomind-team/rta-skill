'''Exercise source-linked literal retrieval and safe cache publication.
- 🤖All text and assets in these tests are synthetic.
'''
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'evidence_index.py'
spec = importlib.util.spec_from_file_location('evidence_index', MODULE_PATH)
assert spec and spec.loader
evidence_index = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence_index)


class EvidenceIndexTests(unittest.TestCase):
    '''Check retrieval boundaries independently of source semantics.'''

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.asset = self.root / 'frame.png'
        self.asset.write_bytes(b'synthetic asset bytes')
        self.records = self.root / 'units.jsonl'
        self.index = self.root / 'cache.sqlite'
        self.rows = [{
            'id': 'frame-1', 'source_id': 'lesson-a', 'kind': 'future_figure_kind',
            'locator': {'page': 3, 'sample_time': None, 'time_status': 'unknown'},
            'text': '保存后，结果显示在列表中。', 'text_origin': 'ocr_candidate',
            'path': 'frame.png', 'sha256': hashlib.sha256(self.asset.read_bytes()).hexdigest(),
            'status': 'candidate', 'extra_relationship': {'derived_from': 'raw-1'},
        }, {
            'id': 'held-1', 'source_id': 'lesson-a', 'kind': 'frame',
            'locator': {'sample_time': 12, 'time_status': 'sample_candidate'},
            'text': '保存后的结果。', 'status': 'private_hold',
        }, {
            'id': 'text-1', 'source_id': 'article-b', 'kind': 'paragraph',
            'locator': {'paragraph': 'p-1'}, 'text': '保存记录的方式。', 'status': 'accepted',
        }]

    def build(self) -> dict[str, object]:
        self.records.write_text(
            '\n'.join(json.dumps(row, ensure_ascii=False) for row in self.rows), encoding='utf-8',
        )
        return evidence_index.build_index(self.records, self.index)

    def test_chinese_query_preserves_locator_origin_and_extra_fields(self) -> None:
        self.build()
        result = evidence_index.search_index(self.index, query='保存 结果')
        self.assertEqual(result['total_matches'], 1)
        row = result['matches'][0]
        self.assertEqual(row['id'], 'frame-1')
        self.assertEqual(row['locator']['time_status'], 'unknown')
        self.assertEqual(row['text_origin'], 'ocr_candidate')
        self.assertEqual(row['extra_relationship'], {'derived_from': 'raw-1'})
        self.assertEqual(row['status'], 'candidate')
        self.assertEqual(row['asset_integrity'], 'available_not_rechecked')

    def test_holds_require_explicit_review_query(self) -> None:
        self.build()
        normal = evidence_index.search_index(self.index, query='结果')
        expanded = evidence_index.search_index(self.index, query='结果', include_held=True)
        self.assertEqual(normal['total_matches'], 1)
        self.assertEqual(expanded['total_matches'], 2)
        self.assertEqual(next(r for r in expanded['matches'] if r['id'] == 'held-1')['status'],
                         'private_hold')

    def test_verified_changed_and_missing_asset_do_not_gain_acceptance(self) -> None:
        self.build()
        def row() -> dict[str, object]:
            return evidence_index.search_index(self.index, query='结果', verify=True)['matches'][0]
        self.assertEqual(row()['asset_integrity'], 'matched')
        self.asset.write_bytes(b'changed')
        self.assertEqual(row()['asset_integrity'], 'stale')
        self.assertEqual(row()['status'], 'candidate')
        self.asset.unlink()
        self.assertEqual(row()['asset_integrity'], 'missing')

    def test_duplicate_input_fails_without_publishing_or_leaking_stage(self) -> None:
        self.rows.append(dict(self.rows[0]))
        with self.assertRaisesRegex(ValueError, 'duplicate id'):
            self.build()
        self.assertFalse(self.index.exists())
        self.assertEqual(list(self.root.glob('.cache.sqlite.*')), [])

    def test_existing_index_is_never_overwritten(self) -> None:
        self.build()
        original = self.index.read_bytes()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(original, self.index.read_bytes())

    def test_concurrent_writer_is_preserved_and_stage_is_removed(self) -> None:
        real_link = os.link

        def concurrent_link(source: Path, destination: Path) -> None:
            destination.write_bytes(b'another writer owns this output')
            real_link(source, destination)

        with patch.object(evidence_index.os, 'link', side_effect=concurrent_link):
            with self.assertRaises(FileExistsError):
                self.build()
        self.assertEqual(self.index.read_bytes(), b'another writer owns this output')
        self.assertEqual(list(self.root.glob('.cache.sqlite.*')), [])

    def test_digest_binds_exact_consumed_input_including_bom_and_blank_lines(self) -> None:
        raw = ('\ufeff' + json.dumps(self.rows[0], ensure_ascii=False) + '\r\n\r\n').encode('utf-8')
        self.records.write_bytes(raw)
        result = evidence_index.build_index(self.records, self.index)
        self.assertEqual(result['records_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['records'], 1)

    def test_missing_index_does_not_create_files(self) -> None:
        result = evidence_index.search_index(self.index, query='保存')
        self.assertEqual(result['status'], 'NOT_PRESENT')
        self.assertFalse(self.index.exists())

    def test_filters_and_limit_keep_results_bounded(self) -> None:
        self.build()
        result = evidence_index.search_index(self.index, query='保存', source_id='article-b', limit=1)
        self.assertEqual([r['id'] for r in result['matches']], ['text-1'])
        with self.assertRaises(ValueError):
            evidence_index.search_index(self.index, query='保存', limit=0)

    def test_large_match_set_returns_ranked_top_k_and_total_count(self) -> None:
        self.rows = [{
            'id': f'item-{number:04d}', 'source_id': 'large-source', 'kind': 'paragraph',
            'locator': {'paragraph': number}, 'text': ('needle ' * (number % 7 + 1)).strip(),
        } for number in range(700)]
        self.build()

        result = evidence_index.search_index(self.index, query='needle', limit=3)
        expected = sorted(
            self.rows,
            key=lambda row: (-row['text'].count('needle'), row['id']),
        )[:3]

        self.assertEqual(result['total_matches'], len(self.rows))
        self.assertEqual([row['id'] for row in result['matches']], [row['id'] for row in expected])
        self.assertEqual(
            [row['literal_match']['occurrences'] for row in result['matches']],
            [row['text'].count('needle') for row in expected],
        )

    def test_corrupt_or_unsupported_index_is_not_an_empty_success(self) -> None:
        self.index.write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):
            evidence_index.search_index(self.index, query='保存')

    def test_invalid_locator_fails_without_publishing(self) -> None:
        self.rows[0]['locator'] = {}
        with self.assertRaisesRegex(ValueError, 'locator'):
            self.build()
        self.assertFalse(self.index.exists())


if __name__ == '__main__':
    unittest.main()
