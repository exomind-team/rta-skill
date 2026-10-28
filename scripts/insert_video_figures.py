#!/usr/bin/env python3
"""Insert source-mapped local video frames as reflowable EPUB figure groups."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import posixpath
import re
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET


XHTML = "http://www.w3.org/1999/xhtml"
OPF = "http://www.idpf.org/2007/opf"
CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
SAFE_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def q(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def has_class(node: ET.Element, class_name: str) -> bool:
    return class_name in node.attrib.get("class", "").split()


def is_disclosure_for_anchor(node: ET.Element, anchor_id: str, source_unit_id: str | None = None) -> bool:
    """Recognize only the disclosure belonging to this paragraph.

    EPUBs may place an original-text disclosure either before or after the
    proofread paragraph. In the original-first layout, the next sibling may be
    the *next* paragraph's disclosure; never step over it when placing a figure.
    """
    if node.tag != q(XHTML, "details"):
        return False
    anchor_ids = {anchor_id}
    if anchor_id.startswith("edited-"):
        anchor_ids.add(anchor_id[len("edited-"):])
    if node.attrib.get("id") in anchor_ids:
        return True
    for key in ("data-anchor-id", "data-source-anchor-id"):
        if node.attrib.get(key) in anchor_ids:
            return True
    return bool(source_unit_id and node.attrib.get("data-source-unit-id") == source_unit_id)


def serialize(root: ET.Element, default_namespace: str) -> bytes:
    ET.register_namespace("", default_namespace)
    ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
    ET.register_namespace("epub", "http://www.idpf.org/2007/ops")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def timestamp_label(frame: dict) -> str:
    value = frame.get("timestamp")
    if isinstance(value, str) and value:
        return value
    seconds = frame.get("timestamp_seconds")
    if not isinstance(seconds, (int, float)) or seconds < 0:
        raise ValueError("Every frame needs timestamp or timestamp_seconds")
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, seconds_part = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}"


def package_path(files: dict[str, bytes]) -> str:
    root = ET.fromstring(files["META-INF/container.xml"])
    node = root.find(f"{q(CONTAINER, 'rootfiles')}/{q(CONTAINER, 'rootfile')}")
    if node is None or not node.attrib.get("full-path"):
        raise ValueError("EPUB container has no package path")
    return node.attrib["full-path"]


def find_css(files: dict[str, bytes], package: ET.Element, package_dir: str) -> str:
    manifest = package.find(q(OPF, "manifest"))
    if manifest is None:
        raise ValueError("EPUB package has no manifest")
    for item in manifest:
        if item.attrib.get("media-type") == "text/css":
            return posixpath.normpath(posixpath.join(package_dir, item.attrib["href"]))
    raise ValueError("EPUB has no CSS stylesheet to style the inserted figures")


def source_id(figure: dict) -> str:
    return figure.get("source_id") or f"video-frame-source-{figure['chapter_id']}"


def validate_local_references(files: dict[str, bytes], package: ET.Element, package_dir: str) -> int:
    manifest = package.find(q(OPF, "manifest"))
    if manifest is None:
        raise ValueError("EPUB package has no manifest")
    for item in manifest:
        href = item.attrib.get("href")
        if not href:
            continue
        parsed = urllib.parse.urlsplit(href)
        if parsed.scheme or parsed.netloc:
            continue
        target = posixpath.normpath(posixpath.join(package_dir, urllib.parse.unquote(parsed.path)))
        if target not in files:
            raise ValueError(f"OPF manifest refers to missing file: {href}")

    documents = {
        path: ET.fromstring(data)
        for path, data in files.items()
        if path.endswith((".xhtml", ".html", ".htm"))
    }
    checked = 0
    for path, document in documents.items():
        for node in document.iter():
            for attribute in ("href", "src"):
                value = node.attrib.get(attribute)
                if not value:
                    continue
                parsed = urllib.parse.urlsplit(value)
                if parsed.scheme or parsed.netloc or value.startswith("//"):
                    continue
                target = path if not parsed.path else posixpath.normpath(
                    posixpath.join(posixpath.dirname(path), urllib.parse.unquote(parsed.path))
                )
                if target not in files:
                    raise ValueError(f"XHTML reference in {path} points to missing file: {value}")
                if parsed.fragment and target in documents:
                    fragment = urllib.parse.unquote(parsed.fragment)
                    if not any(element.attrib.get("id") == fragment for element in documents[target].iter()):
                        raise ValueError(f"XHTML reference in {path} points to missing fragment: {value}")
                checked += 1
    return checked


def insert_figures(input_epub: Path, output_epub: Path, mapping_path: Path) -> dict:
    input_epub = input_epub.resolve()
    output_epub = output_epub.resolve()
    if input_epub == output_epub:
        raise ValueError("Input and output EPUB paths must differ")
    if output_epub.exists():
        raise FileExistsError(f"Output already exists: {output_epub}")
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    figures = mapping.get("figures") if isinstance(mapping, dict) else None
    if not isinstance(figures, list) or not figures:
        raise ValueError("Mapping JSON must contain a non-empty figures array")
    page_time_matches = mapping.get("page_time_matches", [])
    if not isinstance(page_time_matches, list):
        raise ValueError("page_time_matches must be a JSON array")

    with zipfile.ZipFile(input_epub) as source:
        if source.testzip() is not None:
            raise ValueError("Input EPUB failed ZIP integrity check")
        original_infos = source.infolist()
        files = {info.filename: source.read(info.filename) for info in original_infos}

    opf_path = package_path(files)
    package = ET.fromstring(files[opf_path])
    manifest = package.find(q(OPF, "manifest"))
    if manifest is None:
        raise ValueError("EPUB package has no manifest")
    package_dir = posixpath.dirname(opf_path)
    source_path = f"{package_dir}/sources.xhtml"
    source_doc = ET.fromstring(files[source_path]) if source_path in files else None
    css_path = find_css(files, package, package_dir)
    existing_ids = {item.attrib.get("id") for item in manifest}
    existing_hrefs = {posixpath.normpath(posixpath.join(package_dir, item.attrib.get("href", ""))) for item in manifest}
    used_figure_ids: set[str] = set()
    source_records: dict[str, dict] = {}
    inserted: list[dict] = []
    documents: dict[str, ET.Element] = {}
    parents_by_path: dict[str, dict[ET.Element, ET.Element]] = {}
    atlas_documents: dict[str, ET.Element] = {}
    page_time_updates: list[dict] = []

    for figure in figures:
        if not isinstance(figure, dict):
            raise ValueError("Figure mappings must be JSON objects")
        figure_id = figure.get("figure_id")
        chapter_id = figure.get("chapter_id")
        anchor_id = figure.get("anchor_id")
        if not all(isinstance(value, str) and SAFE_ID.fullmatch(value) for value in (figure_id, chapter_id, anchor_id)):
            raise ValueError(f"Invalid figure/chapter/anchor ID: {figure_id!r}, {chapter_id!r}, {anchor_id!r}")
        if not SAFE_ID.fullmatch(source_id(figure)):
            raise ValueError(f"Invalid source appendix ID: {source_id(figure)!r}")
        if figure_id in used_figure_ids:
            raise ValueError(f"Duplicate figure_id: {figure_id}")
        used_figure_ids.add(figure_id)
        chapter_path = figure.get("chapter_path") or f"{package_dir}/chapter-{int(chapter_id[-3:]):03}.xhtml"
        if chapter_path not in files:
            raise FileNotFoundError(f"Chapter document not found in EPUB: {chapter_path}")
        if chapter_path not in documents:
            documents[chapter_path] = ET.fromstring(files[chapter_path])
            parents_by_path[chapter_path] = {
                child: parent for parent in documents[chapter_path].iter() for child in list(parent)
            }
        document = documents[chapter_path]
        parent_map = parents_by_path[chapter_path]
        if any(node.attrib.get("id") == figure_id for node in document.iter()):
            raise ValueError(f"Figure ID already exists in {chapter_path}: {figure_id}")
        anchors = [node for node in document.iter() if node.attrib.get("id") == anchor_id]
        if len(anchors) != 1:
            raise ValueError(f"Expected one anchor {anchor_id!r} in {chapter_path}; found {len(anchors)}")
        anchor = anchors[0]
        parent = parent_map.get(anchor)
        if parent is None:
            raise ValueError(f"Anchor {anchor_id!r} has no parent element")
        siblings = list(parent)
        position = siblings.index(anchor)
        source_unit_id = figure.get("source_unit_id")
        while position + 1 < len(siblings) and is_disclosure_for_anchor(
            siblings[position + 1], anchor_id, source_unit_id if isinstance(source_unit_id, str) else None
        ):
            position += 1

        frame_rows = figure.get("frames")
        if not isinstance(frame_rows, list) or not frame_rows:
            raise ValueError(f"Figure {figure_id} needs at least one frame")
        figure_node = ET.Element(q(XHTML, "figure"), {"id": figure_id, "class": "video-frame-group"})
        source_href = None
        src_path = figure.get("source_video")
        existing_source_video = figure.get("existing_source_video")
        if isinstance(existing_source_video, str) and existing_source_video:
            if source_doc is None:
                raise ValueError("Reusing a video source requires sources.xhtml in the EPUB")
            existing_source_section_id = figure.get("existing_source_section_id")
            if not isinstance(existing_source_section_id, str) or not existing_source_section_id:
                raise ValueError("Reusing an existing video path requires its containing existing_source_section_id")
            section_matches = [
                node for node in source_doc.iter(q(XHTML, "section"))
                if node.attrib.get("id") == existing_source_section_id
            ]
            if len(section_matches) != 1:
                raise ValueError(
                    f"Expected one existing source section {existing_source_section_id!r}; found {len(section_matches)}"
                )
            source_section = section_matches[0]
            existing_source_id = figure.get("existing_source_id")
            if existing_source_id:
                matches = [
                    node for node in source_doc.iter()
                    if node.attrib.get("id") == existing_source_id
                ]
                if len(matches) != 1:
                    raise ValueError(f"Expected one existing video-source ID {existing_source_id!r}; found {len(matches)}")
                source_node = matches[0]
                if source_node not in source_section.iter():
                    raise ValueError(
                        f"Existing video-source ID {existing_source_id!r} is outside section {existing_source_section_id!r}"
                    )
                if existing_source_video not in "".join(source_node.itertext()):
                    raise ValueError(f"Existing video-source ID {existing_source_id!r} does not contain the requested path")
                sid = existing_source_id
                if source_id(figure) != sid:
                    raise ValueError(f"source_id {source_id(figure)!r} must match existing_source_id {sid!r}")
            else:
                matches = [
                    node for node in source_section.iter(q(XHTML, "p"))
                    if existing_source_video in "".join(node.itertext())
                ]
                if len(matches) != 1:
                    raise ValueError(
                        f"Expected one video-source paragraph for {existing_source_video!r} "
                        f"inside section {existing_source_section_id!r}; found {len(matches)}"
                    )
                source_node = matches[0]
                sid = source_id(figure)
            if any(node is not source_node and node.attrib.get("id") == sid for node in source_doc.iter()):
                raise ValueError(f"Source appendix ID already exists: {sid}")
            if source_node.attrib.get("id") not in {None, sid}:
                raise ValueError(f"Existing source element already has another ID: {source_node.attrib['id']}")
            source_node.attrib["id"] = sid
            chapter_href = posixpath.relpath(chapter_path, posixpath.dirname(source_path))
            link_parent = source_node if source_node.tag == q(XHTML, "p") else ET.SubElement(source_node, q(XHTML, "p"))
            link = ET.SubElement(link_parent, q(XHTML, "a"), {"href": f"{chapter_href}#{figure_id}"})
            link.text = " · " + figure.get("caption", "课程画面")
            source_href = f"sources.xhtml#{sid}"
        elif isinstance(src_path, str) and src_path:
            source_href = f"sources.xhtml#{source_id(figure)}"
            record = source_records.setdefault(source_id(figure), {
                "id": source_id(figure), "chapter_id": chapter_id,
                "chapter_title": figure.get("chapter_title", chapter_id),
                "chapter_path": chapter_path,
                "source_video": src_path,
                "source_video_sha256": figure.get("source_video_sha256"),
                "figures": [],
            })
            record["figures"].append({"id": figure_id, "caption": figure.get("caption", "")})

        for frame_index, frame in enumerate(frame_rows, start=1):
            if not isinstance(frame, dict):
                raise ValueError(f"Frame rows for {figure_id} must be JSON objects")
            reuse_href = frame.get("reuse_epub_asset")
            if reuse_href:
                if frame.get("image"):
                    raise ValueError("Use either image or reuse_epub_asset for one frame, not both")
                parsed_asset = urllib.parse.urlsplit(str(reuse_href))
                if parsed_asset.scheme or parsed_asset.netloc or parsed_asset.fragment:
                    raise ValueError(f"reuse_epub_asset must be a local package path: {reuse_href}")
                asset_ref = urllib.parse.unquote(parsed_asset.path)
                asset_path = posixpath.normpath(
                    asset_ref if asset_ref.startswith(package_dir + "/")
                    else posixpath.join(package_dir, asset_ref)
                )
                if asset_path not in files:
                    raise FileNotFoundError(f"Reused EPUB asset is missing: {asset_path}")
                if asset_path not in existing_hrefs:
                    raise ValueError(f"Reused EPUB asset is not already in the OPF manifest: {asset_path}")
                suffix = posixpath.splitext(asset_path)[1].lower()
                image_path = None
                image_bytes = files[asset_path]
                digest = sha256(image_bytes)
                expected_digest = frame.get("reuse_epub_asset_sha256")
                if not isinstance(expected_digest, str) or digest.lower() != expected_digest.lower():
                    raise ValueError(f"Reused EPUB asset SHA-256 does not match mapping: {asset_path}")
                reused_epub_asset = True
            else:
                image_path = Path(frame.get("image", "")).resolve()
                if not image_path.is_file():
                    raise FileNotFoundError(f"Video frame not found: {image_path}")
                suffix = image_path.suffix.lower()
                image_bytes = image_path.read_bytes()
                digest = sha256(image_bytes)
                chapter_slug = chapter_id.lower()
                safe_timestamp = re.sub(r"[^0-9-]", "-", timestamp_label(frame))
                filename = f"video-{chapter_slug}-{safe_timestamp}-{digest[:8]}{suffix}"
                asset_path = f"{package_dir}/images/{filename}"
                reused_epub_asset = False
            media_type = IMAGE_TYPES.get(suffix)
            if not media_type:
                raise ValueError(f"Unsupported image format for {asset_path}: {suffix}")
            source_frame_path = Path(frame["source_frame"]).resolve() if frame.get("source_frame") else None
            if reused_epub_asset and source_frame_path is None:
                raise ValueError("Reusing a PPT atlas image for a video figure requires its matched source_frame")
            source_frame_digest = None
            if source_frame_path is not None:
                if not source_frame_path.is_file():
                    raise FileNotFoundError(f"Original extracted frame not found: {source_frame_path}")
                source_frame_digest = sha256_file(source_frame_path)
                if frame.get("source_frame_sha256") and source_frame_digest.lower() != str(frame["source_frame_sha256"]).lower():
                    raise ValueError(f"Source frame SHA-256 does not match mapping: {source_frame_path}")
                if frame.get("crop_box_normalized_ltrb") is not None:
                    crop_box = frame["crop_box_normalized_ltrb"]
                    if (not isinstance(crop_box, list) or len(crop_box) != 4
                            or any(not isinstance(value, (int, float)) for value in crop_box)
                            or not (0 <= crop_box[0] < crop_box[2] <= 1 and 0 <= crop_box[1] < crop_box[3] <= 1)):
                        raise ValueError(f"Invalid normalized crop box for {source_frame_path}")
            timestamp = timestamp_label(frame)
            if not reused_epub_asset:
                href = posixpath.relpath(asset_path, package_dir or ".")
                if asset_path in files or asset_path in existing_hrefs:
                    raise ValueError(f"Image asset already exists: {asset_path}")
                item_id = f"media-{chapter_slug}-{safe_timestamp}-{digest[:8]}"
                if item_id in existing_ids:
                    raise ValueError(f"EPUB manifest item ID already exists: {item_id}")
                ET.SubElement(manifest, q(OPF, "item"), {
                    "id": item_id, "href": href, "media-type": media_type,
                })
                existing_ids.add(item_id)
                files[asset_path] = image_bytes
            panel = ET.SubElement(figure_node, q(XHTML, "div"), {"class": "video-frame-panel"})
            label = ET.SubElement(panel, q(XHTML, "p"), {"class": "video-frame-label"})
            frame_label = frame.get("label") or (f"画面 {frame_index}" if len(frame_rows) > 1 else "视频画面")
            label.text = f"{frame_label} · {timestamp}（候选采样点）"
            relative_src = posixpath.relpath(asset_path, posixpath.dirname(chapter_path))
            ET.SubElement(panel, q(XHTML, "img"), {
                "src": relative_src, "alt": frame.get("alt", frame.get("label", figure.get("caption", "课程画面"))),
            })
            inserted.append({
                "figure_id": figure_id, "chapter_id": chapter_id, "anchor_id": anchor_id,
                "timestamp": timestamp, "source_video": src_path or existing_source_video,
                "frame": str(image_path) if image_path is not None else asset_path,
                "frame_sha256": digest, "reused_epub_asset": reused_epub_asset,
                "source_frame": str(source_frame_path) if source_frame_path else (str(image_path) if image_path else asset_path),
                "source_frame_sha256": source_frame_digest or digest,
                "crop_box_normalized_ltrb": frame.get("crop_box_normalized_ltrb"),
                "epub_asset": asset_path,
            })

        caption = ET.SubElement(figure_node, q(XHTML, "figcaption"))
        caption.text = figure.get("caption", "课程视频画面")
        if source_href:
            link = ET.SubElement(caption, q(XHTML, "a"), {"href": source_href})
            link.text = "视频来源"
        atlas_page_href = figure.get("atlas_page_href")
        if atlas_page_href:
            parsed_atlas = urllib.parse.urlsplit(str(atlas_page_href))
            if parsed_atlas.scheme or parsed_atlas.netloc or not parsed_atlas.path or not parsed_atlas.fragment:
                raise ValueError(f"atlas_page_href must be a local XHTML path and fragment: {atlas_page_href}")
            atlas_path = posixpath.normpath(posixpath.join(
                posixpath.dirname(chapter_path), urllib.parse.unquote(parsed_atlas.path)
            ))
            if atlas_path not in files:
                raise FileNotFoundError(f"Linked atlas page document is missing: {atlas_path}")
            atlas_document = atlas_documents.setdefault(atlas_path, ET.fromstring(files[atlas_path]))
            atlas_page_id = urllib.parse.unquote(parsed_atlas.fragment)
            atlas_page = next((node for node in atlas_document.iter()
                               if node.attrib.get("id") == atlas_page_id), None)
            if atlas_page is None or not has_class(atlas_page, "atlas-page"):
                raise ValueError(f"Linked fragment is not an atlas page: {atlas_page_href}")
            if not any(node.attrib.get("href") == atlas_page_href for node in caption.iter(q(XHTML, "a"))):
                atlas_link = ET.SubElement(caption, q(XHTML, "a"), {"href": str(atlas_page_href)})
                atlas_link.text = figure.get("atlas_page_link_text", "对应课件图册页")
            chapter_href = posixpath.relpath(chapter_path, posixpath.dirname(atlas_path))
            return_href = f"{chapter_href}#{figure_id}"
            if not any(node.attrib.get("href") == return_href for node in atlas_page.iter(q(XHTML, "a"))):
                back = ET.SubElement(atlas_page, q(XHTML, "p"), {"class": "atlas-video-crosslink"})
                link = ET.SubElement(back, q(XHTML, "a"), {"href": return_href})
                link.text = figure.get("atlas_return_link_text", "返回正文视频画面")
        parent.insert(position + 1, figure_node)
        parents_by_path[chapter_path] = {
            child: ancestor for ancestor in document.iter() for child in list(ancestor)
        }

    for path, document in documents.items():
        files[path] = serialize(document, XHTML)

    page_time_updates: list[dict] = []
    video_hashes: dict[str, str] = {}
    for match in page_time_matches:
        if not isinstance(match, dict):
            raise ValueError("Every page_time_matches entry must be a JSON object")
        href = match.get("atlas_page_href")
        sample_time = match.get("sample_time")
        evidence = match.get("evidence")
        source_video = match.get("source_video")
        source_video_hash = match.get("source_video_sha256")
        source_frame = match.get("source_frame")
        source_frame_hash = match.get("source_frame_sha256")
        if not all(isinstance(value, str) and value for value in
                   (href, sample_time, evidence, source_video, source_video_hash, source_frame, source_frame_hash)):
            raise ValueError("An atlas page time match needs an explicit local video/frame, hashes, time, and evidence")
        if not re.fullmatch(r"\d{2,}:\d{2}:\d{2}", sample_time):
            raise ValueError(f"Invalid accepted sample_time: {sample_time}")
        parsed = urllib.parse.urlsplit(href)
        if parsed.scheme or parsed.netloc or not parsed.path or not parsed.fragment:
            raise ValueError(f"atlas_page_href must be a local XHTML path and fragment: {href}")
        atlas_path = posixpath.normpath(posixpath.join(
            package_dir, urllib.parse.unquote(parsed.path)
        ))
        if atlas_path not in files:
            raise FileNotFoundError(f"Atlas page document is missing: {atlas_path}")
        atlas_document = atlas_documents.setdefault(atlas_path, ET.fromstring(files[atlas_path]))
        page_id = urllib.parse.unquote(parsed.fragment)
        page = next((node for node in atlas_document.iter()
                     if node.attrib.get("id") == page_id and has_class(node, "atlas-page")), None)
        if page is None:
            raise ValueError(f"Atlas page does not exist: {href}")
        expected_source = str(match.get("source_id", ""))
        expected_page = str(match.get("page_number", ""))
        if expected_source and page.attrib.get("data-source-id") != expected_source:
            raise ValueError(f"Atlas page source_id differs from time mapping: {href}")
        if expected_page and page.attrib.get("data-page-number") != expected_page:
            raise ValueError(f"Atlas page number differs from time mapping: {href}")

        current_status = page.attrib.get("data-time-status")
        current_time = page.attrib.get("data-sample-time")
        if current_status in {"accepted_video_sample_point_only", "accepted_sample_point_only"}:
            if current_time != sample_time:
                raise ValueError(f"Refusing to replace a different accepted atlas sample time: {href}")
        elif current_status not in {"unknown", "unknown_no_accepted_mapping", "no_match", "similar_not_same", "unmapped"}:
            raise ValueError(f"Atlas page has missing/unsupported prior time status: {href} {current_status!r}")

        video_path = Path(source_video).resolve()
        frame_path = Path(source_frame).resolve()
        if not video_path.is_file() or not frame_path.is_file():
            raise FileNotFoundError(f"Page-time evidence source missing: {video_path} / {frame_path}")
        video_key = str(video_path)
        if video_key not in video_hashes:
            video_hashes[video_key] = sha256_file(video_path)
        actual_video_hash = video_hashes[video_key]
        actual_frame_hash = sha256_file(frame_path)
        if actual_video_hash.lower() != source_video_hash.lower():
            raise ValueError(f"Source video SHA-256 differs from page-time mapping: {video_path}")
        if actual_frame_hash.lower() != source_frame_hash.lower():
            raise ValueError(f"Source frame SHA-256 differs from page-time mapping: {frame_path}")

        page.attrib["data-sample-time"] = sample_time
        page.attrib["data-time-status"] = "accepted_video_sample_point_only"
        page.attrib["data-time-evidence"] = re.sub(r"[^A-Za-z0-9_.-]+", "_", evidence).strip("_")[:96]
        visible_label = f"视频采样点：{sample_time} （不表示页面出现起点或持续区间）"
        label = next((node for node in page.iter(q(XHTML, "p")) if has_class(node, "atlas-time-status")), None)
        if label is None:
            label = ET.SubElement(page, q(XHTML, "p"), {"class": "atlas-time-status small"})
        else:
            label.clear()
            label.set("class", "atlas-time-status small")
        label.text = visible_label
        page_time_updates.append({
            "atlas_page_href": href, "source_id": page.attrib.get("data-source-id"),
            "page_number": page.attrib.get("data-page-number"), "sample_time": sample_time,
            "video_sha256": actual_video_hash, "source_frame_sha256": actual_frame_hash,
            "evidence": evidence, "semantics": "candidate sample point only; not onset or interval",
        })

    for path, document in atlas_documents.items():
        files[path] = serialize(document, XHTML)
    metadata = package.find(q(OPF, "metadata"))
    if metadata is not None:
        modified = next((node for node in metadata.iter(q(OPF, "meta"))
                         if node.attrib.get("property") == "dcterms:modified"), None)
        if modified is None:
            modified = ET.SubElement(metadata, q(OPF, "meta"), {"property": "dcterms:modified"})
        modified.text = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    files[opf_path] = serialize(package, OPF)

    if source_records:
        if source_doc is None:
            raise ValueError("Video-source mappings require an existing sources.xhtml in the EPUB")
        body = source_doc.find(q(XHTML, "body"))
        if body is None:
            raise ValueError("sources.xhtml has no body")
        section = next((node for node in source_doc.iter(q(XHTML, "section"))
                        if node.attrib.get("id") == "video-frame-sources"), None)
        if section is None:
            section = ET.SubElement(body, q(XHTML, "section"), {"id": "video-frame-sources"})
            heading = ET.SubElement(section, q(XHTML, "h2"))
            heading.text = "视频抽帧来源"
            note = ET.SubElement(section, q(XHTML, "p"))
            note.text = "下列视频时间为抽帧候选点，便于回看，不代表画面起始时点。"
        for source in source_records.values():
            if any(node.attrib.get("id") == source["id"] for node in source_doc.iter()):
                raise ValueError(f"Source appendix ID already exists: {source['id']}")
            entry = ET.SubElement(section, q(XHTML, "section"), {"id": source["id"]})
            heading = ET.SubElement(entry, q(XHTML, "h3"))
            heading.text = f"{source['chapter_id']} · {source['chapter_title']}"
            video = ET.SubElement(entry, q(XHTML, "p"))
            video.text = "源视频：" + source["source_video"]
            if source.get("source_video_sha256"):
                digest = ET.SubElement(entry, q(XHTML, "p"))
                digest.text = "SHA-256：" + source["source_video_sha256"]
            for figure_ref in source["figures"]:
                link_p = ET.SubElement(entry, q(XHTML, "p"))
                chapter_href = posixpath.relpath(source["chapter_path"], package_dir or ".")
                link = ET.SubElement(link_p, q(XHTML, "a"), {
                    "href": f"{chapter_href}#{figure_ref['id']}"
                })
                link.text = "返回插图：" + figure_ref["caption"]
    if source_doc is not None and (source_records or any(figure.get("existing_source_video") for figure in figures)):
        files[source_path] = serialize(source_doc, XHTML)

    css = files[css_path].decode("utf-8")
    marker = "/* source-mapped video frame groups */"
    if marker not in css:
        css += "\n" + marker + "\n" + """\
