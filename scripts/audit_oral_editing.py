#!/usr/bin/env python3
"""Lint reader-editor JSON for likely unfinished spoken-word cleanup.

This tool is deliberately advisory: it never edits text. It flags prose that
differs from the ASR candidate only in punctuation/spacing, filler runs, and a
small set of adjacent function-word repetitions for contextual review.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata


FILLER_RUN = re.compile(r"(?:呃|嗯|啊){2,}")
FILLER_TOKEN = re.compile(r"[呃嗯]")
REPEATED_WORDS = (
    "就是", "因为", "所以", "然后", "但是", "可是", "不过", "其实", "如果",
    "我们", "你们", "他们", "她们", "它们", "不是", "这个", "那个", "可以",
    "我", "你", "他", "她", "它", "这", "那", "就", "是", "因",
)
REPEATED_TOKEN = re.compile(
    r"(?P<token>" + "|".join(map(re.escape, sorted(REPEATED_WORDS, key=len, reverse=True)))
    + r")(?P=token)"
)
PARTIAL_REPETITION = re.compile(r"因因为|这这个|那那个|他他们|她她们|它它们|我我们|你你们")


def lexical_form(text: str) -> str:
    """Remove punctuation, separators, and formatting marks for edit comparison."""
    return "".join(
        char.casefold()
        for char in text
        if unicodedata.category(char)[0] not in {"P", "Z", "C"}
    )


def excerpt(text: str, start: int, end: int, radius: int = 42) -> str:
    left = max(0, start - radius)
    right = min(len(text), max(end, start + 1) + radius)
    prefix = "…" if left else ""
    suffix = "…" if right < len(text) else ""
    return prefix + text[left:right] + suffix


def _finding(record: dict, category: str, start: int, end: int,
             text: str, severity: str = "review", note: str = "", *,
             context_sha256: str) -> dict:
    record_id = record.get("record_id", "")
    matched_text = text[start:end] if end > start else ""
    stable_key = f"{record_id}\0{category}\0{start}\0{end}\0{matched_text}"
    return {
        "finding_id": hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:20],
        "context_sha256": context_sha256,
        "record_id": record_id,
        "source_segment_ids": record.get("source_segment_ids", []),
        "source_locator": record.get("source_locator", {}),
        "category": category,
        "severity": severity,
        "span": [start, end],
        "matched_text": matched_text,
        "context": excerpt(text, start, end),
        "note": note,
    }


def audit_record(record: dict, *, namespace: str = '', neighbors: list[dict] | None = None) -> list[dict]:
    proofread = str(record.get("proofread_text") or record.get("reader_text") or "")
    original = str(record.get("original_candidate_text") or "")
    asr = str(record.get("asr_punctuated_candidate_text") or "")
    findings: list[dict] = []
    # 🤖Bind decisions to this source/prose and immediate context, not the whole book revision.
    context = [{key: row.get(key) for key in (
        'record_id', 'source_segment_ids', 'source_locator', 'original_candidate_text',
        'asr_punctuated_candidate_text', 'proofread_text', 'reader_text',
    )} for row in [record, *(neighbors if neighbors else [])]]
    context_sha256 = hashlib.sha256(json.dumps(
        [namespace, context], ensure_ascii=False, sort_keys=True,
    ).encode('utf-8')).hexdigest()

    same_asr = bool(asr) and lexical_form(proofread) == lexical_form(asr)
    same_original = bool(original) and lexical_form(proofread) == lexical_form(original)
    if same_asr:
        findings.append(_finding(
            record, "punctuation_or_spacing_only_vs_asr", 0, 0, proofread,
            "info",
            "校对稿与标点候选去除标点/空白后相同；这不是错误证明，但需确认本段确实无需口语清理或措辞整理。",
            context_sha256=context_sha256,
        ))
    if same_original and asr:
        findings.append(_finding(
            record, "punctuation_or_spacing_only_vs_source", 0, 0, proofread,
            "info",
            "校对稿与冻结原文去除标点/空白后相同；请确认词语层面的修订确实不需要。",
            context_sha256=context_sha256,
        ))

    filler_runs = list(FILLER_RUN.finditer(proofread))
    for match in filler_runs:
        findings.append(_finding(record, "filler_run", match.start(), match.end(), proofread, "review",
                                 "连续填充音候选；结合语境判断是否为肯定、回应、强调或口误。",
                                 context_sha256=context_sha256))
    for match in FILLER_TOKEN.finditer(proofread):
        if any(match.start() < run.end() and match.end() > run.start() for run in filler_runs):
            continue
        findings.append(_finding(record, "filler_token", match.start(), match.end(), proofread, "review",
                                 "口头填充音候选；结合语境判断是否为肯定、回应、强调或自我修正。",
                                 context_sha256=context_sha256))
    for category, pattern, note in (
        ("adjacent_repetition", REPEATED_TOKEN, "相邻功能词/代词重复候选；核对是否为口吃、自我修正或有意强调。"),
        ("partial_word_repetition", PARTIAL_REPETITION, "词首重复候选；请对照原文与上下文，不要机械替换。"),
    ):
        for match in pattern.finditer(proofread):
            findings.append(_finding(record, category, match.start(), match.end(), proofread, "review", note,
                                     context_sha256=context_sha256))
    return findings


def audit_file(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("paragraphs"), list):
        raise ValueError(f"Expected a reader-editor JSON object with a paragraphs array: {path}")
    paragraphs = [row for row in data["paragraphs"] if isinstance(row, dict)]
    identity = [data.get('course_id'), data.get('lesson_id'),
                data.get('source_layer', {}).get('frozen_segments_path')]
    namespace = json.dumps(identity if any(identity) else [path.resolve().parent.as_posix()])
    findings = [item for index, row in enumerate(paragraphs)
                for item in audit_record(row, namespace=namespace,
                    neighbors=paragraphs[max(0, index - 1):index] + paragraphs[index + 1:index + 2])]
    categories = Counter(item["category"] for item in findings)
    paragraph_findings = {item["record_id"] for item in findings if item["record_id"]}
    same_asr = categories["punctuation_or_spacing_only_vs_asr"]
    same_source = categories["punctuation_or_spacing_only_vs_source"]
    return {
        "input": str(path),
        "lesson_id": data.get("course_id") or data.get("lesson_id") or path.stem,
        "paragraph_count": len(paragraphs),
        "punctuation_or_spacing_only_vs_asr": same_asr,
        "punctuation_or_spacing_only_vs_source": same_source,
        "finding_paragraph_count": len(paragraph_findings),
        "finding_count_by_category": dict(sorted(categories.items())),
        "findings": findings,
    }


def markdown_report(results: list[dict]) -> str:
    lines = [
        "# Spoken-text cleanup lint",
        "",
        "This is a review queue, not an automatic correction or semantic verdict.",
        "Residue findings require a contextual keep decision; punctuation-only signals are advisory.",
        "",
        "| Lesson | Paragraphs | Punctuation-only vs ASR | Punctuation-only vs source | Paragraphs flagged | Open residue | Advisory |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result['lesson_id']} | {result['paragraph_count']} | "
            f"{result['punctuation_or_spacing_only_vs_asr']} | "
            f"{result['punctuation_or_spacing_only_vs_source']} | "
            f"{result['finding_paragraph_count']} | {result['unresolved_count']} | {result['advisory_count']} |"
        )
    # 🤖One paragraph context per review group; full per-finding detail stays in the JSON sidecar.
    for result in results:
        grouped: dict[str, list[dict]] = {}
        for finding in result['findings']:
            if finding['severity'] != 'info':
                grouped.setdefault(finding['record_id'], []).append(finding)
        if grouped:
            lines += ['', f"## {result['lesson_id']}", '']
        for record_id, findings in grouped.items():
            categories = ', '.join(
                f"{item['category']}@{item['span'][0]}:{item['span'][1]} ({item['disposition']})"
                for item in findings
            )
            lines += [f'- {record_id}: {categories} ({len(findings)} signals)',
                      f"  {findings[0]['context']}"]
    lines += [
        "",
        "## Review rules",
        "",
        "- Punctuation-only matches are advisory; unchanged good prose needs no keep paperwork.",
        "- Filler and repetition matches must be checked against speech acts, emphasis, correction, and lesson meaning.",
        "- Do not use an empty finding count as proof of source coverage, acoustic accuracy, or semantic fidelity.",
        "- The JSON sidecar contains exact record IDs, source locators, spans, and short context windows.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True,
                        help="Reader-editor JSON; repeat for a course batch.")
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-markdown", type=Path)
    parser.add_argument("--decisions", type=Path,
                        help="Project-local keep decisions keyed by finding_id and context_sha256.")
    parser.add_argument("--strict", action="store_true",
                        help="Return exit code 2 while residue findings lack a current contextual keep decision.")
    args = parser.parse_args()
    results = [audit_file(Path(path)) for path in args.input]
    decisions_by_id = {}
    if args.decisions:
        decision_data = json.loads(args.decisions.read_text(encoding="utf-8-sig"))
        for decision in decision_data.get("decisions", []):
            if (decision.get('decision') == 'keep' and isinstance(decision.get('reason'), str)
                    and decision['reason'].strip()):
                decisions_by_id[(str(decision.get("finding_id", "")),
                                 decision.get('context_sha256'))] = decision
    for result in results:
        unresolved = 0
        reviewed = 0
        for finding in result["findings"]:
            decision = decisions_by_id.get((finding['finding_id'], finding['context_sha256']))
            if finding['severity'] == 'info':
                finding['disposition'] = 'advisory'
            elif decision:
                finding["disposition"] = "keep"
                finding['decision_binding'] = 'current'
                finding["decision_reason"] = str(decision["reason"]).strip()
                reviewed += 1
            else:
                finding["disposition"] = "open"
                finding['decision_binding'] = 'missing_or_stale'
                unresolved += 1
        result["finding_count"] = len(result["findings"])
        result["reviewed_keep_count"] = reviewed
        result["unresolved_count"] = unresolved
        result['advisory_count'] = sum(item['severity'] == 'info' for item in result['findings'])
    findings = sum(row["finding_count"] for row in results)
    unresolved = sum(row["unresolved_count"] for row in results)
    advisory = sum(row['advisory_count'] for row in results)
    if unresolved:
        status = 'needs_review'
    elif findings > advisory:
        status = 'reviewed'
    elif advisory:
        status = 'advisory_only'
    else:
        status = 'no_rule_findings'
    payload = {
        "schema_version": "oral-edit-lint/1.1",
        "kind": "oral_residue_lint",
        "scope": "Rule matches in the supplied records only; contextual keep decisions are declarations, not verified semantics.",
        "status": status,
        "finding_count": findings,
        "unresolved_finding_count": unresolved,
        "advisory_finding_count": advisory,
        "files": results,
        "limitations": [
            "This script does not edit text or decide whether a filler/repetition is meaningful.",
            "A clean lint result does not establish semantic, acoustic, or source-coverage acceptance.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(markdown_report(results), encoding="utf-8")
    print(f"{payload['status']}: {unresolved} unresolved residue; {advisory} advisory signals across {len(results)} file(s)")
    return 2 if args.strict and unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
