#!/usr/bin/env python3
"""RTA experimental evidence workbench: read-only except explicit normalize output.

This is NOT a general SourceSet schema, semantic search engine, or source-truth verifier.
All subcommands operate on explicit files. No auto discovery, model calls or network.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

HELD = {'retracted', 'superseded', 'hold', 'excluded', 'private_hold'}
VER_RX = re.compile(r'(?i)\bv?(\d+)\.(\d+)\.(\d+)[-_.]?(rc|alpha|beta)[-_.]?(\d+)\b')
KIND_TEXT_KEYS = {
    'paragraph': ('text',), 'course_paragraph': ('proofread_text',),
    'uncertainty': ('text',), 'localized_uncertainty': ('note',),
    'body_figure': ('caption',), 'course_figure': ('caption', 'alt'),
    'source_page': ('description',), 'source_page_image': ('description',),
    'pdf_reference_text_page': ('text',), 'notion_page': ('source_markdown',),
    'directory-entry': ('source_text',), 'editorial_boundary': ('note',),
    'document_supported_normalization': ('note',),
    'external-resource-link': ('source_text',),
}
SUPPORTED = set(KIND_TEXT_KEYS)


def json_dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def load_jsonl(path: Path):
    with path.open('rb') as f:
        for i, raw in enumerate(f, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw.decode('utf-8-sig' if i == 1 else 'utf-8'))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError(f'{path.name}:{i}: invalid JSONL: {exc}') from exc
            if not isinstance(row, dict):
                raise ValueError(f'{path.name}:{i}: expected JSON object')
            yield i, row, hashlib.sha256(raw.rstrip(b'\r\n')).hexdigest()


def _text(v: object) -> str:
    return v.strip() if isinstance(v, str) else ''


def record_adapter(row: dict, line: int, digest: str, collection: str) -> tuple[dict | None, str]:
    """Convert explicitly supported projection rows. Never infer source truth or permissions."""
    inner = row.get('record') if isinstance(row.get('record'), dict) else row
    kind = inner.get('record_type') or inner.get('kind')
    if kind not in SUPPORTED:
        return None, str(kind or 'unknown_type')
    source = _text(inner.get('source_id'))
    if not source:
        return None, 'missing_source_id'
    ident = next((_text(inner.get(k)) for k in
                  ('record_id', 'paragraph_id', 'figure_id', 'uncertainty_id', 'page_anchor')
                  if _text(inner.get(k))), '')
    if not ident and kind in ('source_page', 'source_page_image', 'pdf_reference_text_page'):
        page = inner.get('page_number', inner.get('source_page'))
        if isinstance(page, int) and page >= 0:
            ident = f'{kind}:{source}:{page}'
    if not ident:
        return None, 'missing_unit_id'
    href = next((_text(inner.get(k)) for k in
                 ('epub_locator', 'source_locator', 'paragraph_anchor', 'body_locator', 'epub_href')
                 if _text(inner.get(k))), '')
    if not href and kind == 'source_page':
        atlas = _text(inner.get('atlas_document'))
        anchor = _text(inner.get('page_anchor'))
        if atlas and anchor:
            href = atlas + '#' + anchor
    if not href:
        chapter = _text(inner.get('chapter_href'))
        anchor = _text(inner.get('dom_anchor_id', inner.get('anchor_id')))
        if chapter:
            href = chapter + (f'#{anchor}' if anchor else '')
    locator = {}
    if href:
        locator['epub_href'] = href
    for src, dest in [('source_context_locator', 'source_context'),
                      ('video_timestamp_candidate', 'sample_time'),
                      ('sample_time', 'sample_time'),
                      ('page_number', 'source_page'),
                      ('source_page', 'source_page')]:
        val = inner.get(src)
        if val is not None and val != '' and dest not in locator:
            locator[dest] = val
    # A unit with no EPUB locator or page/time cannot be made precise by guessing.
    if kind == 'notion_page':
        url = _text(inner.get('source_url'))
        if url.startswith(('https://','http://')):
            locator['source_url'] = url  # opaque provenance locator: NEVER fetched by this tool
        if inner.get('capture_date'):
            locator['capture_date'] = inner['capture_date']
    if kind == 'external-resource-link':
        url = _text(inner.get('uri'))
        if url.startswith(('https://','http://')):
            locator['external_url_unvisited'] = url
    if not locator:
        return None, 'no_supported_locator'
    parts = [v.strip() for k in KIND_TEXT_KEYS[kind]
             if isinstance((v := inner.get(k)), str) and v.strip()]
    metadata_only = kind in {'source_page', 'source_page_image'} and not parts
    if not parts and not metadata_only:
        return None, 'no_readable_text'
    status = _text(inner.get('status')) or ('metadata_only' if metadata_only else 'candidate')
    if kind in ('uncertainty', 'localized_uncertainty') and status == 'candidate':
        status = 'unresolved_candidate'
    if kind == 'external-resource-link' and status == 'candidate':
        status = 'external_unvisited'
    version = _text(inner.get('version')) or _text(row.get('edition'))
    result = {
        'id': f'{collection}:{ident}',
        'source_id': f'{collection}:{source}',
        'kind': kind,
        'locator': locator,
        'text': '\n'.join(parts),
        'status': status,
        'source_projection': 'rta-agent-current-envelope/1.0' if inner is not row else 'flat-records',
        'source_unit_id': ident,
        'origin_line': line,
        'origin_line_sha256': digest,
        'edition': version or None,
        'review': 'not_inferred',
        'readable_text_status': 'no_verified_text' if metadata_only else 'present_unverified',
    }
    # Scope fields are labels only; never promote sampled time to onset.
    sem = inner.get('time_semantics') or inner.get('source_time_semantics')
    if sem:
        result['locator']['time_semantics'] = sem
    return result, ''


def _safe_collection(collection: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,70}', collection):
        raise ValueError('collection must match [A-Za-z0-9][A-Za-z0-9_.-]{0,70}')
    return collection


def normalize(input_path: Path, output_path: Path, collection: str) -> dict:
    if not input_path.is_file():
        raise ValueError('input JSONL not found')
    if input_path.resolve() == output_path.resolve() or output_path.exists() or output_path.is_symlink():
        raise FileExistsError('refusing to overwrite input or an existing output')
    _safe_collection(collection)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    seen = set()
    output_path = output_path.resolve()
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=output_path.parent, prefix='rta-normalize-',
                                         suffix='.tmp', delete=False) as f:
            temp = Path(f.name)
            for line, raw, digest in load_jsonl(input_path):
                unit, reason = record_adapter(raw, line, digest, collection)
                if unit is None:
                    counts[f'skipped:{reason}'] += 1
                    continue
                if unit['id'] in seen:
                    raise ValueError(f'duplicate normalized ID at line {line}: {unit["id"]}')
                seen.add(unit['id'])
                f.write(json.dumps(unit, ensure_ascii=False, sort_keys=True) + '\n')
                counts['converted'] += 1
            f.flush()
    except Exception:
        if temp is not None:
            temp.unlink(missing_ok=True)
        raise
    assert temp is not None
    try:
        # Atomic no-replace hard link (same directory), like existing evidence_index.
        import os
        os.link(temp, output_path)
    finally:
        temp.unlink(missing_ok=True)
    return {
        'status': 'NORMALIZED', 'collection': collection,
        'converted': counts.pop('converted', 0),
        'skipped_by_reason': {k.split(':', 1)[1]: v for k, v in sorted(counts.items())},
        'output': str(output_path),
        'scope': 'Compatibility projection only; excluded rows and review status remain explicit.',
    }


def load_units(records: Path) -> list[dict]:
    units = []
    seen = set()
    for line, row, _ in load_jsonl(records):
        for key in ('id', 'source_id', 'kind', 'locator', 'status'):
            if key not in row:
                raise ValueError(f'line {line}: missing normalized field {key}')
        if row['id'] in seen:
            raise ValueError(f'line {line}: duplicate id {row["id"]}')
        if not isinstance(row['locator'], dict) or not row['locator']:
            raise ValueError(f'line {line}: missing source locator')
        seen.add(row['id'])
        units.append(row)
    return units


def coverage(records: Path, declared: Path | None = None) -> dict:
    units = load_units(records)
    counts = Counter(u['status'] for u in units)
    kinds = Counter(u['kind'] for u in units)
    sources = Counter(u['source_id'] for u in units)
    report = {
        'status': 'MEASURED_INDEX_SCOPE', 'indexed_units': len(units),
        'by_status': dict(sorted(counts.items())), 'by_kind': dict(sorted(kinds.items())),
        'source_ids_count': len(sources), 'sources': dict(sorted(sources.items())),
        'source_total_coverage': 'UNKNOWN',
        'warning': 'A count of indexed units is NOT source completeness or semantic fidelity.',
    }
    if declared:
        manifest = json.loads(declared.read_text(encoding='utf-8'))
        expected = manifest.get('expected_unit_ids') if isinstance(manifest, dict) else None
        if (not isinstance(expected, list) or not expected
                or any(not isinstance(s, str) or not s for s in expected)
                or len(set(expected)) != len(expected)):
            raise ValueError('scope must include a nonempty unique expected_unit_ids list')
        got = {u['id'] for u in units}
        report['declared_scope'] = {'expected': len(expected), 'present': len(set(expected) & got),
                                    'missing_ids': sorted(set(expected) - got),
                                    'unknown_extra_ids': sorted(got - set(expected)),
                                    'scope_status': 'DECLARATION_ONLY_NOT_SOURCE_AUDIT'}
    return report


def trace(records: Path, target: str, include_held: bool = False) -> dict:
    data = {r['id']: r for r in load_units(records)}
    if target not in data:
        return {'status': 'NOT_FOUND_IN_PROJECTION', 'id': target,
                'warning': 'Not indexed does not mean absent from original material.'}
    seen, in_stack, missing, steps, cycles = set(), set(), set(), [], []
    def visit(k: str, depth: int):
        if depth > 64:
            raise ValueError('lineage depth exceeds 64 (possible invalid records)')
        if k in in_stack:
            cycles.append(k)
            return
        if k in seen:
            return
        if k not in data:
            missing.add(k)
            return
        in_stack.add(k)
        rec = data[k]
        refs = rec.get('derived_from', [])
        if not isinstance(refs, list) or any(not isinstance(r, str) for r in refs):
            raise ValueError(f'{k}: derived_from must be a list of IDs')
        for ref in refs:
            visit(ref, depth + 1)
        in_stack.remove(k)
        seen.add(k)
        steps.append({'id': k, 'source_id': rec['source_id'], 'kind': rec['kind'],
                      'locator': rec['locator'], 'status': rec['status'],
                      'withheld_by_default': rec['status'] in HELD,
                      'origin_line_sha256': rec.get('origin_line_sha256')})
    visit(target, 0)
    if data[target]['status'] in HELD and not include_held:
        return {'status': 'HELD', 'id': target, 'hint': 'Explicit --include-held to inspect metadata.'}
    return {'status': 'TRACED_METADATA_ONLY', 'id': target, 'lineage': steps,
            'missing_references': sorted(missing), 'cycles': cycles,
            'warning': 'Lineage links and hashes do not establish truth or source coverage.'}


def load_review_records(path: Path | None) -> tuple[dict[str, dict], str | None]:
    """Load an explicit review sidecar; source projections never certify themselves."""
    if path is None:
        return {}, None
    raw = path.read_bytes()
    data = json.loads(raw.decode('utf-8-sig'))
    rows = data.get('reviews') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError('review file must contain an array "reviews"')
    allowed_scopes = {'observed_state', 'continuous_transition',
                      'procedure_replay', 'support_of_target'}
    allowed_assessments = {'supports', 'contradicts', 'inconclusive'}
    reviews = {}
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
            raise ValueError(f'review {i} missing ID')
        if row['id'] in reviews:
            raise ValueError(f'duplicate review ID: {row["id"]}')
        if row.get('scope') not in allowed_scopes:
            raise ValueError(f'{row["id"]}: unsupported review scope')
        evidence_ids = row.get('evidence_ids')
        if not isinstance(evidence_ids, list) or not evidence_ids or any(
            not isinstance(k, str) or not k for k in evidence_ids
        ) or len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError(f'{row["id"]}: nonempty unique evidence_ids required')
        if not _text(row.get('reviewer')) or not _text(row.get('method')):
            raise ValueError(f'{row["id"]}: reviewer and method are required')
        if row.get('assessment') not in allowed_assessments:
            raise ValueError(f'{row["id"]}: unsupported assessment')
        limits = row.get('limitations')
        if not isinstance(limits, list) or any(not isinstance(x, str) for x in limits):
            raise ValueError(f'{row["id"]}: limitations must be a string array')
        hashes = row.get('origin_line_sha256')
        if not isinstance(hashes, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in hashes.items()
        ):
            raise ValueError(f'{row["id"]}: origin_line_sha256 must be an ID-to-digest map')
        artifacts = row.get('evidence_artifacts', [])
        if not isinstance(artifacts, list):
            raise ValueError(f'{row["id"]}: evidence_artifacts must be an array')
        for artifact in artifacts:
            if not isinstance(artifact, dict) or not isinstance(artifact.get('path'), str):
                raise ValueError(f'{row["id"]}: each evidence artifact needs a relative path')
            artifact_path = Path(artifact['path'])
            if artifact_path.is_absolute() or '..' in artifact_path.parts:
                raise ValueError(f'{row["id"]}: evidence artifact path must be relative and contained')
            if not isinstance(artifact.get('sha256'), str) or not re.fullmatch(
                r'[0-9a-f]{64}', artifact['sha256']
            ):
                raise ValueError(f'{row["id"]}: evidence artifact needs a lowercase SHA-256')
        reviews[row['id']] = row
    return reviews, hashlib.sha256(raw).hexdigest()


def verify_review_artifacts(review: dict, evidence_root: Path | None) -> tuple[bool, list[str], int]:
    artifacts = review.get('evidence_artifacts', [])
    if not artifacts:
        return True, [], 0
    if evidence_root is None:
        return False, ['review_evidence_root_required'], 0
    root = evidence_root.resolve()
    if not root.is_dir():
        return False, ['review_evidence_root_unavailable'], 0
    failures = []
    checked = 0
    for artifact in artifacts:
        candidate = (root / artifact['path']).resolve()
        if candidate != root and root not in candidate.parents:
            failures.append('review_evidence_path_unsafe')
            continue
        if not candidate.is_file():
            failures.append('review_evidence_artifact_missing')
            continue
        digest = hashlib.sha256()
        with candidate.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        checked += 1
        if digest.hexdigest() != artifact['sha256']:
            failures.append('review_evidence_artifact_hash_mismatch')
    return not failures, sorted(set(failures)), checked


def audit_claims(records: Path, claims_path: Path, reviews_path: Path | None = None,
                 evidence_root: Path | None = None) -> dict:
    units = {r['id']: r for r in load_units(records)}
    reviews, review_digest = load_review_records(reviews_path)
    artifact_checks = {}
    checked_artifacts = 0
    data = json.loads(claims_path.read_text(encoding='utf-8'))
    claims = data.get('claims') if isinstance(data, dict) else None
    if not isinstance(claims, list):
        raise ValueError('claims file must contain an array "claims"')
    out = []
    for i, claim in enumerate(claims, 1):
        if not isinstance(claim, dict) or not isinstance(claim.get('id'), str):
            raise ValueError(f'claim {i} missing ID')
        category = claim.get('type')
        if category not in {'observed_state', 'transition', 'procedure', 'source_mapping'}:
            raise ValueError(f'{claim["id"]}: unsupported type {category!r}')
        refs = claim.get('evidence_ids')
        if not isinstance(refs, list) or not refs or any(not isinstance(s, str) for s in refs):
            raise ValueError(f'{claim["id"]}: nonempty evidence_ids required')
        selected = [units[k] for k in refs if k in units]
        missing = sorted(set(refs) - units.keys())
        held = sorted(r['id'] for r in selected if r['status'] in HELD)
        reasons = []
        claim_reviews = []
        review_ids = claim.get('review_ids')
        if not isinstance(review_ids, list) or not review_ids or any(
            not isinstance(k, str) or not k for k in review_ids
        ):
            reasons.append('explicit_review_ids_required')
            review_ids = []
        for review_id in review_ids:
            review = reviews.get(review_id)
            if review is None:
                reasons.append('missing_review_id')
                continue
            relevant = sorted(set(review['evidence_ids']) & set(refs))
            if not relevant:
                reasons.append('review_does_not_cover_claim_evidence')
                continue
            if any(k not in units for k in relevant):
                reasons.append('review_evidence_id_missing')
                continue
            if any(review['origin_line_sha256'].get(k) != units[k].get('origin_line_sha256')
                   for k in relevant):
                reasons.append('review_not_bound_to_current_input_rows')
                continue
            if review_id not in artifact_checks:
                artifact_checks[review_id] = verify_review_artifacts(review, evidence_root)
            artifacts_ok, artifact_reasons, artifact_count = artifact_checks[review_id]
            checked_artifacts += artifact_count
            if not artifacts_ok:
                reasons.extend(artifact_reasons)
                continue
            claim_reviews.append(review)
        if missing:
            reasons.append('missing_evidence_ids')
        if held:
            reasons.append('held_or_retracted_evidence')
        if category == 'observed_state':
            if not any(r.get('scope') == 'observed_state' and r.get('assessment') == 'supports'
                       for r in claim_reviews):
                reasons.append('observed_state_review_not_bound')
        if category == 'transition':
            if not any(r.get('scope') == 'continuous_transition'
                       and r.get('assessment') == 'supports'
                       and r.get('time_semantics') in {'verified_interval', 'verified_onset'}
                       for r in claim_reviews):
                reasons.append('sampled_frames_do_not_prove_transition')
        if category == 'procedure':
            if not any(r.get('scope') == 'procedure_replay'
                       and r.get('assessment') == 'supports'
                       and r.get('replay_result') == 'passed' for r in claim_reviews):
                reasons.append('procedure_replay_not_established')
        if category == 'source_mapping':
            target = claim.get('target_id')
            matching_scope = [r for r in claim_reviews
                              if r.get('scope') == 'support_of_target'
                              and isinstance(target, str) and target
                              and r.get('target_id') == target]
            if not matching_scope:
                reasons.append('evidence_scope_does_not_match_target')
            elif not any(r.get('assessment') == 'supports' for r in matching_scope):
                reasons.append('review_does_not_support_claim')
        out.append({'id': claim['id'], 'type': category,
                    'status': 'NEEDS_REVIEW' if reasons else 'REVIEW_BINDING_READY_NOT_TRUTH_VERIFIED',
                    'reasons': reasons, 'missing': missing, 'held': held,
                    'evidence_count': len(selected), 'review_ids': review_ids})
    return {'status': 'CLAIM_CONTRACT_CHECKED', 'claims': out,
            'needs_review_count': sum(r['status'] == 'NEEDS_REVIEW' for r in out),
            'review_file_sha256': review_digest,
            'evidence_artifacts_checked': checked_artifacts,
            'warning': 'Review bindings are supplied records; this tool does not inspect source content or verify reviewer judgments.'}


def _ver(s: str) -> str | None:
    m = VER_RX.search(s or '')
    return (f'{m.group(1)}.{m.group(2)}.{m.group(3)}-{m.group(4).lower()}.{m.group(5)}'
            if m else None)


def epub_title(epub: Path) -> str:
    with zipfile.ZipFile(epub) as z:
        if z.testzip():
            raise ValueError('EPUB failed ZIP integrity check')
        from posixpath import dirname, normpath
        container = ET.fromstring(z.read('META-INF/container.xml'))
        rf = next((n for n in container.iter() if n.tag.endswith('rootfile')), None)
        if rf is None or not rf.attrib.get('full-path'):
            raise ValueError('EPUB has no rootfile')
        opf = normpath(rf.attrib['full-path'])
        if opf.startswith('../') or opf.startswith('/'):
            raise ValueError('unsafe EPUB rootfile')
        root = ET.fromstring(z.read(opf))
        title = next((n.text.strip() for n in root.iter() if n.tag.endswith('}title') and n.text), None)
        if not title:
            raise ValueError('EPUB title not found')
        return title


def projection_drift(projection: Path, epub: Path, expected: str | None) -> dict:
    book = next((row for _, row, _ in load_jsonl(projection)
                 if row.get('record_type') == 'book'), None)
    title = epub_title(epub)
    if book is None:
        return {'status': 'NOT_APPLICABLE', 'reason': 'No flat book header in projection.',
                'epub_title_version': _ver(title)}
    truth = _ver(expected) if expected else _ver(str(book.get('version') or ''))
    checked = {
        'explicit_version': truth, 'book_field_version': _ver(str(book.get('version') or '')),
        'projection_title_version': _ver(str(book.get('title') or '')),
        'epub_title_version': _ver(title),
    }
    mismatches = [k for k in ('book_field_version', 'projection_title_version', 'epub_title_version')
                  if truth and checked[k] and checked[k] != truth]
    uncheckable = [k for k in ('book_field_version', 'projection_title_version', 'epub_title_version')
                   if not checked[k]]
    return {'status': 'DRIFT_DETECTED' if mismatches else 'CHECKED_WITH_GAPS' if uncheckable else 'VERSION_CONSISTENT',
            'version_fields': checked, 'mismatched_fields': mismatches,
            'uncheckable_fields': uncheckable,
            'note': 'Only edition version strings, not text equality or EPUB projection accuracy.'}


def doctor() -> dict:
    from importlib.util import find_spec
    return {'status': 'ENVIRONMENT_CHECKED', 'python': sys.version.split()[0],
            'python_3_11_or_later': sys.version_info >= (3, 11),
            'tools': {k: shutil.which(k) for k in ('ffmpeg', 'ffprobe')},
            'optional_python_modules': {k: bool(find_spec(k)) for k in ('diff_match_patch', 'PIL')},
            'network_or_install_attempted': False,
            'note': 'Optional dependency absence is not a failed source audit.'}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest='cmd', required=True)
    n = subs.add_parser('normalize', help='Read legacy projection and write independent normalized JSONL')
    n.add_argument('--input', type=Path, required=True)
    n.add_argument('--output', type=Path, required=True)
    n.add_argument('--collection', required=True)
    c = subs.add_parser('coverage', help='Index scope only; never infer original source coverage')
    c.add_argument('--records', type=Path, required=True)
    c.add_argument('--declared-scope', type=Path)
    t = subs.add_parser('trace', help='Read explicit lineage metadata without running source content')
    t.add_argument('--records', type=Path, required=True)
    t.add_argument('--id', required=True)
    t.add_argument('--include-held', action='store_true')
    a = subs.add_parser('audit-claims', help='Conservative claim-to-evidence contract check')
    a.add_argument('--records', type=Path, required=True)
    a.add_argument('--claims', type=Path, required=True)
    a.add_argument('--reviews', type=Path, help='Optional separately authored review-record JSON')
    a.add_argument('--evidence-root', type=Path, help='Optional root for relative evidence_artifacts paths')
    d = subs.add_parser('projection-drift', help='Compare edition version labels only')
    d.add_argument('--projection', type=Path, required=True)
    d.add_argument('--epub', type=Path, required=True)
    d.add_argument('--expected-version')
    subs.add_parser('doctor', help='Report environment readiness without installation')
    args = p.parse_args(argv)
    try:
        if args.cmd == 'normalize':
            result = normalize(args.input, args.output, args.collection)
        elif args.cmd == 'coverage':
            result = coverage(args.records, args.declared_scope)
        elif args.cmd == 'trace':
            result = trace(args.records, args.id, args.include_held)
        elif args.cmd == 'audit-claims':
            result = audit_claims(args.records, args.claims, args.reviews, args.evidence_root)
        elif args.cmd == 'projection-drift':
            result = projection_drift(args.projection, args.epub, args.expected_version)
        else:
            result = doctor()
        print(json_dump(result))
        return 3 if result['status'] in {'DRIFT_DETECTED'} or result.get('needs_review_count', 0) > 0 else 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(f'RTA_TRIAL_ERROR: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
