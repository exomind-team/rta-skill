'''Exercise optional manifests and scoped review reuse with invented assets.
- 🤖Agent-authored regression cases; no real course material is included.
'''
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'project_state.py'
spec = importlib.util.spec_from_file_location('project_state', MODULE_PATH)
assert spec and spec.loader
project_state = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = project_state
spec.loader.exec_module(project_state)


class ProjectStateTests(unittest.TestCase):
    '''Verify cache assistance without promoting metadata into content acceptance.'''

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name, text in [('source.txt', 'Source case.'), ('chapter.txt', 'Edited case.'),
                           ('review.md', 'A bounded independent review.'), ('style.css', 'p {}')]:
            (self.root / name).write_text(text, encoding='utf-8')
        self.manifest = self.root / 'project.json'
        self.data = {
            'schema_version': 'knowledge-project/1',
            'sources': [{'id': 'raw', 'kind': 'future_source_kind', 'path': 'source.txt'}],
            'artifacts': [{
                'id': 'chapter', 'kind': 'reading_text', 'path': 'chapter.txt',
                'depends_on': ['raw'],
                'checks': [{
                    'kind': 'source_to_text', 'status': 'passed',
                    'scope': 'Synthetic chapter, source-to-text claims only; no audio or figures.',
                    'inputs': {identifier: project_state.digest_file(self.root / name)
                               for identifier, name in [('raw', 'source.txt'), ('chapter', 'chapter.txt')]},
                    'report': {'path': 'review.md',
                               'sha256': project_state.digest_file(self.root / 'review.md')},
                }],
            }, {'id': 'style', 'kind': 'css', 'path': 'style.css'}],
            'current': {'manuscript': 'chapter'},
            'future_extension': {'allowed': True},
        }
        self.save()

    def save(self) -> None:
        self.manifest.write_text(json.dumps(self.data), encoding='utf-8')

    def check(self, *, verify: bool = True) -> dict[str, object]:
        return project_state.inspect_project(
            self.manifest, selected=['chapter'], verify=verify,
        )['assets'][0]['checks'][0]

    def test_missing_optional_manifest_allows_direct_work(self) -> None:
        result = project_state.inspect_project(self.root / 'absent.json')
        self.assertEqual(result['status'], 'NOT_PRESENT')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                         ['chapter.txt', 'project.json', 'review.md', 'source.txt', 'style.css'])

    def test_inspection_does_not_pretend_to_recheck_hashes(self) -> None:
        result = self.check(verify=False)
        self.assertFalse(result['reusable'])
        self.assertEqual(result['binding'], 'not_rechecked')

    def test_unchanged_bindings_reuse_and_unrelated_style_stays_local(self) -> None:
        self.assertTrue(self.check()['reusable'])
        (self.root / 'style.css').write_text('p { color: gray; }', encoding='utf-8')
        self.assertTrue(self.check()['reusable'])

    def test_scoped_acceptance_survives_inspection_without_becoming_a_whole_book_pass(self) -> None:
        check = self.data['artifacts'][0]['checks'][0]
        check.update(kind='glossary', scope='Only the changed term in paragraph one.')
        self.save()
        result = self.check()
        self.assertEqual(result['kind'], 'glossary')
        self.assertEqual(result['scope'], check['scope'])
        self.assertEqual(result['declared_status'], 'passed')
        self.assertTrue(result['reusable'])

    def test_unknown_legacy_scope_can_match_hashes_without_authorizing_reuse(self) -> None:
        del self.data['artifacts'][0]['checks'][0]['scope']
        self.save()
        result = self.check()
        self.assertEqual(result['binding'], 'matched')
        self.assertIsNone(result['scope'])
        self.assertFalse(result['reusable'])
        self.assertIn('scope', result['reuse_limitation'])

    def test_changed_source_invalidates_the_bound_check(self) -> None:
        (self.root / 'source.txt').write_text('Changed condition.', encoding='utf-8')
        result = self.check()
        self.assertEqual(result['binding'], 'stale')
        self.assertEqual(result['changed_asset'], 'raw')

    def test_changed_report_is_not_accepted_as_same_review(self) -> None:
        (self.root / 'review.md').write_text('Different report.', encoding='utf-8')
        self.assertEqual(self.check()['binding'], 'stale_report')

    def test_missing_dependency_binding_cannot_be_reused(self) -> None:
        del self.data['artifacts'][0]['checks'][0]['inputs']['raw']
        self.save()
        self.assertEqual(self.check()['binding'], 'incomplete_dependencies')

    def test_missing_source_is_not_hash_verified(self) -> None:
        (self.root / 'source.txt').unlink()
        self.assertEqual(self.check()['binding'], 'missing_file')

    def test_unaccepted_result_is_not_promoted(self) -> None:
        self.data['artifacts'][0]['checks'][0]['status'] = 'pending'
        self.save()
        self.assertEqual(self.check()['binding'], 'not_accepted')

    def test_hashing_requires_deliberately_selected_scope(self) -> None:
        with self.assertRaisesRegex(ValueError, '--artifact'):
            project_state.inspect_project(self.manifest, verify=True)

    def test_cyclic_and_unknown_dependencies_are_local_format_errors(self) -> None:
        self.data['artifacts'][0]['depends_on'] = ['chapter']
        self.save()
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            self.check()
        self.data['artifacts'][0]['depends_on'] = ['unknown']
        self.save()
        with self.assertRaisesRegex(ValueError, 'unknown dependencies'):
            self.check()

    def test_unknown_transitive_dependency_is_reported_before_traversal(self) -> None:
        self.data['sources'][0]['depends_on'] = ['chapter']
        self.data['artifacts'][0]['depends_on'] = ['unknown']
        self.save()
        with self.assertRaisesRegex(ValueError, 'unknown dependencies'):
            self.check()


if __name__ == '__main__':
    unittest.main()