figure.video-frame-group { margin: 1.2em 0; }
.video-frame-panel { display: block; margin: 0 0 1em; }
.video-frame-panel img { display: block; max-width: 100%; height: auto; margin: 0 auto; }
.video-frame-label { margin: 0.35em 0; font-size: 0.9em; color: inherit; }
figure.video-frame-group figcaption { margin-top: 0.45em; font-size: 0.9em; }
"""
        files[css_path] = css.encode("utf-8")

    local_references = validate_local_references(files, package, package_dir)

    output_epub.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_epub, "w") as target:
        target.writestr("mimetype", files["mimetype"], compress_type=zipfile.ZIP_STORED)
        original_names = {info.filename for info in original_infos}
        for info in original_infos:
            if info.filename == "mimetype":
                continue
            target.writestr(info, files[info.filename])
        for name, content in files.items():
            if name not in original_names:
                target.writestr(name, content, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(output_epub) as check:
        if check.testzip() is not None:
            raise ValueError("Output EPUB failed ZIP integrity check")
        scripts = sum(
            node.tag == q(XHTML, "script")
            for name in check.namelist() if name.endswith(".xhtml")
            for node in ET.fromstring(check.read(name)).iter()
        )
        if scripts:
            raise ValueError("Output EPUB unexpectedly contains JavaScript")

    report = {
        "input": str(input_epub), "output": str(output_epub),
        "mapping": str(mapping_path.resolve()), "figure_groups": len(figures),
        "frames": len(inserted), "source_videos": len(source_records),
        "modified_chapters": sorted(documents),
        "sha256": sha256(output_epub.read_bytes()), "scripts": scripts,
        "checked_local_references": local_references,
        "timestamp_note": "Sampled frame locations are not guaranteed slide-onset timestamps.",
        "page_time_matches": page_time_updates,
        "inserted": inserted,
    }
    report_path = output_epub.with_suffix(output_epub.suffix + ".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    args = parser.parse_args()
    report = insert_figures(args.input, args.output, args.mapping)
    print(json.dumps({key: report[key] for key in ("figure_groups", "frames", "source_videos", "sha256", "output")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
