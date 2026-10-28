#!/usr/bin/env python3
"""Preflight structure for a reader-editor JSON before independent semantic review.

This verifies source identity/coverage/order, section-to-record order, two-layer
diff replay, anchors, links, normalization records, and declared counts. It does
not verify acoustic accuracy, meaning, or editorial completeness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

SUPPORTED_SCHEMA_VERSIONS = frozenset({
    "reader-editor/1.0.0",
    "reader-editor-v2",
    "reader-editor-v3",
})

READER_UNRESOLVED_LINK_PATTERN: re.Pattern[str] = re.compile(
    r"\s*\[†\]\(#([^\s)]+)(?:\s+[^)]*)?\)"
)
'''读者层疑点入口的Markdown形式'''


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def __supported_schema(version: object) -> bool:
    '''Recognize the reader-editor contract with an optional project namespace.
    - 📌Namespaced versions still undergo every source/diff/anchor check below.
    - 🤖Preserve existing project inputs without publishing private project names.
    '''
    if not isinstance(version, str):
        return False
    match = re.fullmatch(r'(?:[a-z0-9]+-)*(reader-editor(?:/[0-9.]+|-v[0-9]+))', version)
    return bool(match and match.group(1) in SUPPORTED_SCHEMA_VERSIONS)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def refs_of(paragraph: dict) -> list[str]:
    refs = paragraph.get("unresolved_refs", []) or []
    return [x if isinstance(x, str) else x.get("unresolved_id", x.get("id", "")) for x in refs]


def replay(base: str, ops: list[dict], start_key: str, end_key: str, insert_key: str, label: str) -> str:
    pieces = []
    cursor = 0
    for index, op in enumerate(ops):
        start, end = op.get(start_key), op.get(end_key)
        if not isinstance(start, int) or not isinstance(end, int):
            raise ValueError(f"{label}[{index}] lacks integer edit offsets")
        if start < cursor or end < start or end > len(base):
            raise ValueError(f"{label}[{index}] has overlapping/out-of-bounds offsets {start}:{end}")
        kind = op.get("op")
        if kind not in {"insert", "delete", "replace"}:
            raise ValueError(f"{label}[{index}] has unknown op {kind!r}")
        if kind == "insert" and start != end:
            raise ValueError(f"{label}[{index}] insert must have an empty source span")
        if kind in {"delete", "replace"} and start == end:
            raise ValueError(f"{label}[{index}] {kind} must consume source text")
        pieces.append(base[cursor:start])
        replacement = op.get(insert_key, "")
        if not isinstance(replacement, str):
            raise ValueError(f"{label}[{index}] replacement must be text")
        if kind == "delete" and replacement:
            raise ValueError(f"{label}[{index}] delete must not insert text")
        pieces.append(replacement)
        cursor = end
    pieces.append(base[cursor:])
    return "".join(pieces)


def project_source_span(base: str, ops: list[dict], span_start: int, span_end: int) -> list[str]:
    if span_start < 0 or span_end <= span_start or span_end > len(base):
        raise ValueError(f"invalid source span {span_start}:{span_end}")

    pieces: list[str] = []
    boundary_insertions: list[str] = []
    cursor = span_start
    for op in ops:
        start, end = op.get("source_char_start"), op.get("source_char_end")
        replacement = op.get("proofread_text", "")
        if not isinstance(start, int) or not isinstance(end, int) or not isinstance(replacement, str):
            raise ValueError("diff operation has invalid offsets or replacement text")
        if end < span_start or (end == span_start and start < span_start):
            continue
        if start > span_end:
            break
        if start < span_start < end or start < span_end < end:
            raise ValueError("diff operation crosses the normalization span boundary")
        if start == end:
            if span_start <= start < span_end:
                if start > cursor:
                    pieces.append(base[cursor:start])
                    cursor = start
                pieces.append(replacement)
            elif start == span_end:
                boundary_insertions.append(replacement)
            continue
        if start >= span_end:
            break
        if start < cursor:
            raise ValueError("diff operations overlap inside the normalization span")
        if start > cursor:
            pieces.append(base[cursor:start])
        pieces.append(replacement)
        cursor = end

    if cursor < span_end:
        pieces.append(base[cursor:span_end])
    projected = "".join(pieces)
    candidates = [projected]
    for insertion in boundary_insertions:
        candidates.append(candidates[-1] + insertion)
    return candidates


def normalization_form_matches(projected: str, expected: str) -> bool:
    start, end = 0, len(projected)
    while start < end and (projected[start].isspace() or unicodedata.category(projected[start]).startswith("P")):
        start += 1
    while end > start and (projected[end - 1].isspace() or unicodedata.category(projected[end - 1]).startswith("P")):
        end -= 1
    return projected[start:end] == expected


def markdown_link_targets(markdown: str) -> list[str]:
    targets = re.findall(r"\]\(\s*#([^\s)]+)(?:\s+[^)]*)?\)", markdown)
    targets.extend(re.findall(r"\bhref\s*=\s*['\"]\s*#([^'\"]+)['\"]", markdown, re.IGNORECASE))
    return targets


def reader_body_without_uncertainty_links(reader_text: str) -> str:
    '''去除读者层疑点入口，返回正文投影
    - 🎯确保reader层只增加入口，不改写proofread正文
    - This implementation still requires independent review.
    '''
    return READER_UNRESOLVED_LINK_PATTERN.sub('', reader_text)


class __ManuscriptBody(HTMLParser):
    '''Extract a record's visible prose, excluding its folded source.
    - 📌This is an anchored Markdown contract, not a general Markdown renderer.
    - 🤖Agent-authored; inline Markdown remains literal on both sides.
    '''

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.details_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'details':
            if any(name == 'open' for name, _ in attrs):
                raise ValueError('source disclosure must be closed in manuscript projection')
            self.details_depth += 1
        elif not self.details_depth and tag in {'p', 'br', 'div'}:
            self.parts.append('\n')

    def handle_endtag(self, tag: str) -> None:
        if tag == 'details':
            self.details_depth = max(0, self.details_depth - 1)
        elif not self.details_depth and tag in {'p', 'div'}:
            self.parts.append('\n')

    def handle_data(self, data: str) -> None:
        if not self.details_depth:
            self.parts.append(data)


def __manuscript_body(fragment: str) -> str:
    '''Normalize HTML presentation and whitespace without discarding words or punctuation.
    - 📌Unsupported projections must use their own render-layer check, never a substring search.
    - 🤖An unclosed source disclosure is a failed projection, not hidden trailing prose.
    '''
    parser = __ManuscriptBody()
    parser.feed(fragment)
    parser.close()
    if parser.details_depth:
        raise ValueError('unclosed source disclosure in manuscript record')
    return ' '.join(''.join(parser.parts).split())


def validate_markdown_projection(
    path: Path,
    candidate: dict,
    *,
    required: bool,
) -> tuple[dict[str, object], list[str], str | None]:
    if not path.is_file():
        errors = [f"manuscript Markdown is required but missing: {path}"] if required else []
        return {
            "checked": False,
            "record_anchor_coverage": False,
            "record_anchor_order": False,
            "section_anchor_order": False,
            "paragraph_record_anchor_order": False,
            "unresolved_anchor_coverage": False,
            "unresolved_link_targets": False,
            "record_body_matches_reader_text": False,
        }, errors, None

    try:
        markdown = path.read_text(encoding="utf-8-sig")
    except Exception as e:
        return {"checked": False}, [f"cannot read manuscript Markdown: {e}"], None

    errors: list[str] = []
    id_matches = list(re.finditer(r"\bid\s*=\s*(['\"])([^'\"]+)\1", markdown, re.IGNORECASE))
    id_counts = Counter(match.group(2) for match in id_matches)
    sections = candidate.get("sections", [])
    paragraphs = candidate.get("paragraphs", [])
    expected_order: list[str] = []
    expected_section_order: list[str] = []
    for section in sections:
        section_id = section.get("section_id")
        if isinstance(section_id, str) and section_id:
            expected_section_order.append(section_id)
            expected_order.append(section_id)
        expected_order.extend(
            record_id for record_id in section.get("record_ids", [])
            if isinstance(record_id, str) and record_id
        )
    record_anchor_ok = True
    for anchor_id in expected_order:
        if id_counts[anchor_id] != 1:
            errors.append(f"manuscript anchor {anchor_id} occurs {id_counts[anchor_id]} times; expected exactly once")
            record_anchor_ok = False
    expected_set = set(expected_order)
    observed_order = [match.group(2) for match in id_matches if match.group(2) in expected_set]
    section_set = set(expected_section_order)
    record_set = {p.get("record_id") for p in paragraphs if isinstance(p.get("record_id"), str)}
    observed_sections = [match.group(2) for match in id_matches if match.group(2) in section_set]
    observed_records = [match.group(2) for match in id_matches if match.group(2) in record_set]
    section_anchor_order_ok = observed_sections == expected_section_order
    paragraph_record_anchor_order_ok = observed_records == [p.get("record_id") for p in paragraphs]
    order_ok = (
        observed_order == expected_order
        and section_anchor_order_ok
        and paragraph_record_anchor_order_ok
    )
    if not order_ok:
        errors.append("manuscript section/record anchors do not follow candidate order")

    body_ok = record_anchor_ok
    anchor_positions = {match.group(2): index for index, match in enumerate(id_matches)}
    # 🤖Compare whole anchored blocks; finding the expected sentence somewhere is insufficient.
    for paragraph in paragraphs:
        record_id = paragraph.get('record_id')
        if id_counts[record_id] != 1:
            body_ok = False
            continue
        index = anchor_positions[record_id]
        start = markdown.find('>', id_matches[index].end()) + 1
        end = markdown.rfind('<', 0, id_matches[index + 1].start()) if index + 1 < len(id_matches) else len(markdown)
        try:
            observed = __manuscript_body(markdown[start:end])
            expected = __manuscript_body(paragraph.get('reader_text', paragraph.get('proofread_text', '')))
        except ValueError as exc:
            errors.append(f'{record_id}: {exc}')
            body_ok = False
            continue
        if observed != expected:
            errors.append(f'{record_id}: manuscript body differs from candidate reader_text')
            body_ok = False

    unresolved = candidate.get("unresolved_register", [])
    unresolved_ids = {
        entry.get("unresolved_id") for entry in unresolved
        if isinstance(entry.get("unresolved_id"), str) and entry.get("unresolved_id")
    }
    unresolved_anchor_ok = True
    for unresolved_id in sorted(unresolved_ids):
        if id_counts[unresolved_id] != 1:
            errors.append(
                f"{unresolved_id}: manuscript anchor occurs {id_counts[unresolved_id]} times; expected exactly once"
            )
            unresolved_anchor_ok = False

    expected_links: Counter[str] = Counter()
    reader_links_ok = True
    for paragraph in paragraphs:
        refs = set(refs_of(paragraph))
        paragraph_links = markdown_link_targets(paragraph.get("reader_text", ""))
        known_links = [target for target in paragraph_links if target in unresolved_ids]
        if set(known_links) != refs or len(known_links) != len(refs):
            errors.append(f"{paragraph.get('record_id')}: reader_text link targets do not match unresolved_refs")
            reader_links_ok = False
        expected_links.update(known_links)
    manuscript_links = Counter(
        target for target in markdown_link_targets(markdown)
        if target in unresolved_ids or re.fullmatch(r"[A-Za-z0-9_-]+-U\d+", target)
    )
    for target in sorted(set(expected_links) | set(manuscript_links)):
        if expected_links[target] != manuscript_links[target]:
            errors.append(
                f"{target}: manuscript unresolved-link count {manuscript_links[target]} "
                f"does not match reader_text count {expected_links[target]}"
            )
            reader_links_ok = False
    return {
        "checked": True,
        "record_anchor_coverage": record_anchor_ok,
        "record_anchor_order": order_ok,
        "section_anchor_order": section_anchor_order_ok,
        "paragraph_record_anchor_order": paragraph_record_anchor_order_ok,
        "unresolved_anchor_coverage": unresolved_anchor_ok,
        "unresolved_link_targets": reader_links_ok,
        "record_body_matches_reader_text": body_ok,
        "markdown_id_attribute_count": len(id_matches),
        "markdown_unresolved_link_count": sum(manuscript_links.values()),
    }, errors, sha256(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate", type=Path, help="reader-editor candidate JSON")
    ap.add_argument("--report", type=Path, help="output report (default: sibling *-preflight-report.json)")
    ap.add_argument("--markdown", type=Path, help="manuscript Markdown (default: candidate sibling with .md suffix)")
    ap.add_argument("--require-markdown", action="store_true", help="fail if the companion manuscript Markdown is missing")
    args = ap.parse_args()
    candidate_path = args.candidate.resolve()
    report_path = args.report.resolve() if args.report else candidate_path.with_name(candidate_path.stem + "-preflight-report.json")
    markdown_path = args.markdown.resolve() if args.markdown else candidate_path.with_suffix(".md")
    errors: list[str] = []
    checks: dict[str, object] = {}

    try:
        candidate = json.loads(candidate_path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"FAIL: cannot read candidate JSON: {e}", file=sys.stderr)
        return 2

    validator_sha256 = sha256(Path(__file__).resolve())
    schema_version = candidate.get("schema_version")
    if not __supported_schema(schema_version):
        report = {
            "status": "NOT_APPLICABLE_SCHEMA",
            "kind": "structural_preflight",
            "scope": "structural preflight only; schema is not supported by this validator",
            "schema_version": schema_version,
            "supported_schema_versions": sorted(SUPPORTED_SCHEMA_VERSIONS),
            "validator_sha256": validator_sha256,
            "candidate_path": str(candidate_path),
            "candidate_sha256": sha256(candidate_path),
            "reason": "Use the preflight contract that matches this candidate schema; do not interpret this status as PASS or FAIL.",
            "errors": [],
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 3

    source_layer = candidate.get("source_layer", {})
    source_files: dict[str, Path] = {}
    source_hashes: dict[str, str] = {}
    for path_key, hash_key in (
        ("frozen_segments_path", "frozen_segments_sha256"),
        ("punctuated_candidate_path", "punctuated_candidate_sha256"),
        ("source_manifest_path", "source_manifest_sha256"),
        ("funasr_output_path", "funasr_output_sha256"),
    ):
        relative = source_layer.get(path_key)
        if not relative:
            if path_key != "funasr_output_path":
                errors.append(f"source_layer missing {path_key}")
            continue
        path = Path(relative)
        if not path.is_absolute():
            path = candidate_path.parent / path
        path = path.resolve()
        if not path.is_file():
            errors.append(f"source path missing: {path_key}={path}")
            continue
        actual = sha256(path)
        expected = source_layer.get(hash_key)
        if not expected or actual.lower() != str(expected).lower():
            errors.append(f"source hash mismatch: {path_key}")
        source_files[path_key] = path
        source_hashes[path_key] = actual

    source_path = source_files.get("frozen_segments_path")
    punctuated_by_id = {}
    punctuated_segments = []
    punctuated_projection_ok = True
    if source_path:
        try:
            segments = load_jsonl(source_path)
            ids = [s["segment_id"] for s in segments]
            ordinals = [s["ordinal"] for s in segments]
            if len(ids) != len(set(ids)):
                errors.append("frozen source contains duplicate segment_id")
            if len(ordinals) != len(set(ordinals)):
                errors.append("frozen source contains duplicate ordinal")
            if ordinals != sorted(ordinals):
                errors.append("frozen source JSONL is not in ordinal order")
            source_by_id = {s["segment_id"]: s for s in segments}
            checks["source_segment_total"] = len(segments)
            checks["source_id_ordered"] = ordinals == sorted(ordinals)
        except Exception as e:
            errors.append(f"cannot parse frozen source: {e}")
            segments, source_by_id = [], {}
    else:
        segments, source_by_id = [], {}

    punctuated_path = source_files.get("punctuated_candidate_path")
    if punctuated_path:
        try:
            punctuated_segments = load_jsonl(punctuated_path)
            p_ids = [s["segment_id"] for s in punctuated_segments]
            p_ordinals = [s["ordinal"] for s in punctuated_segments]
            source_ids = [s["segment_id"] for s in segments]
            if p_ids != source_ids or p_ordinals != [s["ordinal"] for s in segments]:
                errors.append("punctuated candidate IDs/order differ from frozen source")
                punctuated_projection_ok = False
            punctuated_by_id = {s["segment_id"]: s for s in punctuated_segments}
            checks["punctuated_source_segment_total"] = len(punctuated_segments)
        except Exception as e:
            errors.append(f"cannot parse punctuated candidate: {e}")
            punctuated_projection_ok = False

    paragraphs = candidate.get("paragraphs", [])
    dispositions = candidate.get("non_body_boundary_disposition", [])
    sections = candidate.get("sections", [])
    record_ids = [p.get("record_id") for p in paragraphs]
    if any(not x for x in record_ids) or len(record_ids) != len(set(record_ids)):
        errors.append("paragraph record_id is missing or duplicated")
    record_id_set = set(record_ids)

    body_ids = [sid for p in paragraphs for sid in p.get("source_segment_ids", [])]
    nonbody_ids = [sid for d in dispositions for sid in d.get("source_segment_ids", [])]
    total_ids = body_ids + nonbody_ids
    counts = Counter(total_ids)
    duplicate_ids = sorted(s for s, n in counts.items() if n > 1)
    unknown_ids = sorted(set(total_ids) - set(source_by_id))
    missing_ids = sorted(set(source_by_id) - set(total_ids), key=lambda s: source_by_id[s]["ordinal"])
    if duplicate_ids:
        errors.append(f"source IDs covered more than once: {duplicate_ids[:8]}")
    if unknown_ids:
        errors.append(f"candidate references unknown source IDs: {unknown_ids[:8]}")
    if missing_ids:
        errors.append(f"source IDs not covered: {missing_ids[:8]}")
    checks["coverage_exact_once"] = not duplicate_ids and not unknown_ids and not missing_ids

    body_ordinals = [source_by_id[s]["ordinal"] for s in body_ids if s in source_by_id]
    if body_ordinals != sorted(body_ordinals):
        errors.append("body source IDs are not in frozen-source order")
    for disposition in dispositions:
        ords = [source_by_id[s]["ordinal"] for s in disposition.get("source_segment_ids", []) if s in source_by_id]
        if ords != sorted(ords):
            errors.append(f"disposition source IDs are not ordered: {disposition.get('disposition_id')}")
    checks["body_and_disposition_order"] = body_ordinals == sorted(body_ordinals)

    paragraph_by_id = {p["record_id"]: p for p in paragraphs if p.get("record_id")}
    replay_original_ok = True
    replay_presentation_ok = True
    reader_projection_ok = True
    empty_diff_errors = 0
    for paragraph in paragraphs:
        rid = paragraph.get("record_id", "<missing>")
        p_ids = paragraph.get("source_segment_ids", [])
        if any(sid not in source_by_id for sid in p_ids):
            continue
        if len(p_ids) != len(set(p_ids)):
            errors.append(f"{rid}: duplicate source IDs within paragraph")
        ords = [source_by_id[sid]["ordinal"] for sid in p_ids]
        if ords != sorted(ords):
            errors.append(f"{rid}: source IDs within paragraph are out of order")
        original = paragraph.get("original_candidate_text", "")
        reconstructed = "".join(source_by_id[sid].get("text", "") for sid in p_ids)
        if reconstructed != original:
            errors.append(f"{rid}: original_candidate_text does not reconstruct from frozen segments")
            replay_original_ok = False
        if punctuated_by_id:
            punctuated_text = paragraph.get("asr_punctuated_candidate_text")
            if not isinstance(punctuated_text, str):
                errors.append(f"{rid}: missing asr_punctuated_candidate_text")
                punctuated_projection_ok = False
            else:
                punctuated_reconstructed = "".join(
                    punctuated_by_id[sid].get("asr_punctuated_text", punctuated_by_id[sid].get("text", ""))
                    for sid in p_ids
                )
                if punctuated_reconstructed != punctuated_text:
                    errors.append(f"{rid}: asr_punctuated_candidate_text does not reconstruct from punctuated source")
                    punctuated_projection_ok = False
        locator = paragraph.get("source_locator", {})
        if p_ids:
            first, last = source_by_id[p_ids[0]], source_by_id[p_ids[-1]]
            if locator.get("start_ms") != first.get("start_ms") or locator.get("end_ms") != last.get("end_ms"):
                errors.append(f"{rid}: source locator does not match first/last source segments")
        proofread = paragraph.get("proofread_text", "")
        original_ops = paragraph.get("diff_from_original", [])
        if not original_ops and proofread != original:
            errors.append(f"{rid}: proofread differs from original but diff_from_original is empty")
            empty_diff_errors += 1
        try:
            if replay(original, original_ops, "source_char_start", "source_char_end", "proofread_text", f"{rid}.diff_from_original") != proofread:
                errors.append(f"{rid}: original-to-proofread diff does not replay")
                replay_original_ok = False
        except Exception as e:
            errors.append(str(e))
            replay_original_ok = False
        reader = paragraph.get("reader_text", proofread)
        if reader_body_without_uncertainty_links(reader) != proofread:
            errors.append(f"{rid}: reader_text body differs from proofread after removing uncertainty links")
            reader_projection_ok = False
        presentation_ops = paragraph.get("presentation_diff_from_proofread", [])
        if not presentation_ops and reader != proofread:
            errors.append(f"{rid}: reader_text differs from proofread but presentation diff is empty")
            empty_diff_errors += 1
        try:
            if replay(proofread, presentation_ops, "proofread_char_start", "proofread_char_end", "reader_text", f"{rid}.presentation_diff_from_proofread") != reader:
                errors.append(f"{rid}: proofread-to-reader presentation diff does not replay")
                replay_presentation_ok = False
        except Exception as e:
            errors.append(str(e))
            replay_presentation_ok = False

    checks["original_diff_replay"] = replay_original_ok
    checks["punctuated_candidate_projection_exact"] = punctuated_projection_ok
    checks["presentation_diff_replay"] = replay_presentation_ok
    checks["reader_body_matches_proofread_after_uncertainty_links"] = reader_projection_ok
    checks["empty_diff_consistency"] = empty_diff_errors == 0

    section_ids = [s.get("section_id") for s in sections]
    if any(not x for x in section_ids) or len(section_ids) != len(set(section_ids)):
        errors.append("section_id is missing or duplicated")
    section_record_refs = [rid for section in sections for rid in section.get("record_ids", [])]
    if Counter(section_record_refs) != Counter(record_ids):
        errors.append("section record_ids do not cover each paragraph exactly once")
    section_record_order_ok = section_record_refs == record_ids
    if not section_record_order_ok:
        errors.append("section record_ids do not preserve paragraph/source order")
    section_id_set = set(section_ids)
    for p in paragraphs:
        if p.get("section_id") and p["section_id"] not in section_id_set:
            errors.append(f"{p.get('record_id')}: unknown section_id {p['section_id']}")
    section_index = {section_id: index for index, section_id in enumerate(section_ids)}
    paragraph_section_order_ok = True
    last_section_index = -1
    for p in paragraphs:
        sid = p.get("section_id")
        if sid not in section_index:
            errors.append(f"{p.get('record_id')}: missing or unknown section_id {sid!r}")
            paragraph_section_order_ok = False
            continue
        current_index = section_index[sid]
        if current_index < last_section_index:
            errors.append(
                f"{p.get('record_id')}: section assignment moves backward in paragraph/source order"
            )
            paragraph_section_order_ok = False
        last_section_index = current_index
    section_source_ranges_ordered = True
    previous_section_max: int | None = None
    for section in sections:
        section_ordinals = [
            source_by_id[sid]["ordinal"]
            for rid in section.get("record_ids", [])
            for sid in paragraph_by_id.get(rid, {}).get("source_segment_ids", [])
            if sid in source_by_id
        ]
        if section_ordinals != sorted(section_ordinals):
            errors.append(f"{section.get('section_id')}: section source IDs are not ordered")
            section_source_ranges_ordered = False
        if section_ordinals:
            section_min, section_max = min(section_ordinals), max(section_ordinals)
            if previous_section_max is not None and section_min < previous_section_max:
                errors.append(
                    f"{section.get('section_id')}: section source range overlaps or moves backward"
                )
                section_source_ranges_ordered = False
            previous_section_max = section_max
    checks["section_record_order"] = section_record_order_ok
    checks["paragraph_section_order"] = paragraph_section_order_ok
    checks["section_source_ranges_ordered"] = section_source_ranges_ordered
    checks["section_links"] = Counter(section_record_refs) == Counter(record_ids) and all(
        not p.get("section_id") or p["section_id"] in section_id_set for p in paragraphs
    )

    unresolved = candidate.get("unresolved_register", [])
    unresolved_by_id = {u.get("unresolved_id"): u for u in unresolved if u.get("unresolved_id")}
    if len(unresolved_by_id) != len(unresolved):
        errors.append("unresolved_id is missing or duplicated")
    reverse_refs = {uid: set() for uid in unresolved_by_id}
    unresolved_entries_nonempty = True
    for p in paragraphs:
        for uid in refs_of(p):
            if uid not in unresolved_by_id:
                errors.append(f"{p.get('record_id')}: unresolved_ref points to missing {uid}")
            else:
                reverse_refs[uid].add(p["record_id"])
    for uid, entry in unresolved_by_id.items():
        linked_records = entry.get("reader_record_ids", [])
        candidate_spans = entry.get("candidate_spans", [])
        anchors = entry.get("anchors", [])
        if not isinstance(candidate_spans, list) or not candidate_spans or any(
            not isinstance(span, str) or not span.strip() for span in candidate_spans
        ):
            errors.append(f"{uid}: unresolved entry has no nonblank candidate spans")
            unresolved_entries_nonempty = False
        if not isinstance(anchors, list) or not anchors:
            errors.append(f"{uid}: unresolved entry has no source anchors")
            unresolved_entries_nonempty = False
            anchors = []
        valid_anchors = [anchor for anchor in anchors if isinstance(anchor, dict)]
        if len(valid_anchors) != len(anchors):
            errors.append(f"{uid}: anchors contain a non-object entry")
            unresolved_entries_nonempty = False
        if not isinstance(linked_records, list) or not linked_records:
            errors.append(f"{uid}: unresolved entry has no reader records")
            unresolved_entries_nonempty = False
            linked_records = []
        valid_linked_records = [rid for rid in linked_records if isinstance(rid, str) and rid]
        if len(valid_linked_records) != len(linked_records):
            errors.append(f"{uid}: reader_record_ids contains an invalid record ID")
            unresolved_entries_nonempty = False
        if len(valid_linked_records) != len(set(valid_linked_records)):
            errors.append(f"{uid}: duplicate reader_record_ids")
        if set(valid_linked_records) != reverse_refs[uid]:
            errors.append(f"{uid}: reader_record_ids do not match paragraph unresolved_refs")
        for anchor in valid_anchors:
            sid = anchor.get("source_segment_id")
            if sid not in source_by_id:
                errors.append(f"{uid}: anchor points to missing source segment {sid}")
                continue
            start, end = anchor.get("char_start_in_segment"), anchor.get("char_end_in_segment")
            raw = source_by_id[sid].get("text", "")
            if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start or end > len(raw):
                errors.append(f"{uid}: anchor offsets are invalid for {sid}")
                continue
            if raw[start:end] != anchor.get("candidate_span"):
                errors.append(f"{uid}: anchor text does not match frozen source for {sid}")
            rid = anchor.get("record_id")
            if rid not in record_id_set or sid not in paragraph_by_id.get(rid, {}).get("source_segment_ids", []):
                errors.append(f"{uid}: anchor paragraph does not contain its source segment")
    checks["unresolved_entries_nonempty"] = unresolved_entries_nonempty
    checks["unresolved_link_integrity"] = not any("unresolved" in e or "anchor" in e for e in errors)

    normalizations = candidate.get("normalization_register", [])
    seen_norms = set()
    for norm in normalizations:
        sid = norm.get("source_segment_id")
        key = (sid, norm.get("source_char_start"), norm.get("source_char_end"))
        if key in seen_norms:
            errors.append(f"duplicate normalization record at {key}")
        seen_norms.add(key)
        if sid not in source_by_id:
            errors.append(f"normalization points to missing source segment {sid}")
            continue
        raw = source_by_id[sid].get("text", "")
        start, end = norm.get("source_char_start"), norm.get("source_char_end")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start or end > len(raw):
            errors.append(f"normalization offsets invalid at {key}")
            continue
        if raw[start:end] != norm.get("source_form"):
            errors.append(f"normalization source_form mismatch at {key}")
        affected = [p for p in paragraphs if sid in p.get("source_segment_ids", [])]
        if len(affected) != 1:
            errors.append(f"normalization source span does not map to exactly one paragraph at {key}")
            continue
        paragraph = affected[0]
        source_offset = 0
        for paragraph_sid in paragraph.get("source_segment_ids", []):
            if paragraph_sid == sid:
                break
            source_offset += len(source_by_id.get(paragraph_sid, {}).get("text", ""))
        paragraph_start = source_offset + start
        paragraph_end = source_offset + end
        try:
            projected_forms = project_source_span(
                paragraph.get("original_candidate_text", ""),
                paragraph.get("diff_from_original", []),
                paragraph_start,
                paragraph_end,
            )
        except Exception as e:
            errors.append(f"normalization mapping cannot be checked at {key}: {e}")
            continue
        if not any(normalization_form_matches(projected, norm.get("proofread_form", "")) for projected in projected_forms):
            errors.append(f"normalization proofread_form does not match diff-projected source span at {key}")
    checks["normalization_integrity"] = len(seen_norms) == len(normalizations) and not any(
        "normalization" in e for e in errors
    )

    markdown_checks, markdown_errors, markdown_sha256 = validate_markdown_projection(
        markdown_path, candidate, required=args.require_markdown
    )
    checks["manuscript_markdown_projection"] = markdown_checks
    errors.extend(markdown_errors)

    validation = candidate.get("validation", {})
    expected_counts = {
        "source_segment_total": len(segments),
        "body_unique_source_ids": len(set(body_ids)),
        "non_body_unique_source_ids": len(set(nonbody_ids)),
        "record_count": len(paragraphs),
        "section_count": len(sections),
        "unresolved_group_count": len(unresolved),
        "unresolved_anchor_count": sum(len(u.get("anchors", [])) for u in unresolved),
        "reader_link_count": sum(len(u.get("reader_record_ids", [])) for u in unresolved),
        "normalization_count": len(normalizations),
    }
    for key, actual in expected_counts.items():
        if validation.get(key) != actual:
            errors.append(f"validation.{key}={validation.get(key)!r} but calculated {actual}")
    if validation.get("coverage_exact_once") is not True or not checks["coverage_exact_once"]:
        errors.append("declared or calculated source coverage is not exact-once")
    checks["declared_counts_match"] = all(validation.get(k) == v for k, v in expected_counts.items())

    report = {
        "status": "PASS" if not errors else "FAIL",
        "kind": "structural_preflight",
        "scope": "structural preflight only; no semantic or acoustic review",
        "not_checked": ["oral_editing_completeness", "case_and_meaning_retention",
                        "acoustic_accuracy", "visual_teaching_coverage", "target_reader_behavior"],
        "schema_version": schema_version,
        "validator_sha256": validator_sha256,
        "candidate_path": str(candidate_path),
        "candidate_sha256": sha256(candidate_path),
        "manuscript_path": str(markdown_path) if markdown_checks.get("checked") else None,
        "manuscript_sha256": markdown_sha256,
        "source_hashes": source_hashes,
        "checks": checks,
        "calculated_counts": expected_counts,
        "errors": errors,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
