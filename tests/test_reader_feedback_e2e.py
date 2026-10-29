"""Synthetic reader-feedback repair: trace the target and bound EPUB changes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'


def load_script(name):
    path = ROOT / 'scripts' / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evidence = load_script('rta_trial.py')
scope = load_script('rta_scope_diff.py')


def write_epub(path: Path, version: str, *, added_emphasis: bool, unexpected: bool = False):
    emphasis = '<ins class="added">new</ins>' if added_emphasis else '<ins>new</ins>'
    css = 'ins { color: #138a36; }' if not added_emphasis else 'ins { color: #138a36; font-weight: 700; }'
    chapter = f'<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="edited-p00001">We learn {emphasis}.</p></body></html>'
    package = (
        '<package xmlns="http://www.idpf.org/2007/opf" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0" unique-identifier="id">'
        f'<metadata><dc:identifier id="id">urn:demo:{version}</dc:identifier>'
        f'<dc:title>Synthetic reading edition {version}</dc:title></metadata></package>'
    )
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        archive.writestr('META-INF/container.xml',
                         '<container><rootfile full-path="OEBPS/package.opf"/></container>')
        archive.writestr('OEBPS/package.opf', package)
        archive.writestr('OEBPS/chapter-001.xhtml', chapter)
        archive.writestr('OEBPS/style.css', css)
        if unexpected:
            archive.writestr('OEBPS/chapter-002.xhtml', '<p>Unrelated content changed.</p>')


class ReaderFeedbackEndToEndTests(unittest.TestCase):
    def test_feedback_binds_edition_traces_target_and_limits_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            before = work / 'before.epub'
            after = work / 'after.epub'
            invalid_after = work / 'invalid-after.epub'
            write_epub(before, '1.0.0-rc.1', added_emphasis=False)
            write_epub(after, '1.0.1-rc.1', added_emphasis=True)
            write_epub(invalid_after, '1.0.1-rc.1', added_emphasis=True, unexpected=True)

            case_file = FIXTURES / 'reader_feedback_cases.synthetic.json'
            case = json.loads(case_file.read_text('utf-8'))['cases'][0]
            case['edition']['epub_sha256'] = hashlib.sha256(before.read_bytes()).hexdigest()
            self.assertEqual(len(case['edition']['epub_sha256']), 64)

            normalized = work / 'source-units.jsonl'
            result = evidence.normalize(FIXTURES/'synthetic_flat_course.jsonl', normalized, 'demo-v1.0.0')
            self.assertGreater(result['converted'], 0)
            traced = evidence.trace(normalized, case['target']['unit_id'])
            self.assertEqual(traced['status'], 'TRACED_METADATA_ONLY')
            self.assertEqual(traced['lineage'][0]['locator']['epub_href'], case['target']['epub_href'])

            claims = work / 'claims.json'
            claims.write_text(json.dumps({'claims':[{
                'id':'state-change-claim','type':'transition',
                'evidence_ids':['demo-v1.0.0:demo-early','demo-v1.0.0:demo-later']
            }]}),encoding='utf-8')
            claim_audit = evidence.audit_claims(normalized, claims)
            self.assertEqual(claim_audit['claims'][0]['status'],'NEEDS_REVIEW')
            self.assertIn('sampled_frames_do_not_prove_transition',claim_audit['claims'][0]['reasons'])

            policy = FIXTURES / 'synthetic_feedback_scope_policy.json'
            accepted = scope.scope_diff(before, after, policy)
            self.assertEqual(accepted['status'], 'SCOPE_PASS')
            self.assertEqual(set(accepted['changed']), {
                'OEBPS/package.opf', 'OEBPS/chapter-001.xhtml', 'OEBPS/style.css'
            })
            self.assertIn('NOT semantic', accepted['warning'])

            rejected = scope.scope_diff(before, invalid_after, policy)
            self.assertEqual(rejected['status'], 'SCOPE_FAIL')
            self.assertEqual(rejected['unexpected']['added'], ['OEBPS/chapter-002.xhtml'])

            stale = evidence.projection_drift(FIXTURES/'synthetic_flat_course.jsonl', after, '1.0.1-rc.1')
            self.assertEqual(stale['status'], 'DRIFT_DETECTED')
            rows = [json.loads(line) for line in (FIXTURES/'synthetic_flat_course.jsonl').read_text('utf-8').splitlines()]
            rows[0]['version'] = '1.0.1-rc.1'
            rows[0]['title'] = 'Synthetic reading edition 1.0.1-rc.1'
            updated_projection = work / 'agent-current.jsonl'
            updated_projection.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
            aligned = evidence.projection_drift(updated_projection, after, '1.0.1-rc.1')
            self.assertEqual(aligned['status'], 'VERSION_CONSISTENT')


if __name__ == '__main__':
    unittest.main()
