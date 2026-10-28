#!/usr/bin/env python3
'''Validate a packaged EPUB against its current Agent projection and atlas manifest.
- 🎯Catch stale figure IDs, missing assets, orphaned uncertainty notes and atlas/count drift.
- ⚠️This is a mechanical binding check, not an editorial, acoustic or reader acceptance test.
'''
from __future__ import annotations

import argparse  # Used for the read-only command-line interface.
import hashlib  # Used to verify packaged image bytes against projection hashes.
import json  # Used to read and write current projection reports.
import os  # Used to normalize local external asset paths across platforms.
import posixpath  # Used to normalize EPUB package paths.
import re  # Used for display-count labels and safe diagnostic patterns.
import sys  # Used for exit codes and standard output.
import zipfile  # Used to inspect EPUB members without extracting them.
from pathlib import Path, PureWindowsPath  # Used for input and report paths.
from typing import Any  # Used for parsed JSON projection records.
from urllib.parse import unquote, urlsplit  # Used to resolve local EPUB href/src references.
from xml.etree import ElementTree as ET  # Used to parse XHTML and atlas pages safely.

XHTML_NS: str = 'http://www.w3.org/1999/xhtml'
'''XHTML namespace used by EPUB body and atlas documents.'''
BODY_CHAPTER_PREFIX: str = 'OEBPS/chapter-'
'''Package prefix used to identify lesson XHTML files.'''
BODY_FIGURE_RECORD: str = 'body_figure'
'''Current Agent record kind for a figure placed beside lesson prose.'''
UNCERTAINTY_RECORD: str = 'uncertainty'
'''Current Agent record kind for an unresolved or source-question note.'''
SOURCE_PAGE_RECORD: str = 'source_page'
'''Page-atlas manifest record kind for a complete source slide page.'''
SUPPORTED_PROJECTION_RECORDS: set[str] = {
    BODY_FIGURE_RECORD,
    UNCERTAINTY_RECORD,
    SOURCE_PAGE_RECORD,
}
'''Root-level Agent record types understood by the package-binding checker.'''


def __sha256(data: bytes) -> str:
    '''Return the lowercase SHA-256 digest for package or image bytes.'''
    return hashlib.sha256(data).hexdigest()


def __oebps_path(value: str) -> str:
    '''Normalize a package-relative path under OEBPS and reject traversal.'''
    path = unquote(value).replace('\\', '/').lstrip('/')
    if path.startswith('OEBPS/'):
        normalized = posixpath.normpath(path)
    else:
        normalized = posixpath.normpath(posixpath.join('OEBPS', path))
    if normalized == 'OEBPS/..' or normalized.startswith('../') or not normalized.startswith('OEBPS/'):
        raise ValueError(f'Package path escapes OEBPS: {value!r}')
    return normalized


def __resolve_local_reference(document: str, value: str) -> tuple[str, str]:
    '''Resolve an XHTML-local href/src into a package member and fragment.'''
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith('//'):
        raise ValueError(f'Expected local package reference, found {value!r}')
    path = unquote(parsed.path).replace('\\', '/')
    target = document if not path else posixpath.normpath(posixpath.join(posixpath.dirname(document), path))
    if not target.startswith('OEBPS/') or target.startswith('OEBPS/../'):
        raise ValueError(f'Local reference escapes OEBPS: {value!r}')
    return target, unquote(parsed.fragment)


def __read_jsonl(path: Path) -> list[dict[str, Any]]:
    '''Read nonblank JSONL records without assuming a version-specific schema.'''
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f'Invalid JSONL at line {line_number}: {exc.msg}') from exc
        if not isinstance(record, dict):
            raise ValueError(f'JSONL line {line_number} is not an object')
        records.append(record)
    return records


def __manifest_file_paths(value: str, manifest_path: Path, external_asset_roots: list[Path]) -> list[Path] | None:
    '''Resolve absolute paths or relative paths under the manifest and declared source roots.'''
    raw = value.strip()
    if not raw:
        raise ValueError('Asset path is empty')
    windows_path = PureWindowsPath(raw)
    if windows_path.is_absolute():
        return [Path(raw)] if os.name == 'nt' else None
    candidate = Path(raw)
    if candidate.is_absolute():
        return [candidate]
    candidates = [manifest_path.parent / candidate, *(root / candidate for root in external_asset_roots)]
    unique: dict[str, Path] = {}
    for path in candidates:
        unique.setdefault(os.path.normcase(str(path.resolve(strict=False))), path)
    return list(unique.values())


