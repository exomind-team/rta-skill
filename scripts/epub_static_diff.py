#!/usr/bin/env python3
"""Convert paragraph-paired XHTML in an EPUB into a static original→edited diff."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET

from diff_match_patch import diff_match_patch

XHTML = "http://www.w3.org/1999/xhtml"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
OPS = "http://www.idpf.org/2007/ops"
CSS_MARKER = "/* Source comparison reader placement: leading and right aligned */"

ET.register_namespace("", XHTML)
ET.register_namespace("epub", OPS)
ET.register_namespace("dc", DC)


def q(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def text_content(node: ET.Element) -> str:
    return "".join(node.itertext())


def classes(node: ET.Element) -> set[str]:
    return set(node.attrib.get("class", "").split())


def serialize(node: ET.Element) -> bytes:
    return ET.tostring(node, encoding="utf-8", xml_declaration=True)


def resolve_package_path(files: dict[str, bytes]) -> str:
    container = ET.fromstring(files["META-INF/container.xml"])
    rootfile = container.find(f"{q(CONTAINER, 'rootfiles')}/{q(CONTAINER, 'rootfile')}")
    if rootfile is None or not rootfile.attrib.get("full-path"):
        raise ValueError("container.xml does not name an OPF package document")
    return rootfile.attrib["full-path"]


def spine_xhtml_paths(files: dict[str, bytes], package_path: str) -> list[str]:
    package = ET.fromstring(files[package_path])
    manifest = package.find(q(OPF, "manifest"))
    spine = package.find(q(OPF, "spine"))
    if manifest is None or spine is None:
        raise ValueError("OPF is missing manifest or spine")
    items = {node.attrib["id"]: node for node in manifest.findall(q(OPF, "item"))}
    result = []
    for itemref in spine.findall(q(OPF, "itemref")):
        item = items.get(itemref.attrib.get("idref", ""))
        if item is None or item.attrib.get("media-type") != "application/xhtml+xml":
            continue
        result.append(posixpath.normpath(posixpath.join(posixpath.dirname(package_path), item.attrib["href"])))
    return result


def append_text(node: ET.Element, value: str) -> None:
    if not value:
        return
    if len(node):
        node[-1].tail = (node[-1].tail or "") + value
    else:
        node.text = (node.text or "") + value


def render_diff(original: str, revised: str, dmp: diff_match_patch) -> tuple[ET.Element, int, int]:
    parts = dmp.diff_main(original, revised)
    dmp.diff_cleanupSemantic(parts)
    old_check = "".join(value for operation, value in parts if operation != 1)
    new_check = "".join(value for operation, value in parts if operation != -1)
    if old_check != original or new_check != revised:
        raise ValueError("character diff did not reconstruct both source texts")

    paragraph = ET.Element(q(XHTML, "p"), {"class": "diff"})
    added = deleted = 0
    for operation, value in parts:
        if operation == 0:
            append_text(paragraph, value)
            continue
        tag = "del" if operation == -1 else "ins"
        css_class = "diff-deleted" if operation == -1 else "diff-added"
        marked = ET.SubElement(paragraph, q(XHTML, tag), {"class": css_class})
        marked.text = value
        if operation == -1:
            deleted += len(value)
        else:
            added += len(value)
    return paragraph, added, deleted


def disclosure(original_id: str, diff: ET.Element, added: int, deleted: int) -> ET.Element:
    details = ET.Element(q(XHTML, "details"), {
        "id": original_id,
        "class": "source-comparison",
        "data-added": str(added),
        "data-deleted": str(deleted),
    })
    summary = ET.SubElement(details, q(XHTML, "summary"))
    label = ET.SubElement(summary, q(XHTML, "span"), {"class": "diff-label"})
    label.text, label.tail = "原文", " "
    plus = ET.SubElement(summary, q(XHTML, "span"), {"class": "diff-add"})
    plus.text, plus.tail = f"+{added}", " "
    minus = ET.SubElement(summary, q(XHTML, "span"), {"class": "diff-delete"})
    minus.text = f"-{deleted}"
    quote = ET.SubElement(details, q(XHTML, "blockquote"), {"class": "comparison"})
    quote.append(diff)
    return details


def add_css(css: bytes) -> bytes:
    source = css.decode("utf-8")
    if CSS_MARKER in source:
        return css
    rules = """

