from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "audit_oral_editing.py"
spec = importlib.util.spec_from_file_location("audit_oral_editing", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class AuditOralEditingTests(unittest.TestCase):
    def test_flags_punctuation_only_copy_with_filler_and_stutter(self):
        record = {
            "record_id": "SYNTH-P0001",
            "source_segment_ids": ["synthetic-seg-1"],
            "source_locator": {"start_hms": "00:00:01"},
            "original_candidate_text": "嗯嗯我我选择蓝色",
            "asr_punctuated_candidate_text": "嗯嗯，我我选择蓝色。",
            "proofread_text": "嗯嗯，我我选择蓝色。",
        }
        findings = mod.audit_record(record)
        categories = {item["category"] for item in findings}
        self.assertIn("punctuation_or_spacing_only_vs_asr", categories)
        self.assertIn("punctuation_or_spacing_only_vs_source", categories)
        self.assertIn("filler_run", categories)
        self.assertIn("adjacent_repetition", categories)
        self.assertTrue(all(item["record_id"] == "SYNTH-P0001" for item in findings))
        self.assertTrue(all(item["source_segment_ids"] == ["synthetic-seg-1"] for item in findings))

    def test_reports_unpunctuated_filler_and_partial_repetition(self):
        record = {"record_id": "SYNTH-P0002", "proofread_text": "呃因因为他在说这这个问题啊。"}
        findings = mod.audit_record(record)
        matches = {(item["category"], item["matched_text"]) for item in findings}
        self.assertIn(("partial_word_repetition", "因因为"), matches)
        self.assertIn(("partial_word_repetition", "这这个"), matches)
        self.assertIn(("filler_token", "呃"), matches)
        self.assertNotIn(("terminal_particle_a", "啊"), matches)

    def test_does_not_flag_emphatic_lexical_reduplication(self):
        record = {"record_id": "SYNTH-P0003", "proofread_text": "这个方法非常非常重要。"}
        findings = mod.audit_record(record)
        self.assertNotIn("adjacent_repetition", {item["category"] for item in findings})
        self.assertNotIn("partial_word_repetition", {item["category"] for item in findings})

    def test_cli_strict_exit_stays_open_while_findings_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic.json"
            output = root / "audit.json"
            source.write_text(json.dumps({"paragraphs": [{"record_id": "SYNTH-P1",
                "asr_punctuated_candidate_text": "呃呃。", "proofread_text": "呃呃。"}]}), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--input", str(source),
                 "--output-json", str(output), "--strict"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 2)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "needs_review")
            decisions = root / "decisions.json"
            decisions.write_text(json.dumps({"decisions": [
                {"finding_id": finding["finding_id"], "decision": "keep",
                 "context_sha256": finding['context_sha256'],
                 "reason": "Synthetic test fixture: retained to verify adjudication."}
                for finding in payload["files"][0]["findings"]
            ]}), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--input", str(source),
                 "--output-json", str(output), "--decisions", str(decisions), "--strict"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "reviewed")
            self.assertEqual(payload["unresolved_finding_count"], 0)

    def test_context_changes_invalidate_keep_without_changing_match_identity(self):
        record = {'record_id': 'P1', 'original_candidate_text': '嗯我同意',
                  'proofread_text': '嗯，我同意。'}
        first = mod.audit_record(record)[0]
        changed = dict(record, proofread_text='嗯，我不同意。')
        second = mod.audit_record(changed)[0]
        self.assertEqual(first['finding_id'], second['finding_id'])
        self.assertNotEqual(first['context_sha256'], second['context_sha256'])
        source_changed = mod.audit_record(dict(record, original_candidate_text='嗯我不同意'))[0]
        self.assertNotEqual(first['context_sha256'], source_changed['context_sha256'])

    def test_immediate_neighbor_and_lesson_identity_are_review_dependencies(self):
        record = {'record_id': 'P1', 'proofread_text': '嗯。'}
        first = mod.audit_record(record, namespace='lesson-a', neighbors=[{'proofread_text': 'Yes.'}])[0]
        second = mod.audit_record(record, namespace='lesson-a', neighbors=[{'proofread_text': 'No.'}])[0]
        other_lesson = mod.audit_record(record, namespace='lesson-b', neighbors=[{'proofread_text': 'Yes.'}])[0]
        self.assertNotEqual(first['context_sha256'], second['context_sha256'])
        self.assertNotEqual(first['context_sha256'], other_lesson['context_sha256'])

    def test_clean_unchanged_prose_needs_no_keep_paperwork(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / 'input.json', root / 'report.json'
            source.write_text(json.dumps({'paragraphs': [{'record_id': 'P1',
                'original_candidate_text': '请先保存文件', 'asr_punctuated_candidate_text': '请先保存文件。',
                'proofread_text': '请先保存文件。'}]}, ensure_ascii=False), encoding='utf-8')
            result = subprocess.run([sys.executable, str(SCRIPT), '--input', str(source),
                '--output-json', str(output), '--strict'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(output.read_text(encoding='utf-8'))
            self.assertGreater(payload['advisory_finding_count'], 0)
            self.assertEqual(payload['unresolved_finding_count'], 0)
            self.assertEqual(payload['status'], 'advisory_only')

    def test_legacy_unbound_keep_does_not_close_residue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, decisions = root / 'input.json', root / 'audit.json', root / 'decisions.json'
            source.write_text(json.dumps({'paragraphs': [{'record_id': 'P1', 'proofread_text': '呃呃。'}]}),
                              encoding='utf-8')
            finding = mod.audit_file(source)['findings'][0]
            decisions.write_text(json.dumps({'decisions': [{'finding_id': finding['finding_id'],
                'decision': 'keep', 'reason': 'Legacy context unknown.'}]}), encoding='utf-8')
            result = subprocess.run([sys.executable, str(SCRIPT), '--input', str(source),
                '--output-json', str(output), '--decisions', str(decisions), '--strict'],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            payload = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(payload['files'][0]['findings'][0]['decision_binding'], 'missing_or_stale')

    def test_bound_keep_reopens_after_wording_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, decisions = root / 'input.json', root / 'audit.json', root / 'keep.json'
            data = {'lesson_id': 'synthetic-lesson', 'paragraphs': [
                {'record_id': 'P1', 'proofread_text': '嗯，我同意。'}]}
            source.write_text(json.dumps(data), encoding='utf-8')
            finding = mod.audit_file(source)['findings'][0]
            decisions.write_text(json.dumps({'decisions': [{'finding_id': finding['finding_id'],
                'context_sha256': finding['context_sha256'], 'decision': 'keep',
                'reason': 'Synthetic affirmative response.'}]}), encoding='utf-8')
            command = [sys.executable, str(SCRIPT), '--input', str(source), '--output-json', str(output),
                       '--decisions', str(decisions), '--strict']
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            data['paragraphs'][0]['proofread_text'] = '嗯，我不同意。'
            source.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)

    def test_candidate_rename_and_unrelated_paragraph_leave_local_binding_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / 'v1.json', root / 'v2.json'
            data = {'lesson_id': 'synthetic-lesson', 'paragraphs': [
                {'record_id': 'P1', 'proofread_text': '嗯。'},
                {'record_id': 'P2', 'proofread_text': 'Context.'},
                {'record_id': 'P3', 'proofread_text': 'Unrelated.'}]}
            first.write_text(json.dumps(data), encoding='utf-8')
            before = mod.audit_file(first)['findings'][0]['context_sha256']
            data['paragraphs'][2]['proofread_text'] = 'Unrelated change.'
            second.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(before, mod.audit_file(second)['findings'][0]['context_sha256'])


if __name__ == "__main__":
    unittest.main()