def __manifest_path_identity(value: str, manifest_path: Path, external_asset_roots: list[Path]) -> str:
    '''Return a comparable identity for two manifest paths, including Windows paths.'''
    paths = __manifest_file_paths(value, manifest_path, external_asset_roots)
    if paths is None:
        return value.replace('/', '\\').casefold()
    if len(paths) == 1:
        return os.path.normcase(str(paths[0].resolve(strict=False)))
    return value.replace('\\', '/').casefold()


def __sha256_file(path: Path) -> str:
    '''Hash a local file in bounded memory.'''
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def __check_atlas_external_assets(
    page_rows: list[dict[str, Any]],
    manifest_path: Path,
    external_asset_roots: list[Path],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> dict[str, int]:
    '''Check external image paths when local, without confusing packaged and source hashes.'''
    declarations_checked = 0
    paths_unavailable = 0
    hashes_missing = 0
    hashes_by_path: dict[str, str] = {}
    fields = (
        ('pptx_path', 'pptx_sha256'),
        ('source_image_file', 'source_image_sha256'),
        ('uncropped_render_file', 'uncropped_render_sha256'),
        ('full_page_image_file', 'full_page_image_file_sha256'),
    )
    for row in page_rows:
        for path_field, digest_field in fields:
            raw_path = row.get(path_field)
            if raw_path is None or raw_path == '':
                continue
            if not isinstance(raw_path, str):
                errors.append({
                    'code': 'atlas_external_asset_invalid_path',
                    'member': manifest_path.name,
                    'detail': f'{path_field} is not a string',
                })
                continue
            expected_sha = row.get(digest_field)
            if (
                path_field == 'full_page_image_file'
                and not expected_sha
                and isinstance(row.get('uncropped_render_file'), str)
                and isinstance(row.get('uncropped_render_sha256'), str)
            ):
                try:
                    same_path = __manifest_path_identity(raw_path, manifest_path, external_asset_roots) == __manifest_path_identity(
                        row['uncropped_render_file'], manifest_path, external_asset_roots
                    )
                except (OSError, ValueError):
                    same_path = False
                if same_path:
                    expected_sha = row['uncropped_render_sha256']
            if not isinstance(expected_sha, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha):
                hashes_missing += 1
                warnings.append({
                    'code': 'atlas_external_asset_hash_missing',
                    'member': manifest_path.name,
                    'detail': f'{row.get("page_anchor", "")}: {path_field} has no valid {digest_field}',
                })
                continue
            try:
                paths = __manifest_file_paths(raw_path, manifest_path, external_asset_roots)
            except (OSError, ValueError) as exc:
                errors.append({
                    'code': 'atlas_external_asset_invalid_path',
                    'member': manifest_path.name,
                    'detail': f'{row.get("page_anchor", "")}: {path_field}: {exc}',
                })
                continue
            if paths is None:
                paths_unavailable += 1
                warnings.append({
                    'code': 'atlas_external_asset_not_local',
                    'member': manifest_path.name,
                    'detail': f'{row.get("page_anchor", "")}: {path_field} uses a Windows path on a non-Windows host',
                })
                continue
            existing_paths = [path for path in paths if path.is_file()]
            if not existing_paths:
                paths_unavailable += 1
                warnings.append({
                    'code': 'atlas_external_asset_unavailable',
                    'member': manifest_path.name,
                    'detail': f'{row.get("page_anchor", "")}: {path_field} is unavailable under the manifest directory and declared source roots ({Path(raw_path).name})',
                })
                continue
            actual_hashes: set[str] = set()
            for path in existing_paths:
                try:
                    identity = os.path.normcase(str(path.resolve(strict=True)))
                    actual_sha = hashes_by_path.get(identity)
                    if actual_sha is None:
                        actual_sha = __sha256_file(path)
                        hashes_by_path[identity] = actual_sha
                    actual_hashes.add(actual_sha)
                except OSError:
                    continue
            if not actual_hashes:
                paths_unavailable += 1
                warnings.append({
                    'code': 'atlas_external_asset_unavailable',
                    'member': manifest_path.name,
                    'detail': f'{row.get("page_anchor", "")}: {path_field} could not be read',
                })
                continue
            declarations_checked += 1
            if expected_sha.lower() not in actual_hashes:
                errors.append({
                    'code': 'atlas_external_asset_sha256_mismatch',
                    'member': manifest_path.name,
                    'detail': f'{row.get("page_anchor", "")}: {path_field} differs from {digest_field}',
                })
    return {
        'atlas_external_asset_declarations_checked': declarations_checked,
        'atlas_external_asset_files_hashed': len(hashes_by_path),
        'atlas_external_asset_paths_unavailable': paths_unavailable,
        'atlas_external_asset_hashes_missing': hashes_missing,
    }


def __has_supported_projection_contract(records: list[dict[str, Any]]) -> bool:
    '''Avoid interpreting nested or unrelated JSONL contracts as an empty current projection.'''
    return any(row.get('record_type') in SUPPORTED_PROJECTION_RECORDS for row in records)


def __parse_xml_documents(files: dict[str, bytes], errors: list[dict[str, str]]) -> dict[str, ET.Element]:
    '''Parse package XML documents and report malformed members by package path.'''
    documents: dict[str, ET.Element] = {}
    for name, data in files.items():
        if not name.lower().endswith(('.xhtml', '.xml', '.opf', '.ncx', '.svg')):
            continue
        try:
            documents[name] = ET.fromstring(data)
        except ET.ParseError as exc:
            errors.append({'code': 'xml_parse_error', 'member': name, 'detail': str(exc)})
    return documents


def __ids_by_document(documents: dict[str, ET.Element]) -> dict[str, dict[str, list[ET.Element]]]:
    '''Index element IDs per XHTML/XML member without mixing volume-local IDs.'''
    result: dict[str, dict[str, list[ET.Element]]] = {}
    for name, root in documents.items():
        ids: dict[str, list[ET.Element]] = {}
        for node in root.iter():
            node_id = node.attrib.get('id')
            if node_id:
                ids.setdefault(node_id, []).append(node)
        result[name] = ids
    return result


def __element_text(node: ET.Element) -> str:
    '''Join visible text nodes for a nonempty uncertainty-target check.'''
    return ''.join(node.itertext()).strip()


def __check_body_figures(
    files: dict[str, bytes],
    documents: dict[str, ET.Element],
    ids_by_document: dict[str, dict[str, list[ET.Element]]],
    records: list[dict[str, Any]],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> dict[str, int]:
    '''Reconcile current body-figure records to lesson XHTML IDs and image resources.'''
    sidecar_rows = [row for row in records if row.get('record_type') == BODY_FIGURE_RECORD]
    actual_by_key: dict[tuple[str, str], ET.Element] = {}
    for document, root in documents.items():
        if not document.startswith(BODY_CHAPTER_PREFIX) or not document.endswith('.xhtml'):
            continue
        for node in root.iter():
            if node.tag != f'{{{XHTML_NS}}}figure':
                continue
            images = [child for child in node.iter() if child.tag == f'{{{XHTML_NS}}}img']
            if not images:
                continue
            figure_id = node.attrib.get('id')
            if not figure_id:
                errors.append({'code': 'body_figure_missing_id', 'member': document, 'detail': 'Figure with images has no id'})
                continue
            key = (document, figure_id)
            if key in actual_by_key:
                errors.append({'code': 'duplicate_xhtml_figure_id', 'member': document, 'detail': figure_id})
            actual_by_key[key] = node

    expected_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sidecar_rows:
        figure_id = row.get('figure_id')
        chapter_href = row.get('chapter_href') or row.get('chapter_path')
        if not isinstance(figure_id, str) or not figure_id:
            errors.append({'code': 'body_figure_missing_id', 'member': 'agent-readable-current.jsonl', 'detail': str(row.get('source_id', ''))})
            continue
        if not isinstance(chapter_href, str) or not chapter_href:
            errors.append({'code': 'body_figure_missing_chapter', 'member': 'agent-readable-current.jsonl', 'detail': figure_id})
            continue
        try:
            document = __oebps_path(chapter_href)
        except ValueError as exc:
            errors.append({'code': 'body_figure_invalid_chapter', 'member': 'agent-readable-current.jsonl', 'detail': f'{figure_id}: {exc}'})
            continue
        key = (document, figure_id)
        if key in expected_by_key:
            errors.append({'code': 'duplicate_agent_figure_id', 'member': document, 'detail': figure_id})
        expected_by_key[key] = row
        node = actual_by_key.get(key)
        if node is None:
            errors.append({'code': 'agent_figure_missing_in_xhtml', 'member': document, 'detail': figure_id})
            continue
        source_id = row.get('source_id')
        xhtml_source_id = node.attrib.get('data-source-id')
        if xhtml_source_id and source_id and xhtml_source_id != source_id:
            errors.append({'code': 'body_figure_source_id_mismatch', 'member': document, 'detail': figure_id})
        source_unit_id = row.get('source_unit_id')
        xhtml_source_unit_id = node.attrib.get('data-source-unit-id')
        if xhtml_source_unit_id and source_unit_id and xhtml_source_unit_id != source_unit_id:
            errors.append({'code': 'body_figure_source_unit_mismatch', 'member': document, 'detail': figure_id})

        anchor_id = row.get('anchor_id') or row.get('paragraph_anchor')
        if isinstance(anchor_id, str) and anchor_id:
            if '#' in anchor_id or '/' in anchor_id or anchor_id.lower().endswith('.xhtml'):
                try:
                    anchor_document, anchor_fragment = __resolve_local_reference(document, anchor_id)
                except ValueError:
                    anchor_document, anchor_fragment = document, anchor_id.lstrip('#')
            else:
                anchor_document, anchor_fragment = document, anchor_id
            if not anchor_fragment or anchor_document not in documents or anchor_fragment not in ids_by_document.get(anchor_document, {}):
                errors.append({'code': 'body_figure_anchor_not_resolved', 'member': document, 'detail': f'{figure_id}: {anchor_id}'})

        expected_images = row.get('images')
        if not isinstance(expected_images, list) or not expected_images:
            errors.append({'code': 'agent_figure_has_no_images', 'member': document, 'detail': figure_id})
            continue
        actual_images = [child for child in node.iter() if child.tag == f'{{{XHTML_NS}}}img']
        if len(actual_images) != len(expected_images):
            errors.append({'code': 'body_figure_image_count_mismatch', 'member': document, 'detail': f'{figure_id}: XHTML={len(actual_images)} Agent={len(expected_images)}'})
        for image_index, (actual_image, expected_image) in enumerate(zip(actual_images, expected_images), start=1):
            src = actual_image.attrib.get('src', '')
            try:
                target, fragment = __resolve_local_reference(document, src)
            except ValueError as exc:
                errors.append({'code': 'body_figure_image_invalid_src', 'member': document, 'detail': f'{figure_id} image {image_index}: {exc}'})
                continue
            expected_href = expected_image.get('image_href')
            if not isinstance(expected_href, str):
                errors.append({'code': 'agent_figure_image_missing_href', 'member': document, 'detail': f'{figure_id} image {image_index}'})
                continue
            try:
                expected_target = __oebps_path(expected_href)
            except ValueError as exc:
                errors.append({'code': 'agent_figure_image_invalid_href', 'member': document, 'detail': f'{figure_id}: {exc}'})
                continue
            if target != expected_target or fragment:
                errors.append({'code': 'body_figure_image_href_mismatch', 'member': document, 'detail': f'{figure_id} image {image_index}: XHTML={target} Agent={expected_target}'})
            if target not in files:
                errors.append({'code': 'body_figure_image_resource_missing', 'member': document, 'detail': f'{figure_id}: {target}'})
                continue
            expected_sha = expected_image.get('image_sha256')
            if not isinstance(expected_sha, str) or not expected_sha:
                errors.append({'code': 'agent_figure_image_missing_sha256', 'member': document, 'detail': f'{figure_id} image {image_index}'})
            elif __sha256(files[target]) != expected_sha:
                errors.append({'code': 'body_figure_image_sha256_mismatch', 'member': document, 'detail': f'{figure_id} image {image_index}: {target}'})
            expected_alt = expected_image.get('alt_text')
            if isinstance(expected_alt, str) and actual_image.attrib.get('alt', '') != expected_alt:
                errors.append({'code': 'body_figure_alt_text_mismatch', 'member': document, 'detail': f'{figure_id} image {image_index}'})

    for key in actual_by_key:
        if key not in expected_by_key:
            errors.append({'code': 'xhtml_body_figure_missing_agent_record', 'member': key[0], 'detail': key[1]})
    return {'agent_body_figure_records': len(sidecar_rows), 'xhtml_body_figure_nodes': len(actual_by_key)}


def __check_uncertainties(
    documents: dict[str, ET.Element],
    ids_by_document: dict[str, dict[str, list[ET.Element]]],
    records: list[dict[str, Any]],
    errors: list[dict[str, str]],
) -> dict[str, int]:
    '''Check each current uncertainty locator, appendix section, and visible count label.'''
    uncertainty_rows = [row for row in records if row.get('record_type') == UNCERTAINTY_RECORD]
    locators_by_document: dict[str, set[str]] = {}
    seen_uncertainty_ids: set[str] = set()
    seen_uncertainty_locators: set[tuple[str, str]] = set()
    for row in uncertainty_rows:
        locator = row.get('source_locator')
        uncertainty_id = row.get('uncertainty_id', '')
        if isinstance(uncertainty_id, str) and uncertainty_id:
            if uncertainty_id in seen_uncertainty_ids:
                errors.append({'code': 'duplicate_uncertainty_id', 'member': 'agent-readable-current.jsonl', 'detail': uncertainty_id})
            seen_uncertainty_ids.add(uncertainty_id)
        if not isinstance(locator, str) or '#' not in locator:
            errors.append({'code': 'uncertainty_missing_source_locator', 'member': 'agent-readable-current.jsonl', 'detail': str(uncertainty_id)})
            continue
        document_part, fragment = locator.split('#', 1)
        if not fragment:
            errors.append({'code': 'uncertainty_missing_fragment', 'member': 'agent-readable-current.jsonl', 'detail': str(uncertainty_id)})
            continue
        try:
            document = __oebps_path(document_part)
        except ValueError as exc:
            errors.append({'code': 'uncertainty_invalid_source_locator', 'member': 'agent-readable-current.jsonl', 'detail': f'{uncertainty_id}: {exc}'})
            continue
        fragment = unquote(fragment)
        if document not in documents:
            errors.append({'code': 'uncertainty_target_document_missing', 'member': document, 'detail': str(uncertainty_id)})
            continue
        locator_key = (document, fragment)
        if locator_key in seen_uncertainty_locators:
            errors.append({'code': 'duplicate_uncertainty_locator', 'member': document, 'detail': fragment})
        seen_uncertainty_locators.add(locator_key)
        id_nodes = ids_by_document.get(document, {}).get(fragment, [])
        if len(id_nodes) != 1:
            errors.append({'code': 'uncertainty_target_count_mismatch', 'member': document, 'detail': f'{fragment}: {len(id_nodes)} targets'})
            continue
        if not __element_text(id_nodes[0]):
            errors.append({'code': 'uncertainty_target_empty', 'member': document, 'detail': fragment})
        if not isinstance(row.get('text'), str) or not row['text'].strip():
            errors.append({'code': 'uncertainty_record_empty', 'member': 'agent-readable-current.jsonl', 'detail': str(uncertainty_id)})
        locators_by_document.setdefault(document, set()).add(fragment)

    appendix_sections: dict[str, set[str]] = {}
    for document, root in documents.items():
        for node in root.iter():
            if node.tag == f'{{{XHTML_NS}}}section' and 'uncertainty-entry' in node.attrib.get('class', '').split():
                section_id = node.attrib.get('id')
                if not section_id:
                    errors.append({'code': 'uncertainty_section_missing_id', 'member': document, 'detail': ''})
                else:
                    appendix_sections.setdefault(document, set()).add(section_id)
    for document, section_ids in appendix_sections.items():
        projected_ids = locators_by_document.get(document, set())
        if section_ids != projected_ids:
            errors.append({'code': 'uncertainty_appendix_projection_mismatch', 'member': document, 'detail': f'XHTML sections={len(section_ids)} Agent locators={len(projected_ids)}'})
        labels = [int(match) for match in re.findall(r'(\d+)\s*项未决记录', __element_text(documents[document]))]
        for label in labels:
            if label != len(section_ids):
                errors.append({'code': 'uncertainty_appendix_label_mismatch', 'member': document, 'detail': f'label={label} sections={len(section_ids)}'})
    return {
        'agent_uncertainty_records': len(uncertainty_rows),
        'appendix_uncertainty_sections': sum(len(values) for values in appendix_sections.values()),
        'appendix_documents': len(appendix_sections),
    }


def __check_atlas(
    files: dict[str, bytes],
    documents: dict[str, ET.Element],
    manifest_path: Path | None,
    external_asset_roots: list[Path],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> dict[str, int | None]:
    '''Check optional page-atlas page anchors and packaged display-image hashes.'''
    if manifest_path is None:
        warnings.append({'code': 'page_atlas_manifest_not_supplied', 'member': '', 'detail': 'Complete atlas page coverage was not checked'})
        return {'atlas_pages_in_manifest': 0, 'atlas_pages_in_xhtml': 0}
    try:
        manifest_rows = __read_jsonl(manifest_path)
    except (OSError, ValueError) as exc:
        errors.append({'code': 'page_atlas_manifest_unreadable', 'member': manifest_path.name, 'detail': str(exc)})
        return {'atlas_pages_in_manifest': 0, 'atlas_pages_in_xhtml': 0}
    page_rows = [row for row in manifest_rows if row.get('record_type') == SOURCE_PAGE_RECORD]
    external_asset_counts = __check_atlas_external_assets(page_rows, manifest_path, external_asset_roots, errors, warnings)
    expected_by_document: dict[str, set[str]] = {}
    for row in page_rows:
        try:
            document = __oebps_path(str(row.get('atlas_document', '')))
        except ValueError as exc:
            errors.append({'code': 'atlas_page_invalid_document', 'member': manifest_path.name, 'detail': str(exc)})
            continue
        anchor = row.get('page_anchor')
        if not isinstance(anchor, str) or not anchor:
            errors.append({'code': 'atlas_page_missing_anchor', 'member': document, 'detail': str(row.get('page_number', ''))})
            continue
        expected_by_document.setdefault(document, set()).add(anchor)
        root = documents.get(document)
        if root is None:
            errors.append({'code': 'atlas_page_document_missing', 'member': document, 'detail': anchor})
            continue
        matches = [node for node in root.iter() if node.attrib.get('id') == anchor]
        if len(matches) != 1:
            errors.append({'code': 'atlas_page_anchor_count_mismatch', 'member': document, 'detail': f'{anchor}: {len(matches)} targets'})
            continue
        section = matches[0]
        if section.tag != f'{{{XHTML_NS}}}section' or 'atlas-page' not in section.attrib.get('class', '').split():
            errors.append({'code': 'atlas_page_target_wrong_element', 'member': document, 'detail': anchor})
        source_id = row.get('source_id')
        if source_id and section.attrib.get('data-source-id') != source_id:
            errors.append({'code': 'atlas_page_source_id_mismatch', 'member': document, 'detail': anchor})
        page_number = row.get('page_number')
        if page_number is not None and str(section.attrib.get('data-page-number', '')) != str(page_number):
            errors.append({'code': 'atlas_page_number_mismatch', 'member': document, 'detail': anchor})
        image_href = row.get('full_page_image_epub_href') or row.get('display_derivative_file_epub_href')
        if not isinstance(image_href, str) or not image_href:
            errors.append({'code': 'atlas_page_missing_display_href', 'member': document, 'detail': anchor})
            continue
        try:
            expected_image = __oebps_path(image_href)
        except ValueError as exc:
            errors.append({'code': 'atlas_page_invalid_image_href', 'member': document, 'detail': f'{anchor}: {exc}'})
            continue
        actual_images = []
        for image in section.iter():
            if image.tag == f'{{{XHTML_NS}}}img' and image.attrib.get('src'):
                try:
                    actual, fragment = __resolve_local_reference(document, image.attrib['src'])
                    if not fragment:
                        actual_images.append(actual)
                except ValueError as exc:
                    errors.append({'code': 'atlas_page_invalid_image_src', 'member': document, 'detail': f'{anchor}: {exc}'})
        if expected_image not in actual_images:
            errors.append({'code': 'atlas_page_display_image_mismatch', 'member': document, 'detail': f'{anchor}: expected {expected_image}'})
        if expected_image not in files:
            errors.append({'code': 'atlas_page_display_image_missing', 'member': document, 'detail': f'{anchor}: {expected_image}'})
        else:
            expected_sha = row.get('full_page_image_sha256')
            if not isinstance(expected_sha, str) or __sha256(files[expected_image]) != expected_sha:
                errors.append({'code': 'atlas_page_display_image_sha256_mismatch', 'member': document, 'detail': f'{anchor}: {expected_image}'})
    actual_by_document: dict[str, set[str]] = {}
    for document, root in documents.items():
        for node in root.iter():
            if node.tag == f'{{{XHTML_NS}}}section' and 'atlas-page' in node.attrib.get('class', '').split():
                if node.attrib.get('id'):
                    actual_by_document.setdefault(document, set()).add(node.attrib['id'])
    for document, expected_ids in expected_by_document.items():
        actual_ids = actual_by_document.get(document, set())
        if expected_ids != actual_ids:
            errors.append({'code': 'atlas_manifest_page_set_mismatch', 'member': document, 'detail': f'manifest={len(expected_ids)} xhtml={len(actual_ids)}'})
    manifest_document_pages = sum(len(actual_by_document.get(document, set())) for document in expected_by_document)
    return {
        'atlas_pages_in_manifest': len(page_rows),
        'atlas_pages_in_xhtml': manifest_document_pages,
        **external_asset_counts,
    }


def validate_epub_projection(
    epub_path: Path,
    agent_jsonl_path: Path,
    page_atlas_manifest_path: Path | None = None,
    external_asset_roots: list[Path] | None = None,
) -> dict[str, Any]:
    '''Validate current Agent, figure, uncertainty and optional atlas package bindings.'''
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    records: list[dict[str, Any]] = []
    try:
        records = __read_jsonl(agent_jsonl_path)
    except (OSError, ValueError) as exc:
        errors.append({'code': 'agent_projection_unreadable', 'member': agent_jsonl_path.name, 'detail': str(exc)})
    supported_projection_contract = __has_supported_projection_contract(records)
    projection_schema_names = sorted({
        str(row['projection_schema'])
        for row in records
        if isinstance(row.get('projection_schema'), str) and row['projection_schema']
    })
    if not supported_projection_contract:
        warnings.append({
            'code': 'agent_projection_schema_not_supported',
            'member': agent_jsonl_path.name,
            'detail': 'This checker requires root-level record_type values body_figure, uncertainty, or source_page; use a schema-specific adapter for nested/other exports.',
        })
    files: dict[str, bytes] = {}
    epub_sha256 = ''
    try:
        digest = hashlib.sha256()
        with epub_path.open('rb') as raw_epub:
            for chunk in iter(lambda: raw_epub.read(1024 * 1024), b''):
                digest.update(chunk)
        epub_sha256 = digest.hexdigest()
        with zipfile.ZipFile(epub_path) as archive:
            bad_member = archive.testzip()
            if bad_member:
                errors.append({'code': 'epub_crc_error', 'member': bad_member, 'detail': ''})
            infos = archive.infolist()
            if not infos or infos[0].filename != 'mimetype' or infos[0].compress_type != zipfile.ZIP_STORED:
                errors.append({'code': 'epub_mimetype_order_or_compression', 'member': 'mimetype', 'detail': ''})
            elif archive.read('mimetype') != b'application/epub+zip':
                errors.append({'code': 'epub_mimetype_payload', 'member': 'mimetype', 'detail': ''})
            files = {name: archive.read(name) for name in archive.namelist()}
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        errors.append({'code': 'epub_unreadable', 'member': epub_path.name, 'detail': str(exc)})
    documents = __parse_xml_documents(files, errors)
    ids = __ids_by_document(documents)
    if supported_projection_contract:
        figure_counts = __check_body_figures(files, documents, ids, records, errors, warnings)
        uncertainty_counts = __check_uncertainties(documents, ids, records, errors)
    else:
        figure_counts = {'agent_body_figure_records': 0, 'xhtml_body_figure_nodes': 0}
        uncertainty_counts = {'agent_uncertainty_records': 0, 'appendix_uncertainty_sections': 0, 'appendix_documents': 0}
    atlas_counts = __check_atlas(files, documents, page_atlas_manifest_path, external_asset_roots or [], errors, warnings)
    return {
        'schema_version': 'epub-projection-binding/1',
        'status': 'FAIL' if errors else ('NOT_APPLICABLE_SCHEMA' if not supported_projection_contract else ('PASS_WITH_WARNINGS' if warnings else 'PASS')),
        'validator_sha256': __sha256(Path(__file__).read_bytes()),
        'agent_projection_schema_names': projection_schema_names,
        'agent_projection_contract_supported': supported_projection_contract,
        'epub_sha256': epub_sha256,
        'agent_projection_sha256': hashlib.sha256(agent_jsonl_path.read_bytes()).hexdigest() if agent_jsonl_path.is_file() else None,
        'page_atlas_manifest_sha256': hashlib.sha256(page_atlas_manifest_path.read_bytes()).hexdigest() if page_atlas_manifest_path and page_atlas_manifest_path.is_file() else None,
        'checks': {
            'zip_crc_and_mimetype': not any(item['code'] in {'epub_crc_error', 'epub_mimetype_order_or_compression', 'epub_mimetype_payload', 'epub_unreadable'} for item in errors),
            'body_figure_projection': None if not supported_projection_contract else not any(item['code'].startswith(('body_figure_', 'agent_figure_', 'xhtml_body_figure_', 'duplicate_agent_figure_id', 'duplicate_xhtml_figure_id')) for item in errors),
            'uncertainty_targets_and_counts': None if not supported_projection_contract else not any(item['code'].startswith(('uncertainty_',)) for item in errors),
            'page_atlas_bindings': page_atlas_manifest_path is not None and not any(item['code'].startswith(('atlas_',)) for item in errors),
        },
        'counts': {**figure_counts, **uncertainty_counts, **atlas_counts, 'parsed_xml_documents': len(documents)},
        'errors': errors,
        'warnings': warnings,
        'not_checked': [
            'Semantic accuracy, completeness of cases or preservation of teaching intent.',
            'Audio truth, video-to-speech synchronization or whether a sampled frame is useful to a human reader.',
            'Target-reader behavior, screen-width usability, rights clearance or follow-along success.',
            'For NOT_APPLICABLE_SCHEMA, Agent/body/uncertainty cross-bindings; the report did not attempt to interpret that export contract.',
        ],
    }


def main(argv: list[str] | None = None) -> int:
    '''Run read-only projection checks and emit a JSON report or concise summary.'''
    parser = argparse.ArgumentParser(description='Validate EPUB body figures, uncertainty notes and optional atlas bindings against current Agent exports.')
    parser.add_argument('--epub', type=Path, required=True, help='The exact packaged EPUB candidate.')
    parser.add_argument('--agent-jsonl', type=Path, required=True, help='Current-edition Agent-readable JSONL projection.')
    parser.add_argument('--page-atlas-manifest', type=Path, help='Optional current page-atlas manifest JSONL.')
    parser.add_argument('--external-asset-root', type=Path, action='append', default=[], help='Optional base for relative source-image paths in the page-atlas manifest; may be repeated.')
    parser.add_argument('--report', type=Path, help='Optional path for the JSON result; otherwise print to stdout.')
    args = parser.parse_args(argv)
    result = validate_epub_projection(args.epub, args.agent_jsonl, args.page_atlas_manifest, args.external_asset_root)
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized, encoding='utf-8')
    else:
        print(serialized, end='')
    return 0 if result['status'] != 'FAIL' else 1


if __name__ == '__main__':
    raise SystemExit(main())
