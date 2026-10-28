from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_reader_editor_candidate.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_candidate(root: Path) -> Path:
    lesson = root / "lesson"
    asr = lesson / "asr"
    asr.mkdir(parents=True)
    segments = [
        {"segment_id": "seg-0001", "source_id": "lesson-01", "ordinal": 1, "start_ms": 0, "end_ms": 100,
         "start_hms": "00:00:00.000", "end_hms": "00:00:00.100", "text": "hello", "speaker_id": None},
        {"segment_id": "seg-0002", "source_id": "lesson-01", "ordinal": 2, "start_ms": 100, "end_ms": 200,
         "start_hms": "00:00:00.100", "end_hms": "00:00:00.200", "text": " tail", "speaker_id": None},
    ]
    frozen = asr / "frozen.jsonl"
    punctuated = asr / "punctuated.jsonl"
    manifest = asr / "manifest.json"
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in segments)
    frozen.write_text(payload, encoding="utf-8")
    punctuated_segments = [
        dict(segments[0], asr_punctuated_text="hello,"),
        dict(segments[1], asr_punctuated_text=" tail."),
    ]
    punctuated_payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in punctuated_segments)
    punctuated.write_text(punctuated_payload, encoding="utf-8")
    manifest.write_text('{"lesson_id":"lesson-01"}\n', encoding="utf-8")
    candidate = {
        "schema_version": "reader-editor/1.0.0",
        "source_layer": {
            "frozen_segments_path": "asr/frozen.jsonl",
            "frozen_segments_sha256": digest(frozen),
            "punctuated_candidate_path": "asr/punctuated.jsonl",
            "punctuated_candidate_sha256": digest(punctuated),
            "source_manifest_path": "asr/manifest.json",
            "source_manifest_sha256": digest(manifest),
        },
        "sections": [{
            "section_id": "S01", "reader_heading": "Test", "source_ordinal_range": [1, 1],
            "record_ids": ["P0001"], "source_segment_ids": ["seg-0001"],
        }],
        "paragraphs": [{
            "record_id": "P0001", "section_id": "S01", "source_segment_ids": ["seg-0001"],
            "source_locator": {"start_ms": 0, "end_ms": 100},
            "original_candidate_text": "hello", "asr_punctuated_candidate_text": "hello,",
            "proofread_text": "Hello!", "reader_text": "Hello! [†](#U001)",
            "diff_from_original": [
                {"op": "replace", "source_char_start": 0, "source_char_end": 1, "proofread_text": "H"},
                {"op": "insert", "source_char_start": 5, "source_char_end": 5, "proofread_text": "!"},
            ],
            "presentation_diff_from_proofread": [
                {"op": "insert", "proofread_char_start": 6, "proofread_char_end": 6, "reader_text": " [†](#U001)"},
            ],
            "unresolved_refs": ["U001"],
        }],
        "non_body_boundary_disposition": [{
            "disposition_id": "NB-POST", "type": "post_class", "source_segment_ids": ["seg-0002"],
            "source_locator": {"start_ms": 100, "end_ms": 200}, "original_candidate_text": " tail",
        }],
        "unresolved_register": [{
            "unresolved_id": "U001", "reader_record_ids": ["P0001"],
            "candidate_spans": ["el"],
            "anchors": [{
                "source_segment_id": "seg-0001", "source_ordinal": 1, "candidate_span": "el",
                "char_start_in_segment": 1, "char_end_in_segment": 3, "record_id": "P0001",
            }],
        }],
        "normalization_register": [{
            "source_ordinal": 1, "source_segment_id": "seg-0001", "source_form": "h",
            "proofread_form": "H", "source_char_start": 0, "source_char_end": 1,
        }],
        "validation": {
            "source_segment_total": 2, "body_unique_source_ids": 1, "non_body_unique_source_ids": 1,
            "coverage_exact_once": True, "record_count": 1, "section_count": 1,
            "unresolved_group_count": 1, "unresolved_anchor_count": 1, "reader_link_count": 1,
            "normalization_count": 1,
        },
    }
    path = lesson / "candidate.json"
    path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class ReaderEditorPreflightTests(unittest.TestCase):
    def run_validator(self, candidate: Path, *, require_markdown: bool = False):
        command = [sys.executable, str(VALIDATOR), str(candidate), "--report", str(candidate.parent / "report.json")]
        if require_markdown:
            command.append("--require-markdown")
        return subprocess.run(
            command,
            capture_output=True, text=True, check=False,
        )

    @staticmethod
    def write_valid_markdown(candidate: Path, *, unresolved_anchor: bool = True, unresolved_link: bool = True) -> Path:
        data = json.loads(candidate.read_text(encoding="utf-8"))
        section = data["sections"][0]
        paragraph = data["paragraphs"][0]
        uid = data["unresolved_register"][0]["unresolved_id"]
        marker = f"[†](#{uid})" if unresolved_link else "†"
        unresolved = f'<a id="{uid}"></a>\nuncertain phrase' if unresolved_anchor else ""
        markdown = (
            f'<a id="{section["section_id"]}"></a>\n'
            f'<a id="{paragraph["record_id"]}"></a>\n'
            f'Hello! {marker}\n{unresolved}\n'
        )
        path = candidate.with_suffix(".md")
        path.write_text(markdown, encoding="utf-8")
        return path

    def test_valid_candidate_passes_both_diff_layers_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_validator(make_candidate(Path(tmp)))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((Path(tmp) / "lesson" / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["validator_sha256"], digest(VALIDATOR))
            self.assertTrue(report["checks"]["original_diff_replay"])
            self.assertTrue(report["checks"]["punctuated_candidate_projection_exact"])
            self.assertTrue(report["checks"]["presentation_diff_replay"])
            self.assertTrue(report["checks"]["reader_body_matches_proofread_after_uncertainty_links"])

    def test_presentation_diff_cannot_rewrite_reader_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            data = json.loads(candidate.read_text(encoding="utf-8"))
            paragraph = data["paragraphs"][0]
            paragraph["reader_text"] = "Hullo! [†](#U001)"
            paragraph["presentation_diff_from_proofread"] = [
                {"op": "replace", "proofread_char_start": 1, "proofread_char_end": 2, "reader_text": "u"},
                {"op": "insert", "proofread_char_start": 6, "proofread_char_end": 6, "reader_text": " [†](#U001)"},
            ]
            candidate.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            result = self.run_validator(candidate)
            report = json.loads((Path(tmp) / "lesson" / "report.json").read_text(encoding="utf-8"))

            self.assertEqual(result.returncode, 1)
            self.assertTrue(report["checks"]["presentation_diff_replay"])
            self.assertFalse(report["checks"]["reader_body_matches_proofread_after_uncertainty_links"])
            self.assertIn("reader_text body differs from proofread after removing uncertainty links", result.stdout)

    def test_companion_markdown_anchor_and_unresolved_link_projection_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            self.write_valid_markdown(candidate)
            result = self.run_validator(candidate, require_markdown=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((Path(tmp) / "lesson" / "report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["checks"]["manuscript_markdown_projection"]["record_anchor_order"])
            self.assertTrue(report["checks"]["manuscript_markdown_projection"]["unresolved_link_targets"])
            self.assertTrue(report["manuscript_sha256"])

    def test_companion_markdown_missing_unresolved_anchor_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            self.write_valid_markdown(candidate, unresolved_anchor=False)
            result = self.run_validator(candidate, require_markdown=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("U001: manuscript anchor occurs 0 times", result.stdout)

    def test_companion_body_change_fails_even_with_identical_anchors_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            path = self.write_valid_markdown(candidate)
            path.write_text(path.read_text(encoding='utf-8').replace('Hello!', 'Do not say hello!'),
                            encoding='utf-8')
            result = self.run_validator(candidate, require_markdown=True)
            report = json.loads((candidate.parent / 'report.json').read_text(encoding='utf-8'))
            checks = report['checks']['manuscript_markdown_projection']
            self.assertEqual(result.returncode, 1)
            self.assertTrue(checks['record_anchor_order'])
            self.assertTrue(checks['unresolved_link_targets'])
            self.assertFalse(checks['record_body_matches_reader_text'])
            self.assertIn('P0001: manuscript body differs', result.stdout)

    def test_companion_extra_body_cannot_hide_behind_expected_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            path = self.write_valid_markdown(candidate)
            path.write_text(path.read_text(encoding='utf-8').replace(
                'Hello!', 'Hello! An unsupported case.'), encoding='utf-8')
            self.assertEqual(self.run_validator(candidate, require_markdown=True).returncode, 1)

    def test_companion_source_disclosure_and_inline_html_are_not_body_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            path = self.write_valid_markdown(candidate)
            path.write_text(path.read_text(encoding='utf-8').replace(
                'Hello!', '<details><summary>Original</summary>Different raw source.</details>\n'
                '<strong>Hello!</strong>'), encoding='utf-8')
            result = self.run_validator(candidate, require_markdown=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unclosed_source_disclosure_cannot_hide_body_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            path = self.write_valid_markdown(candidate)
            path.write_text(path.read_text(encoding='utf-8').replace(
                'Hello!', '<details>Different body.'), encoding='utf-8')
            result = self.run_validator(candidate, require_markdown=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('unclosed source disclosure', result.stdout)

    def test_open_disclosure_is_not_silently_ignored_as_hidden_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            path = self.write_valid_markdown(candidate)
            path.write_text(path.read_text(encoding='utf-8').replace(
                'Hello!', '<details open><summary>Original</summary>Extra visible text.</details>Hello!'),
                encoding='utf-8')
            result = self.run_validator(candidate, require_markdown=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('source disclosure must be closed', result.stdout)

    def test_companion_negation_mutation_is_rejected_and_escaped_text_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            data = json.loads(candidate.read_text(encoding='utf-8'))
            paragraph = data['paragraphs'][0]
            prose = 'Do not close if x < 5 & y > 2.'
            paragraph.update(proofread_text=prose, reader_text=prose + ' [†](#U001)',
                diff_from_original=[{'op': 'replace', 'source_char_start': 0,
                                     'source_char_end': 5, 'proofread_text': prose}],
                presentation_diff_from_proofread=[{'op': 'insert', 'proofread_char_start': len(prose),
                    'proofread_char_end': len(prose), 'reader_text': ' [†](#U001)'}])
            data['normalization_register'] = []
            data['validation']['normalization_count'] = 0
            candidate.write_text(json.dumps(data), encoding='utf-8')
            path = self.write_valid_markdown(candidate)
            markdown = path.read_text(encoding='utf-8').replace(
                'Hello!', 'Do not close\nif x &lt; 5 &amp; y &gt; 2.')
            path.write_text(markdown, encoding='utf-8')
            result = self.run_validator(candidate, require_markdown=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            path.write_text(markdown.replace('Do not close', 'Do close'), encoding='utf-8')
            result = self.run_validator(candidate, require_markdown=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('P0001: manuscript body differs', result.stdout)

    def test_structural_pass_names_semantic_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            result = self.run_validator(candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((candidate.parent / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['kind'], 'structural_preflight')
            self.assertIn('case_and_meaning_retention', report['not_checked'])

    def test_companion_markdown_unresolved_link_count_must_match_reader_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            self.write_valid_markdown(candidate, unresolved_link=False)
            result = self.run_validator(candidate, require_markdown=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("U001: manuscript unresolved-link count 0 does not match reader_text count 1", result.stdout)

    def test_companion_markdown_section_and_record_anchor_order_must_match_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            path = self.write_valid_markdown(candidate)
            markdown = path.read_text(encoding="utf-8")
            section_anchor = '<a id="S01"></a>'
            record_anchor = '<a id="P0001"></a>'
            path.write_text(markdown.replace(f"{section_anchor}\n{record_anchor}", f"{record_anchor}\n{section_anchor}"), encoding="utf-8")

            result = self.run_validator(candidate, require_markdown=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("manuscript section/record anchors do not follow candidate order", result.stdout)

    def test_sections_cannot_reorder_records_away_from_source_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            data = json.loads(candidate.read_text(encoding="utf-8"))
            first = data["paragraphs"][0]
            first["section_id"] = "S02"
            second = {
                "record_id": "P0002", "section_id": "S01", "source_segment_ids": ["seg-0002"],
                "source_locator": {"start_ms": 100, "end_ms": 200},
                "original_candidate_text": " tail", "asr_punctuated_candidate_text": " tail.",
                "proofread_text": " tail.", "reader_text": " tail.",
                "diff_from_original": [
                    {"op": "insert", "source_char_start": 5, "source_char_end": 5, "proofread_text": "."},
                ],
                "presentation_diff_from_proofread": [], "unresolved_refs": [],
            }
            data["paragraphs"].append(second)
            data["non_body_boundary_disposition"] = []
            data["sections"] = [
                {"section_id": "S01", "reader_heading": "Later in source", "source_ordinal_range": [2, 2],
                 "record_ids": ["P0002"], "source_segment_ids": ["seg-0002"]},
                {"section_id": "S02", "reader_heading": "Earlier in source", "source_ordinal_range": [1, 1],
                 "record_ids": ["P0001"], "source_segment_ids": ["seg-0001"]},
            ]
            data["validation"].update({
                "body_unique_source_ids": 2, "non_body_unique_source_ids": 0,
                "coverage_exact_once": True, "record_count": 2, "section_count": 2,
            })
            candidate.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            result = self.run_validator(candidate)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads((candidate.parent / "report.json").read_text(encoding="utf-8"))
            self.assertFalse(report["checks"]["section_record_order"])
            self.assertFalse(report["checks"]["paragraph_section_order"])
            self.assertFalse(report["checks"]["section_source_ranges_ordered"])
            self.assertIn("section record_ids do not preserve paragraph/source order", report["errors"])

    def test_companion_markdown_rejects_duplicate_unresolved_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            path = self.write_valid_markdown(candidate)
            with path.open("a", encoding="utf-8") as file:
                file.write('\n<a id="U001"></a>\n')

            result = self.run_validator(candidate, require_markdown=True)

            self.assertEqual(result.returncode, 1)
            self.assertIn("U001: manuscript anchor occurs 2 times", result.stdout)

    def test_required_companion_markdown_must_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            result = self.run_validator(candidate, require_markdown=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("manuscript Markdown is required but missing", result.stdout)

    def test_unsupported_schema_is_not_reported_as_candidate_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            data = json.loads(candidate.read_text(encoding="utf-8"))
            data["schema_version"] = "sample-course-reader-editor/4.0.0"
            candidate.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            result = self.run_validator(candidate)

            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            report = json.loads((Path(tmp) / "lesson" / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "NOT_APPLICABLE_SCHEMA")
            self.assertEqual(report["schema_version"], "sample-course-reader-editor/4.0.0")
            self.assertIn("reader-editor-v3", report["supported_schema_versions"])

    def test_project_namespace_keeps_the_same_structural_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            data = json.loads(candidate.read_text(encoding='utf-8'))
            data['schema_version'] = 'sample-course-reader-editor/1.0.0'
            candidate.write_text(json.dumps(data), encoding='utf-8')
            result = self.run_validator(candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data['paragraphs'][0]['source_segment_ids'] = ['unknown-source']
            candidate.write_text(json.dumps(data), encoding='utf-8')
            result = self.run_validator(candidate)
            self.assertEqual(result.returncode, 1)
            self.assertIn('unknown source IDs', result.stdout)

    def test_missing_source_segment_fails_exact_once_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            data = json.loads(candidate.read_text(encoding="utf-8"))
            data["non_body_boundary_disposition"][0]["source_segment_ids"] = []
            candidate.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_validator(candidate)
            self.assertEqual(result.returncode, 1)
            self.assertIn("source IDs not covered", result.stdout)

    def test_punctuated_projection_must_match_punctuated_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            data = json.loads(candidate.read_text(encoding="utf-8"))
            data["paragraphs"][0]["asr_punctuated_candidate_text"] = "wrong source projection"
            candidate.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_validator(candidate)
            self.assertEqual(result.returncode, 1)
            self.assertIn("does not reconstruct from punctuated source", result.stdout)

    def test_empty_presentation_diff_cannot_hide_reader_text_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            data = json.loads(candidate.read_text(encoding="utf-8"))
            data["paragraphs"][0]["presentation_diff_from_proofread"] = []
            candidate.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_validator(candidate)
            self.assertEqual(result.returncode, 1)
            self.assertIn("presentation diff is empty", result.stdout)

    def test_duplicate_normalization_and_bad_anchor_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            data = json.loads(candidate.read_text(encoding="utf-8"))
            data["normalization_register"].append(dict(data["normalization_register"][0]))
            data["unresolved_register"][0]["anchors"][0]["candidate_span"] = "zz"
            candidate.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_validator(candidate)
            self.assertEqual(result.returncode, 1)
            self.assertIn("duplicate normalization", result.stdout)
            self.assertIn("anchor text does not match", result.stdout)

    def test_normalization_must_match_its_source_span_not_elsewhere_in_paragraph(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            data = json.loads(candidate.read_text(encoding="utf-8"))
            normalization = data["normalization_register"][0]
            normalization["source_form"] = "e"
            normalization["source_char_start"] = 1
            normalization["source_char_end"] = 2
            candidate.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            result = self.run_validator(candidate)

            self.assertEqual(result.returncode, 1)
            self.assertIn("normalization proofread_form does not match diff-projected source span", result.stdout)

    def test_normalization_allows_adjacent_punctuation_in_the_same_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            data = json.loads(candidate.read_text(encoding="utf-8"))
            paragraph = data["paragraphs"][0]
            paragraph["proofread_text"] = "H!ello!"
            paragraph["reader_text"] = "H!ello! [†](#U001)"
            paragraph["diff_from_original"][0]["proofread_text"] = "H!"
            paragraph["presentation_diff_from_proofread"][0]["proofread_char_start"] = 7
            paragraph["presentation_diff_from_proofread"][0]["proofread_char_end"] = 7
            candidate.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            result = self.run_validator(candidate)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_empty_unresolved_entry_fails_even_when_declared_counts_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            data = json.loads(candidate.read_text(encoding="utf-8"))
            paragraph = data["paragraphs"][0]
            paragraph["reader_text"] = paragraph["proofread_text"]
            paragraph["presentation_diff_from_proofread"] = []
            paragraph.pop("unresolved_refs")
            unresolved = data["unresolved_register"][0]
            unresolved["candidate_spans"] = []
            unresolved["anchors"] = []
            unresolved["reader_record_ids"] = []
            data["validation"]["unresolved_anchor_count"] = 0
            data["validation"]["reader_link_count"] = 0
            candidate.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            result = self.run_validator(candidate)

            self.assertEqual(result.returncode, 1)
            self.assertIn("unresolved entry has no nonblank candidate spans", result.stdout)
            self.assertIn("unresolved entry has no source anchors", result.stdout)
            self.assertIn("unresolved entry has no reader records", result.stdout)

    def test_changed_source_hash_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate = make_candidate(Path(tmp))
            source = candidate.parent / "asr" / "frozen.jsonl"
            source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            result = self.run_validator(candidate)
            self.assertEqual(result.returncode, 1)
            self.assertIn("source hash mismatch", result.stdout)


if __name__ == "__main__":
    unittest.main()
