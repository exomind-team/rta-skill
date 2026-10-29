"""Synthetic reader-feedback repair: trace the target and bound EPUB changes."""
import hashlib
import html
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
oral_editing = load_script('audit_oral_editing.py')
package_validator = load_script('validate_epub_projection.py')


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


SYNTHETIC_BADGE = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60" viewBox="0 0 120 60">'
    b'<rect x="2" y="2" width="116" height="56" rx="10" fill="#dcecff"/>'
    b'<text x="60" y="40" text-anchor="middle" font-size="32">3</text></svg>'
)


def figure_projection(version: str, alt: str, image_bytes: bytes) -> list[dict]:
    return [
        {'record_type':'book','title':f'Synthetic book {version}','version':version},
        {'record_type':'body_figure','figure_id':'figure-01','chapter_href':'chapter-001.xhtml',
         'source_id':'demo-source','source_unit_id':'figure-unit-01','anchor_id':'edited-p00001',
         'images':[{'image_href':'images/badge.svg','image_sha256':hashlib.sha256(image_bytes).hexdigest(),
                    'alt_text':alt}]}
    ]


def write_figure_epub(path: Path, version: str, alt: str, image_bytes: bytes) -> None:
    safe_alt=html.escape(alt,quote=True)
    chapter=(f'<html xmlns="http://www.w3.org/1999/xhtml"><body>'
             '<p id="edited-p00001">Synthetic source example.</p>'
             '<figure id="figure-01" data-source-id="demo-source" data-source-unit-id="figure-unit-01">'
             f'<img src="images/badge.svg" alt="{safe_alt}" /></figure></body></html>')
    package=(
        '<package xmlns="http://www.idpf.org/2007/opf" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0" unique-identifier="bookid">'
        f'<metadata><dc:identifier id="bookid">urn:demo:{version}</dc:identifier>'
        f'<dc:title>Synthetic book {version}</dc:title></metadata></package>'
    )
    container=('<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
               '<rootfiles><rootfile full-path="OEBPS/package.opf" '
               'media-type="application/oebps-package+xml"/></rootfiles></container>')
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('mimetype','application/epub+zip',compress_type=zipfile.ZIP_STORED)
        archive.writestr('META-INF/container.xml',container)
        archive.writestr('OEBPS/package.opf',package)
        archive.writestr('OEBPS/chapter-001.xhtml',chapter)
        archive.writestr('OEBPS/images/badge.svg',image_bytes)


