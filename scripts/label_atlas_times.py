#!/usr/bin/env python3
"""Make the time status visible on every numbered PPT atlas page.
- 🎯Show an accepted sample point or an explicit unknown label per page.
- 📌Read only the page-level data-time-status and data-sample-time metadata.
- 🤖Agent implementation; it does not decide whether a page/time match is valid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import BinaryIO
import xml.etree.ElementTree as ET
import zipfile


XHTML_NAMESPACE: str = 'http://www.w3.org/1999/xhtml'
'''📜Namespace used by EPUB XHTML documents.'''

EPUB_NAMESPACE: str = 'http://www.idpf.org/2007/ops'
'''📜Namespace prefix used by EPUB navigation metadata.'''

ATLAS_PAGE_CLASS: str = 'atlas-page'
'''📜Class that identifies one source slide/page entry.'''

TIME_LABEL_CLASS: str = 'atlas-time-status'
'''📜Class used for a visible atlas-page time-status line.'''

BUFFER_SIZE: int = 1024 * 1024
'''📜Streaming buffer size for copying ZIP entries.'''

TIMESTAMP_PATTERN = re.compile(r'^\d{2,}:\d{2}:\d{2}$')
'''📜Accepted EPUB sample-time format: HH:MM:SS.'''

KNOWN_TIME_STATUSES: frozenset[str] = frozenset({
    'accepted_video_sample_point_only',
    'accepted_sample_point_only',
})
'''📜Page matches whose timestamp has been visually accepted as a sample point.'''

UNKNOWN_TIME_STATUSES: frozenset[str] = frozenset({
    'no_match',
    'similar_not_same',
    'unknown',
    'unknown_no_accepted_mapping',
    'unmapped',
})
'''📜Statuses that require an explicit visible unknown-time label.'''

UNKNOWN_SAMPLE_TIME: str = 'unknown'
'''📜Serialized value for a page with no accepted video sample time.'''


def __local_name(tag: str) -> str:
    '''Return an XML element's local name.
    - 📌The atlas helper accepts namespaced and unnamespaced XHTML tags.
    '''
    return tag.rsplit('}', 1)[-1]


def __has_class(element: ET.Element, class_name: str) -> bool:
    '''Check one whitespace-delimited XHTML class token.'''
    return class_name in element.get('class', '').split()


def __visible_text(element: ET.Element) -> str:
    '''Collect text that is not hidden in non-rendered or folded markup.'''
    tag_name = __local_name(element.tag)
    style = element.get('style', '').replace(' ', '').lower()
    if (
        tag_name in {'details', 'script', 'style'}
        or 'hidden' in element.attrib
        or element.get('aria-hidden', '').lower() == 'true'
        or 'display:none' in style
        or 'visibility:hidden' in style
    ):
        return ''

    pieces = [element.text or '']
    for child in list(element):
        pieces.append(__visible_text(child))
        pieces.append(child.tail or '')
    return ''.join(pieces)


def __time_label(section: ET.Element, member_name: str) -> str:
    '''Derive the only permitted visible label from source-page metadata.
    - 🚩Accepted times remain sample points and never imply onset or duration.
    - ⚠️Missing or contradictory metadata fails instead of guessing unknown.
    '''
    page_id = section.get('id') or '<missing-page-id>'
    sample_time = section.get('data-sample-time')
    time_status = section.get('data-time-status')
    page_number = section.get('data-page-number')
    if not section.get('id'):
        raise ValueError(f'{member_name}: atlas page is missing its stable id')
    if not section.get('data-source-id'):
        raise ValueError(f'{member_name}#{page_id}: missing data-source-id')
    if not page_number or not page_number.isdigit() or int(page_number) < 1:
        raise ValueError(f'{member_name}#{page_id}: missing numeric data-page-number')
    if sample_time is None or time_status is None:
        raise ValueError(f'{member_name}#{page_id}: missing page time metadata')

    if time_status in KNOWN_TIME_STATUSES:
        if not TIMESTAMP_PATTERN.fullmatch(sample_time):
            raise ValueError(
                f'{member_name}#{page_id}: accepted sample time must be HH:MM:SS'
            )
        return (
            f'视频采样点：{sample_time} '
            '（不表示页面出现起点或持续区间）'
        )

    if time_status in UNKNOWN_TIME_STATUSES:
        if sample_time != UNKNOWN_SAMPLE_TIME:
            raise ValueError(
                f'{member_name}#{page_id}: unaccepted time status requires '
                'data-sample-time="unknown"'
            )
        return '视频采样时间：未知'

    raise ValueError(
        f'{member_name}#{page_id}: unsupported data-time-status {time_status!r}'
    )


def __already_visible(section: ET.Element, label: str, is_unknown: bool) -> bool:
    '''Check whether nearby visible text already states this exact time status.'''
    visible_text = ' '.join(__visible_text(section).split())
    if is_unknown:
        return re.search(r'视频采样时间\s*[：:]\s*未知', visible_text) is not None

    sample_time = label.split('：', 1)[1].split(' ', 1)[0]
    has_sample = sample_time in visible_text and '采样点' in visible_text
    has_boundary = any(
        phrase in visible_text
        for phrase in ('非起点', '不表示', '不代表首次出现', '非首次出现')
    )
    return has_sample and has_boundary


def label_atlas_document(content: bytes, member_name: str) -> tuple[bytes, dict[str, int]]:
    '''Add visible time labels where atlas-page metadata lacks one.
    - 🎯Keep known sample points distinct from unknown page/video mappings.
    - 📌Existing complete labels remain unchanged; repeated runs are idempotent.
    - 🚩Only the supplied atlas XHTML document is edited.
    '''
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f'{member_name}: invalid XHTML: {exc}') from exc

    sections = [
        element
        for element in root.iter()
        if __local_name(element.tag) == 'section'
        and __has_class(element, ATLAS_PAGE_CLASS)
        and (element.get('id') or '').startswith('atlas-page-')
    ]
    page_ids = [section.get('id') for section in sections]
    if len(page_ids) != len(set(page_ids)):
        raise ValueError(f'{member_name}: duplicate atlas page IDs')

    stats = {'pages': len(sections), 'known': 0, 'unknown': 0, 'labels_changed': 0}
    for section in sections:
        label = __time_label(section, member_name)
        is_unknown = label == '视频采样时间：未知'
        stats['unknown' if is_unknown else 'known'] += 1

        label_elements = [
            element
            for element in section.iter()
            if __local_name(element.tag) == 'p'
            and __has_class(element, TIME_LABEL_CLASS)
        ]
        if len(label_elements) > 1:
            raise ValueError(
                f'{member_name}#{section.get("id")}: multiple {TIME_LABEL_CLASS} paragraphs'
            )

        if label_elements:
            label_element = label_elements[0]
            if ' '.join(''.join(label_element.itertext()).split()) == label:
                continue
            label_element.clear()
            label_element.set('class', f'{TIME_LABEL_CLASS} small')
            label_element.text = label
            stats['labels_changed'] += 1
            continue

        if __already_visible(section, label, is_unknown):
            continue

        heading = next(
            (element for element in list(section) if __local_name(element.tag) == 'h2'),
            None,
        )
        if heading is None:
            raise ValueError(
                f'{member_name}#{section.get("id")}: atlas page has no h2 heading'
            )
        label_element = ET.Element(
            f'{{{XHTML_NAMESPACE}}}p',
            {'class': f'{TIME_LABEL_CLASS} small'},
        )
        label_element.text = label
        section.insert(list(section).index(heading) + 1, label_element)
        stats['labels_changed'] += 1

    if stats['labels_changed'] == 0:
        return content, stats

    ET.register_namespace('', XHTML_NAMESPACE)
    ET.register_namespace('epub', EPUB_NAMESPACE)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True), stats


def __atlas_report(epub_path: Path) -> dict[str, object]:
    '''Inspect visible atlas time labels without reading image payloads.
    - 📌The check mode validates labels only, not the whole EPUB's CRC.
    - 🚩Page metadata must explicitly classify accepted or unknown time.
    '''
    if not epub_path.is_file():
        raise FileNotFoundError(epub_path)

    totals = {
        'atlas_documents': 0,
        'pages': 0,
        'known': 0,
        'unknown': 0,
        'missing_visible_labels': 0,
    }
    with zipfile.ZipFile(epub_path, 'r') as source:
        names = source.namelist()
        if not names or names[0] != 'mimetype':
            raise ValueError('EPUB mimetype must be the first ZIP entry')
        if source.getinfo('mimetype').compress_type != zipfile.ZIP_STORED:
            raise ValueError('EPUB mimetype must be stored without compression')
        if len(names) != len(set(names)):
            raise ValueError('EPUB contains duplicate ZIP entry names')

        for member in source.infolist():
            if not member.filename.lower().endswith('.xhtml'):
                continue
            content = source.read(member)
            _, page_stats = label_atlas_document(content, member.filename)
            if page_stats['pages'] == 0:
                continue
            totals['atlas_documents'] += 1
            for key in ('pages', 'known', 'unknown', 'labels_changed'):
                target_key = 'missing_visible_labels' if key == 'labels_changed' else key
                totals[target_key] += page_stats[key]

    if totals['pages'] == 0:
        raise ValueError('EPUB contains no numbered atlas-page sections')
    totals['input'] = str(epub_path.resolve())
    totals['zip_crc_checked'] = False
    return totals


def check_epub(epub_path: Path) -> dict[str, object]:
    '''Fail unless every numbered atlas page visibly states its time status.'''
    report = __atlas_report(epub_path)
    report['status'] = 'pass' if report['missing_visible_labels'] == 0 else 'fail'
    return report


def __hash_stream(source: BinaryIO) -> str:
    '''Hash a ZIP member incrementally to keep memory bounded.'''
    digest = hashlib.sha256()
    for chunk in iter(lambda: source.read(BUFFER_SIZE), b''):
        digest.update(chunk)
    return digest.hexdigest()


def __validate_staged_epub(
    epub_path: Path,
    source_names: list[str],
    unchanged_hashes: dict[str, str],
) -> dict[str, object]:
    '''Verify staged ZIP CRCs, unchanged members, and visible atlas labels.'''
    totals = {'pages': 0, 'known': 0, 'unknown': 0}
    with zipfile.ZipFile(epub_path, 'r') as staged:
        names = staged.namelist()
        if names != source_names:
            raise ValueError('Staged EPUB changed ZIP entry order or names')
        if not names or names[0] != 'mimetype':
            raise ValueError('Staged EPUB mimetype is not the first ZIP entry')
        if staged.getinfo('mimetype').compress_type != zipfile.ZIP_STORED:
            raise ValueError('Staged EPUB compressed the mimetype entry')

        for member in staged.infolist():
            if member.filename.lower().endswith('.xhtml'):
                content = staged.read(member)
                updated, page_stats = label_atlas_document(content, member.filename)
                if updated != content:
                    raise ValueError(
                        f'Staged EPUB still needs atlas labels: {member.filename}'
                    )
                for key in ('pages', 'known', 'unknown'):
                    totals[key] += page_stats[key]
                member_hash = hashlib.sha256(content).hexdigest()
            else:
                with staged.open(member, 'r') as source:
                    member_hash = __hash_stream(source)
            expected_hash = unchanged_hashes.get(member.filename)
            if expected_hash is not None and member_hash != expected_hash:
                raise ValueError(f'Unmodified EPUB member changed: {member.filename}')

    if totals['pages'] == 0:
        raise ValueError('Staged EPUB contains no numbered atlas-page sections')
    return totals


def label_epub(input_path: Path, output_path: Path) -> dict[str, object]:
    '''Create a new EPUB with explicit per-page sample-time or unknown labels.
    - ⚠️Never overwrites the input or an existing output file.
    - 📌Promote only after ZIP, timestamp-label, and preserved-member checks pass.
    '''
    source_path = input_path.resolve()
    destination = output_path.resolve()
    if source_path == destination:
        raise ValueError('Output EPUB must be a different path from input')
    if destination.exists():
        raise FileExistsError(f'Refusing to overwrite existing output: {destination}')

    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f'.{destination.name}.', suffix='.tmp', dir=destination.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        unchanged_hashes: dict[str, str] = {}
        changed_documents = 0
        page_totals = {'pages': 0, 'known': 0, 'unknown': 0, 'labels_changed': 0}
        with zipfile.ZipFile(source_path, 'r') as source:
            source_names = source.namelist()
            if not source_names or source_names[0] != 'mimetype':
                raise ValueError('EPUB mimetype must be the first ZIP entry')
            if source.getinfo('mimetype').compress_type != zipfile.ZIP_STORED:
                raise ValueError('EPUB mimetype must be stored without compression')
            if len(source_names) != len(set(source_names)):
                raise ValueError('EPUB contains duplicate ZIP entry names')
            with zipfile.ZipFile(temporary_path, 'w') as target:
                target.comment = source.comment
                for member in source.infolist():
                    if member.is_dir():
                        target.writestr(member, b'')
                        unchanged_hashes[member.filename] = hashlib.sha256(b'').hexdigest()
                        continue
                    if member.filename.lower().endswith('.xhtml'):
                        content = source.read(member)
                        updated, page_stats = label_atlas_document(
                            content, member.filename,
                        )
                        for key in page_totals:
                            page_totals[key] += page_stats[key]
                        target.writestr(member, updated)
                        if updated == content:
                            unchanged_hashes[member.filename] = hashlib.sha256(content).hexdigest()
                        elif page_stats['pages']:
                            changed_documents += 1
                    else:
                        digest = hashlib.sha256()
                        with source.open(member, 'r') as source_stream:
                            with target.open(member, 'w') as target_stream:
                                for chunk in iter(
                                    lambda: source_stream.read(BUFFER_SIZE), b'',
                                ):
                                    digest.update(chunk)
                                    target_stream.write(chunk)
                        unchanged_hashes[member.filename] = digest.hexdigest()

        if page_totals['pages'] == 0:
            raise ValueError('EPUB contains no numbered atlas-page sections')
        staged_totals = __validate_staged_epub(
            temporary_path, source_names, unchanged_hashes,
        )
        if staged_totals['pages'] != page_totals['pages']:
            raise ValueError('Staged atlas page count changed')
        try:
            os.link(temporary_path, destination)
        except FileExistsError:
            raise
        except OSError as exc:
            raise OSError(
                'Cannot atomically promote the staged EPUB without overwriting; '
                'use a destination filesystem that supports hard links.'
            ) from exc
        temporary_path.unlink()
        report: dict[str, object] = {
            'status': 'pass',
            'input': str(source_path),
            'output': str(destination),
            'atlas_documents_changed': changed_documents,
            'pages': page_totals['pages'],
            'known_sample_points': page_totals['known'],
            'unknown_time_pages': page_totals['unknown'],
            'labels_added_or_updated': page_totals['labels_changed'],
            'post_write_validation': (
                'ZIP CRC, timestamp labels, and unchanged member hashes passed'
            ),
        }
        with destination.open('rb') as output_stream:
            report['sha256'] = __hash_stream(output_stream)
        return report
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def main() -> int:
    '''Run atlas timestamp labeling or validation from the command line.'''
    parser = argparse.ArgumentParser(
        description='Ensure each PPT atlas page visibly shows a time status.'
    )
    parser.add_argument('--input', required=True, type=Path, help='Source EPUB file')
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--output', type=Path, help='New EPUB output; refuses overwrite')
    modes.add_argument('--check', action='store_true', help='Validate visible labels only')
    args = parser.parse_args()

    try:
        if args.check:
            report = check_epub(args.input.resolve())
        else:
            report = label_epub(args.input, args.output)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report.get('status') == 'fail' else 0


if __name__ == '__main__':
    raise SystemExit(main())