/* Source comparison reader placement: leading and right aligned */
/* The closed control precedes the proofread paragraph and sits at the right edge. */
details.source-comparison { margin: .02em 0 .12em; text-align: right; }
details.source-comparison > summary { cursor: pointer; list-style-position: inside; text-align: right; font-size: .86em; line-height: 1.4; }
.diff-label { color: #777; }
.diff-add, .diff-delete { display:inline-block; margin-left:.25em; padding:0 .22em; border-radius:.18em; font-weight:700; text-indent:0; }
.diff-add { color:#1b5e20; background-color:#d4f8d4; }
.diff-delete { color:#8d1e1e; background-color:#ffd4d4; }
blockquote.comparison { margin:.5em 0 1em 1em; padding:.5em .9em; border-left:2px solid #999; background:transparent; }
p.diff { margin:.25em 0; padding-left:.5em; text-indent:0; text-align:justify; line-height:1.75; overflow-wrap:anywhere; }
p.proofread { text-indent:2em; text-align:justify; }
ins.diff-added { color:#1b5e20; background-color:#d4f8d4; font-weight:700; text-decoration:none; }
del.diff-deleted { color:#8d1e1e; background-color:#ffd4d4; text-decoration:line-through; }
/* Zotero dark mode resets non-link colors/backgrounds with !important. These
   more-specific rules restore both foreground and background contrast. */
:root[data-color-scheme=dark] .diff-label:not(:link):not(:visited) { color:#b8c0cc !important; background-color:transparent !important; }
:root[data-color-scheme=dark] .diff-add:not(:link):not(:visited) { color:#7ee787 !important; background-color:rgba(46,160,67,.25) !important; }
:root[data-color-scheme=dark] .diff-delete:not(:link):not(:visited) { color:#ff7b72 !important; background-color:rgba(248,81,73,.25) !important; }
:root[data-color-scheme=dark] ins.diff-added:not(:link):not(:visited) { color:#7ee787 !important; background-color:rgba(46,160,67,.25) !important; font-weight:700 !important; text-decoration:none !important; }
:root[data-color-scheme=dark] del.diff-deleted:not(:link):not(:visited) { color:#ff7b72 !important; background-color:rgba(248,81,73,.25) !important; text-decoration:line-through !important; }
"""
    return (source.rstrip() + rules + "\n").encode("utf-8")


def find_stylesheet_paths(files: dict[str, bytes], paths: list[str], package_path: str) -> list[str]:
    found = []
    for path in paths:
        root = ET.fromstring(files[path])
        for link in root.iter(q(XHTML, "link")):
            rel = set(link.attrib.get("rel", "").lower().split())
            href = link.attrib.get("href")
            if href and "stylesheet" in rel:
                css_path = posixpath.normpath(posixpath.join(posixpath.dirname(path), href.split("#", 1)[0]))
                if css_path in files and css_path not in found:
                    found.append(css_path)
    if not found:
        raise ValueError("No linked CSS stylesheet found in the EPUB spine")
    return found


def add_preface_note(files: dict[str, bytes], paths: list[str]) -> bool:
    preface_path = next(
        (p for p in paths if PurePosixPath(p).name.lower() in {"preface.xhtml", "front-index.xhtml"}),
        None,
    )
    if not preface_path:
        raise ValueError("A preface.xhtml or front-index.xhtml is required to explain the comparison convention once")
    root = ET.fromstring(files[preface_path])
    body = root.find(q(XHTML, "body"))
    if body is None:
        raise ValueError(f"{PurePosixPath(preface_path).name} has no body")
    if any("source-diff-convention" in classes(node) for node in body):
        return False
    children = list(body)
    reading_index = next(
        (i for i, node in enumerate(children) if "阅读索引" in text_content(node)),
        None,
    )
    index = (
        reading_index + 1
        if reading_index is not None
        else next((i for i, node in enumerate(children) if node.tag in {q(XHTML, "h2"), q(XHTML, "h3")}), len(children))
    )
    note = ET.Element(q(XHTML, "p"), {"class": "source-diff-convention"})
    note.text = "阅读方式：正文默认呈现校读版。折叠摘要中的+N/-M统计从原文到校读版的新增和删去字符；展开后新增为绿色，删去为红色删除线。差异已预先写入本书，不依赖JavaScript。"
    body.insert(index, note)
    files[preface_path] = serialize(root)
    return True


def reconstruct(diff: ET.Element) -> tuple[str, str]:
    old, new = [], []

    def walk(node: ET.Element) -> None:
        tag = node.tag.rsplit("}", 1)[-1]
        if node.text:
            if tag != "ins":
                old.append(node.text)
            if tag != "del":
                new.append(node.text)
        for child in list(node):
            walk(child)
            if child.tail:
                old.append(child.tail)
                new.append(child.tail)

    walk(diff)
    return "".join(old), "".join(new)


def existing_comparison_counts(files: dict[str, bytes], paths: list[str]) -> Counter:
    """Count valid source-comparison disclosures already in the input EPUB.
    - 🎯Allow a reviewed chapter to be updated inside a book that already has diffs.
    - 📌Ordinary collapsible notes are not source comparisons.
    - 🚩Invalid prior comparison markup still fails before a new output is written.
    """
    counts = Counter()
    for path in paths:
        root = ET.fromstring(files[path])
        for details in root.iter(q(XHTML, "details")):
            if "source-comparison" not in classes(details):
                continue
            if "open" in details.attrib:
                raise ValueError(f"Existing source comparison must start closed: {path}")
            summary = details.find(q(XHTML, "summary"))
            diff = next((p for p in details.iter(q(XHTML, "p")) if "diff" in classes(p)), None)
            if summary is None or diff is None:
                raise ValueError(f"Existing source comparison is missing summary or diff: {path}")
            old_text, new_text = reconstruct(diff)
            added = sum(len(text_content(e)) for e in diff.iter(q(XHTML, "ins")))
            deleted = sum(len(text_content(e)) for e in diff.iter(q(XHTML, "del")))
            if (
                text_content(summary).split() != ["原文", f"+{added}", f"-{deleted}"]
                or int(details.attrib.get("data-added", -1)) != added
                or int(details.attrib.get("data-deleted", -1)) != deleted
                or not old_text
                or not new_text
            ):
                raise ValueError(f"Existing source comparison has invalid reconstruction or counters: {path}")
            counts["preserved_comparison_details"] += 1
            counts["preserved_added_chars"] += added
            counts["preserved_deleted_chars"] += deleted
    return counts


def validate(output_path: Path, files: dict[str, bytes], expected: Counter, source_assets: dict[str, str]) -> dict:
    with zipfile.ZipFile(output_path) as archive:
        if archive.testzip():
            raise ValueError("ZIP CRC validation failed")
        names = archive.namelist()
        if not names or names[0] != "mimetype" or archive.read("mimetype") != b"application/epub+zip":
            raise ValueError("mimetype must be the first, uncompressed EPUB entry")
        docs = {
            name: ET.fromstring(archive.read(name))
            for name in names if name.endswith((".xhtml", ".xml", ".opf", ".ncx", ".svg"))
        }
        all_ids = {name: {e.attrib["id"] for e in root.iter() if e.attrib.get("id")} for name, root in docs.items()}
        details_count = total_add = total_delete = scripts = links = 0
        for name, root in docs.items():
            for node in root.iter():
                local = node.tag.rsplit("}", 1)[-1].lower()
                if local == "script":
                    scripts += 1
                if any(key.lower().startswith("on") for key in node.attrib):
                    raise ValueError(f"Inline event handler found in {name}")
                if any(value.strip().lower().startswith("javascript:") for value in node.attrib.values()):
                    raise ValueError(f"javascript: URL found in {name}")
                if node.tag == q(XHTML, "details") and "source-comparison" in classes(node):
                    if "open" in node.attrib:
                        raise ValueError(f"Disclosure must start closed: {name}")
                    summary = node.find(q(XHTML, "summary"))
                    diff = next((p for p in node.iter(q(XHTML, "p")) if "diff" in classes(p)), None)
                    if summary is None or diff is None:
                        raise ValueError(f"Disclosure is missing summary or diff content: {name}")
                    old_text, new_text = reconstruct(diff)
                    added = sum(len(text_content(e)) for e in diff.iter(q(XHTML, "ins")))
                    deleted = sum(len(text_content(e)) for e in diff.iter(q(XHTML, "del")))
                    if (text_content(summary).split() != ["原文", f"+{added}", f"-{deleted}"]
                            or int(node.attrib.get("data-added", -1)) != added
                            or int(node.attrib.get("data-deleted", -1)) != deleted
                            or not old_text or not new_text):
                        raise ValueError(f"Diff summary or reconstructed text is invalid: {name}")
                    total_add += added
                    total_delete += deleted
                    details_count += 1
                for attr in ("href", "src"):
                    reference = node.attrib.get(attr)
                    if not reference or re.match(r"^[a-z][a-z0-9+.-]*:", reference, re.I):
                        continue
                    path, _, fragment = reference.partition("#")
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(name), path)) if path else name
                    if target not in names or (fragment and fragment not in all_ids.get(target, set())):
                        raise ValueError(f"Broken local reference in {name}: {reference}")
                    links += 1
        if scripts:
            raise ValueError("EPUB must not contain script elements")
        expected_details = expected["preserved_comparison_details"] + expected["changed"]
        if details_count != expected_details:
            raise ValueError(f"Expected {expected_details} source comparisons, found {details_count}")
        expected_added = expected["preserved_added_chars"] + expected["added"]
        expected_deleted = expected["preserved_deleted_chars"] + expected["deleted"]
        if total_add != expected_added or total_delete != expected_deleted:
            raise ValueError("Package-wide diff counters differ from preserved and newly built comparisons")
        for name, digest in source_assets.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f"Asset changed during conversion: {name}")
        package = next(root for name, root in docs.items() if name.endswith(".opf"))
        if not package.attrib.get("version", "").startswith("3"):
            raise ValueError("Output is not an EPUB 3 package")
        return {
            "passed": True,
            "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            "size_bytes": output_path.stat().st_size,
            "chapters": sum("chapter-" in name and name.endswith(".xhtml") for name in names),
            "changed_pairs": expected["changed"],
            "preserved_comparison_details": expected["preserved_comparison_details"],
            "total_comparison_details": details_count,
            "unchanged_paragraphs": expected["unchanged"],
            "added_chars": total_add,
            "deleted_chars": total_delete,
            "scripts": scripts,
            "local_links_checked": links,
            "assets_preserved": len(source_assets),
        }


def transform(input_path: Path, output_path: Path, title: str | None = None) -> dict:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Choose a new output path; source EPUBs are never overwritten")
    with zipfile.ZipFile(input_path) as archive:
        infos = {info.filename: copy(info) for info in archive.infolist()}
        files = {name: archive.read(name) for name in archive.namelist()}
    source_assets = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in files.items()
        if name.startswith("OEBPS/images/") or "/images/" in name
    }
    package_path = resolve_package_path(files)
    package = ET.fromstring(files[package_path])
    manifest = package.find(q(OPF, "manifest"))
    metadata = package.find(q(OPF, "metadata"))
    if manifest is None or metadata is None:
        raise ValueError("OPF package is missing manifest or metadata")
    paths = spine_xhtml_paths(files, package_path)
    if not paths:
        raise ValueError("EPUB spine has no XHTML documents")

    dmp = diff_match_patch()
    counts = existing_comparison_counts(files, [name for name in files if name.endswith(".xhtml")])
    for path in paths:
        root = ET.fromstring(files[path])
        parents = {child: parent for parent in root.iter() for child in list(parent)}
        for quote in list(root.iter(q(XHTML, "blockquote"))):
            originals = [p for p in quote.iter(q(XHTML, "p")) if "original" in classes(p)]
            if not originals:
                continue
            if len(originals) != 1:
                raise ValueError(f"Expected one p.original per source block in {path}")
            original_node = originals[0]
            parent = parents.get(quote)
            if parent is None:
                raise ValueError(f"Orphan source block in {path}")
            siblings = list(parent)
            index = siblings.index(quote)
            original_id = original_node.attrib.get("id")
            if not original_id:
                raise ValueError(f"p.original needs a stable id in {path}")
            original_text = text_content(original_node)
            revised = siblings[index + 1] if index + 1 < len(siblings) else None
            paired = revised is not None and revised.tag == q(XHTML, "p") and "rewritten" in classes(revised)
            counts["source_pairs"] += 1
            if not paired:
                if len(list(quote)) != 1 or list(quote)[0] is not original_node:
                    raise ValueError(f"Unchanged source block has unexpected structure in {path}")
                parent.remove(quote)
                original_node.set("class", "proofread")
                parent.insert(index, original_node)
                counts["unchanged"] += 1
                continue

            revised_text = text_content(revised)
            parent.remove(quote)
            revised.set("class", "proofread")
            if original_text == revised_text:
                counts["identical"] += 1
                continue
            diff, added, deleted = render_diff(original_text, revised_text, dmp)
            details = disclosure(original_id, diff, added, deleted)
            revised_index = list(parent).index(revised)
            # Reader preference: keep the disclosure at the paragraph lead,
            # right-aligned above the proofread prose instead of after it.
            parent.insert(revised_index, details)
            counts["changed"] += 1
            counts["added"] += added
            counts["deleted"] += deleted

        for p in root.iter(q(XHTML, "p")):
            if "original" in classes(p):
                p.set("class", "proofread")
                counts["unchanged"] += 1
        files[path] = serialize(root)

    if counts["source_pairs"] == 0:
        raise ValueError("No p.original paragraphs found; prepare paragraph pairs before diffing")
    preface_updated = add_preface_note(files, paths)
    css_paths = find_stylesheet_paths(files, paths, package_path)
    for css_path in css_paths:
        files[css_path] = add_css(files[css_path])

    title_node = metadata.find(q(DC, "title"))
    old_title = text_content(title_node) if title_node is not None else input_path.stem
    new_title = title or (old_title + " · 原文差异版")
    if title_node is None:
        title_node = ET.SubElement(metadata, q(DC, "title"))
    title_node.text = new_title
    identifier = metadata.find(q(DC, "identifier"))
    if identifier is None:
        identifier = ET.SubElement(metadata, q(DC, "identifier"), {"id": "pub-id"})
    identifier.text = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, hashlib.sha256(input_path.read_bytes()).hexdigest() + new_title))
    package.set("version", "3.0")
    modified = next((m for m in metadata.findall(q(OPF, "meta")) if m.attrib.get("property") == "dcterms:modified"), None)
    if modified is None:
        modified = ET.SubElement(metadata, q(OPF, "meta"), {"property": "dcterms:modified"})
    modified.text = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    files[package_path] = serialize(package)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    order = list(infos)
    if "mimetype" not in files:
        raise ValueError("Source EPUB has no mimetype entry")
    order = ["mimetype"] + [name for name in order if name != "mimetype"]
    with zipfile.ZipFile(output_path, "w") as target:
        for name in order:
            info = infos.get(name, zipfile.ZipInfo(name))
            if name == "mimetype":
                info.compress_type = zipfile.ZIP_STORED
            target.writestr(info, files[name])

    validation = validate(output_path, files, counts, source_assets)
    return {
        "source": str(input_path),
        "output": str(output_path),
        "title": new_title,
        "source_pairs": counts["source_pairs"],
        "changed_pairs": counts["changed"],
        "unchanged_paragraphs": counts["unchanged"],
        "identical_pairs_without_disclosure": counts["identical"],
        "added_chars": counts["added"],
        "deleted_chars": counts["deleted"],
        "preface_updated": preface_updated,
        "validation": validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Source EPUB; never overwritten")
    parser.add_argument("--output", type=Path, required=True, help="New EPUB path")
    parser.add_argument("--title", help="New package title; default appends a comparison-edition label")
    parser.add_argument("--report", type=Path, help="Optional JSON validation report path")
    args = parser.parse_args()
    result = transform(args.input, args.output, args.title)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
