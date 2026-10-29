"""Additive, synthetic-only RTA trial tests. Python stdlib only."""
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'
MOD = ROOT / 'scripts' / 'rta_trial.py'
spec = importlib.util.spec_from_file_location('rta_trial', MOD)
assert spec and spec.loader
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


def build_fake_epub(path: Path, title: str):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip')
        archive.writestr('META-INF/container.xml', '<container><rootfile full-path="OEBPS/package.opf"/></container>')
        archive.writestr('OEBPS/package.opf',
                         '<package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata>'
                         f'<dc:title>{title}</dc:title></metadata></package>')


class RtaTrialTests(unittest.TestCase):
    def test_normalize_flat_course_and_coverage_and_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / 'normal.jsonl'
            result = lab.normalize(FIXTURES/'synthetic_flat_course.jsonl', dest, 'demo-v02')
            self.assertEqual(result['converted'], 4)
            self.assertEqual(result['skipped_by_reason']['agent_reading_guide'], 1)
            self.assertEqual(result['skipped_by_reason']['book'], 1)
            summary = lab.coverage(dest, FIXTURES/'synthetic_declared_scope.json')
            self.assertEqual(summary['source_total_coverage'], 'UNKNOWN')
            self.assertEqual(summary['declared_scope']['missing_ids'], ['demo-v02:missing-example'])
            self.assertEqual(lab.trace(dest, 'demo-v02:demo-later')['status'], 'TRACED_METADATA_ONLY')
            with self.assertRaises(FileExistsError):
                lab.normalize(FIXTURES/'synthetic_flat_course.jsonl', dest, 'demo-v02')

    def test_untranscribed_atlas_page_keeps_locator_only(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'normal.jsonl'
            source = Path(folder)/'source.jsonl'
            page = {'record_type':'source_page','source_id':'s001',
                    'page_number':7,'page_anchor':'p007','atlas_document':'atlas.xhtml',
                    'source_image_sha256':'a'*64}
            source.write_text(json.dumps(page)+'\n',encoding='utf-8')
            result=lab.normalize(source,target,'demo')
            self.assertEqual(result['converted'],1)
            record=lab.load_units(target)[0]
            self.assertEqual(record['status'],'metadata_only')
            self.assertEqual(record['text'],'')
            self.assertEqual(record['locator']['epub_href'],'atlas.xhtml#p007')

    def test_normalize_envelope(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'envelope.jsonl'
            out = lab.normalize(FIXTURES/'synthetic_envelope.jsonl', target, 'demo-other')
            self.assertEqual(out['converted'], 2)
            self.assertEqual(lab.coverage(target)['by_kind']['course_figure'], 1)
            self.assertIn('sample_time', lab.load_units(target)[1]['locator'])

    def test_claims_conservative(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'normal.jsonl'
            lab.normalize(FIXTURES/'synthetic_flat_course.jsonl', target, 'demo-v02')
            audit = lab.audit_claims(target, FIXTURES/'synthetic_claims.json')
            self.assertEqual(audit['needs_review_count'], 4)
            self.assertIn('explicit_review_ids_required', audit['claims'][0]['reasons'])
            self.assertIn('sampled_frames_do_not_prove_transition', audit['claims'][1]['reasons'])
            self.assertIn('procedure_replay_not_established', audit['claims'][2]['reasons'])
            self.assertIn('evidence_scope_does_not_match_target', audit['claims'][3]['reasons'])

    def test_separate_review_record_is_bound_but_not_truth_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'source.jsonl'
            target = Path(folder)/'normal.jsonl'
            source.write_text(json.dumps({
                'record_type':'paragraph','source_id':'demo:s','paragraph_id':'demo:p1',
                'source_locator':'chapter.xhtml#p1','text':'A synthetic source sentence.'
            })+'\n',encoding='utf-8')
            lab.normalize(source,target,'demo')
            unit=lab.load_units(target)[0]
            review={"id":"review-a","scope":"continuous_transition",
                    "evidence_ids":[unit['id']],
                    "origin_line_sha256":{unit['id']:unit['origin_line_sha256']},
                    "reviewer":"synthetic-reviewer","method":"manual-source-check",
                    "assessment":"supports","limitations":["Does not establish learner outcome."],
                    "time_semantics":"verified_interval"}
            reviews=Path(folder)/'reviews.json'
            reviews.write_text(json.dumps({'reviews':[review]}),encoding='utf-8')
            spec = Path(folder)/'claims.json'
            spec.write_text(json.dumps({'claims':[{'id':'t','type':'transition',
                'evidence_ids':[unit['id']],'review_ids':['review-a']}]}))
            audit = lab.audit_claims(target, spec, reviews)
            self.assertEqual(audit['needs_review_count'],0)
            self.assertEqual(audit['claims'][0]['status'],'REVIEW_BINDING_READY_NOT_TRUTH_VERIFIED')
            self.assertEqual(audit['review_file_sha256'],hashlib.sha256(reviews.read_bytes()).hexdigest())
            self.assertIn('does not inspect source content',audit['warning'])

    def test_stale_review_row_binding_stays_open(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.jsonl';target=Path(folder)/'normal.jsonl'
            source.write_text(json.dumps({'record_type':'paragraph','source_id':'demo:s',
                'paragraph_id':'demo:p1','source_locator':'chapter.xhtml#p1','text':'Before.'})+'\n',encoding='utf-8')
            lab.normalize(source,target,'demo')
            unit=lab.load_units(target)[0]
            review={'id':'review-a','scope':'observed_state','evidence_ids':[unit['id']],
                'origin_line_sha256':{unit['id']:'0'*64},'reviewer':'synthetic-reviewer',
                'method':'visual-check','assessment':'supports','limitations':[]}
            reviews=Path(folder)/'reviews.json';reviews.write_text(json.dumps({'reviews':[review]}),encoding='utf-8')
            claims=Path(folder)/'claims.json';claims.write_text(json.dumps({'claims':[{
                'id':'state-a','type':'observed_state','evidence_ids':[unit['id']],
                'review_ids':['review-a']}]}),encoding='utf-8')
            audit=lab.audit_claims(target,claims,reviews)
            self.assertEqual(audit['needs_review_count'],1)
            self.assertIn('review_not_bound_to_current_input_rows',audit['claims'][0]['reasons'])

    def test_source_mapping_review_must_bind_the_claim_target(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.jsonl';target=Path(folder)/'normal.jsonl'
            source.write_text(json.dumps({'record_type':'body_figure','source_id':'demo:s',
                'figure_id':'demo:figure','source_locator':'chapter.xhtml#figure','caption':'A visible shape.'})+'\n',encoding='utf-8')
            lab.normalize(source,target,'demo')
            unit=lab.load_units(target)[0]
            review={'id':'review-a','scope':'support_of_target','target_id':'other-target',
                'evidence_ids':[unit['id']],'origin_line_sha256':{unit['id']:unit['origin_line_sha256']},
                'reviewer':'synthetic-reviewer','method':'source-review','assessment':'supports','limitations':[]}
            reviews=Path(folder)/'reviews.json';reviews.write_text(json.dumps({'reviews':[review]}),encoding='utf-8')
            claims=Path(folder)/'claims.json';claims.write_text(json.dumps({'claims':[{
                'id':'mapping-a','type':'source_mapping','target_id':'figure-caption',
                'evidence_ids':[unit['id']],'review_ids':['review-a']}]}),encoding='utf-8')
            audit=lab.audit_claims(target,claims,reviews)
            self.assertEqual(audit['needs_review_count'],1)
            self.assertIn('evidence_scope_does_not_match_target',audit['claims'][0]['reasons'])

    def test_projection_version_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            epub = Path(folder)/'fake.epub'
            build_fake_epub(epub,'虚构练习书 1.0.0-rc.2 第2卷')
            report = lab.projection_drift(FIXTURES/'synthetic_flat_course.jsonl', epub, None)
            self.assertEqual(report['status'], 'DRIFT_DETECTED')
            self.assertEqual(report['mismatched_fields'], ['projection_title_version'])
            build_fake_epub(epub,'虚构练习书 1.0.0-rc.3 第2卷')
            report = lab.projection_drift(FIXTURES/'synthetic_flat_course.jsonl', epub, None)
            self.assertEqual(set(report['mismatched_fields']), {'projection_title_version','epub_title_version'})

    def test_duplicate_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            src=Path(folder)/'dupe.jsonl'
            line=(FIXTURES/'synthetic_flat_course.jsonl').read_text('utf-8').splitlines()[1]
            src.write_text(line+'\n'+line+'\n','utf-8')
            with self.assertRaisesRegex(ValueError,'duplicate normalized ID'):
                lab.normalize(src,Path(folder)/'new.jsonl','demo')
            self.assertFalse((Path(folder)/'new.jsonl').exists())

    def test_unreadable_not_assumed_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'normal.jsonl'
            lab.normalize(FIXTURES/'synthetic_flat_course.jsonl', target, 'demo-v02')
            self.assertEqual(lab.trace(target,'absent')['status'],'NOT_FOUND_IN_PROJECTION')

    def test_cli_error_codes(self):
        r = subprocess.run([sys.executable,str(MOD),'audit-claims','--records',
            str(FIXTURES/'synthetic_flat_course.jsonl'),'--claims',
            str(FIXTURES/'synthetic_claims.json')],capture_output=True,text=True)
        self.assertEqual(r.returncode,2)
        self.assertIn('missing normalized field', r.stderr)

    def test_local_doctor_no_network(self):
        self.assertFalse(lab.doctor()['network_or_install_attempted'])


if __name__=='__main__':
    unittest.main()