class ReaderFeedbackEndToEndTests(unittest.TestCase):
    def test_editorial_feedback_is_compared_and_generalized_without_erasing_emphasis(self):
        case_file = FIXTURES / 'reader_feedback_cases.synthetic.json'
        case = next(item for item in json.loads(case_file.read_text('utf-8'))['cases']
                    if item['case_id'] == 'feedback-editorial-fidelity-02')
        self.assertEqual(case['category'], 'editorial-quality')
        record = {
            'record_id':'demo-p0001',
            'source_segment_ids':['demo-seg-1'],
            'original_candidate_text':'呃呃我我觉得这个方法非常非常重要。',
            'asr_punctuated_candidate_text':'呃呃，我我觉得这个方法非常非常重要。',
            'proofread_text':'呃呃，我我觉得这个方法非常非常重要。'
        }
        before = oral_editing.audit_record(record)
        categories_before = {item['category'] for item in before}
        self.assertIn('filler_run', categories_before)
        self.assertIn('adjacent_repetition', categories_before)

        # Apply the generalized example: remove disfluency/stutter but keep emphasis.
        revised = dict(record, proofread_text='我觉得这个方法非常非常重要。')
        after = oral_editing.audit_record(revised)
        categories_after = {item['category'] for item in after}
        self.assertNotIn('filler_run', categories_after)
        self.assertNotIn('adjacent_repetition', categories_after)
        self.assertIn('非常非常', revised['proofread_text'])

    def test_numeric_image_meaning_feedback_reaches_source_and_package_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder)
            evidence_root=work/'evidence';evidence_root.mkdir()
            source_frame=evidence_root/'source-frame.svg'
            source_frame.write_bytes(SYNTHETIC_BADGE)
            review_note=evidence_root/'visual-review.txt'
            review_note.write_text(
                'Synthetic image displays a badge with numeral 3; it contains no label explaining what 3 counts.',
                encoding='utf-8')

            source_rows=[
                {'record_type':'body_figure','source_id':'demo-source','figure_id':'figure-01',
                 'source_locator':'chapter-001.xhtml#figure-01','caption':'Three tasks are pending.'},
                {'record_type':'source_page','source_id':'demo-source','page_number':1,
                 'page_anchor':'page-001','atlas_document':'source-atlas.xhtml',
                 'description':'A synthetic screenshot visibly shows the numeral 3.',
                 'source_image_sha256':hashlib.sha256(SYNTHETIC_BADGE).hexdigest()}
            ]
            source_projection=work/'source-records.jsonl'
            source_projection.write_text(
                ''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in source_rows),encoding='utf-8')
            normalized=work/'normalized.jsonl'
            evidence.normalize(source_projection,normalized,'demo-v1.0.0')
            units={row['source_unit_id']:row for row in evidence.load_units(normalized)}
            page_unit=units['page-001']

            before=work/'before.epub';after=work/'after.epub'
            old_alt='Three tasks are pending.'
            new_alt='A badge displays the numeral 3.'
            write_figure_epub(before,'1.0.0-rc.1',old_alt,SYNTHETIC_BADGE)
            write_figure_epub(after,'1.0.1-rc.1',new_alt,SYNTHETIC_BADGE)

            feedback=next(item for item in json.loads(
                (FIXTURES/'reader_feedback_cases.synthetic.json').read_text('utf-8'))['cases']
                if item['case_id']=='feedback-image-number-meaning-05')
            feedback['edition']['epub_sha256']=hashlib.sha256(before.read_bytes()).hexdigest()
            self.assertEqual(feedback['edition']['epub_sha256'],hashlib.sha256(before.read_bytes()).hexdigest())
            self.assertEqual(feedback['edition']['version'],'1.0.0-rc.1')
            self.assertEqual(feedback['target']['unit_id'],'demo-v1.0.0:figure-01')
            self.assertEqual(feedback['target']['epub_href'],'chapter-001.xhtml#figure-01')
            trace=evidence.trace(normalized,feedback['target']['unit_id'])
            self.assertEqual(trace['status'],'TRACED_METADATA_ONLY')

            def review(assessment):
                return {'reviews':[{'id':'review-visible-number','scope':'support_of_target',
                    'target_id':'figure-01','evidence_ids':[page_unit['id']],
                    'origin_line_sha256':{page_unit['id']:page_unit['origin_line_sha256']},
                    'evidence_artifacts':[
                        {'path':'source-frame.svg','sha256':hashlib.sha256(source_frame.read_bytes()).hexdigest()},
                        {'path':'visual-review.txt','sha256':hashlib.sha256(review_note.read_bytes()).hexdigest()}],
                    'reviewer':'synthetic-reviewer','method':'compare image and description',
                    'assessment':assessment,
                    'limitations':['A still image cannot establish what the badge counts.']}]}

            claims=work/'claims.json'
            claims.write_text(json.dumps({'claims':[{'id':'figure-alt-claim','type':'source_mapping',
                'claim_text':'Three tasks are pending.','target_id':'figure-01',
                'evidence_ids':[page_unit['id']],'review_ids':['review-visible-number']}]}),encoding='utf-8')
            reviews=work/'reviews.json';reviews.write_text(json.dumps(review('contradicts')),encoding='utf-8')
            before_audit=evidence.audit_claims(normalized,claims,reviews,evidence_root)
            self.assertEqual(before_audit['claims'][0]['status'],'NEEDS_REVIEW')
            self.assertIn('review_does_not_support_claim',before_audit['claims'][0]['reasons'])
            self.assertEqual(before_audit['evidence_artifacts_checked'],2)

            atlas_manifest=work/'empty-atlas.jsonl';atlas_manifest.write_text('',encoding='utf-8')
            old_agent=work/'old-agent.jsonl';new_agent=work/'new-agent.jsonl'
            old_agent.write_text(''.join(json.dumps(row)+'\n' for row in figure_projection('1.0.0-rc.1',old_alt,SYNTHETIC_BADGE)),encoding='utf-8')
            new_agent.write_text(''.join(json.dumps(row)+'\n' for row in figure_projection('1.0.1-rc.1',new_alt,SYNTHETIC_BADGE)),encoding='utf-8')
            old_package_check=package_validator.validate_epub_projection(before,old_agent,atlas_manifest,[])
            new_package_check=package_validator.validate_epub_projection(after,new_agent,atlas_manifest,[])
            self.assertEqual(old_package_check['status'],'PASS')
            self.assertEqual(new_package_check['status'],'PASS')
            self.assertTrue(new_package_check['checks']['body_figure_projection'])

            claims.write_text(json.dumps({'claims':[{'id':'figure-alt-claim','type':'source_mapping',
                'claim_text':new_alt,'target_id':'figure-01','evidence_ids':[page_unit['id']],
                'review_ids':['review-visible-number']}]}),encoding='utf-8')
            reviews.write_text(json.dumps(review('supports')),encoding='utf-8')
            corrected_audit=evidence.audit_claims(normalized,claims,reviews,evidence_root)
            self.assertEqual(corrected_audit['claims'][0]['status'],'REVIEW_BINDING_READY_NOT_TRUTH_VERIFIED')
            self.assertEqual(corrected_audit['evidence_artifacts_checked'],2)

            scope_result=scope.scope_diff(before,after,FIXTURES/'synthetic_feedback_scope_policy.json')
            self.assertEqual(scope_result['status'],'SCOPE_PASS')
            self.assertEqual(scope_result['changed'],['OEBPS/chapter-001.xhtml','OEBPS/package.opf'])
            self.assertEqual(evidence.projection_drift(new_agent,after,'1.0.1-rc.1')['status'],'VERSION_CONSISTENT')

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
