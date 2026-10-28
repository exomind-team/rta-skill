#!/usr/bin/env python3
"""Normalize course terminology or source-comparison placement in an EPUB.

The frozen/original side of each source-comparison disclosure is reconstructed
before editing and verified unchanged afterward. Layout-only mode makes no text
changes. No JavaScript is used.
"""
from __future__ import annotations
import argparse
import difflib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

XHTML = "http://www.w3.org/1999/xhtml"
OPF = "http://www.idpf.org/2007/opf"
CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
OPS = "http://www.idpf.org/2007/ops"
ET.register_namespace("", XHTML)
ET.register_namespace("epub", OPS)
CSS_LAYOUT_MARKER = "/* Source comparison reader placement: leading and right aligned */"
CSS_LAYOUT_RULES = b"""

/* Source comparison reader placement: leading and right aligned */
details.source-comparison { margin: .02em 0 .12em; text-align: right; }
details.source-comparison > summary { cursor: pointer; list-style-position: inside; text-align: right; font-size: .86em; line-height: 1.4; }
"""

def q(local: str) -> str:
    return f"{{{XHTML}}}{local}"

def classes(node: ET.Element) -> set[str]:
    return set(node.attrib.get("class", "").split())

def comparison_text(node: ET.Element) -> str:
    """Return prose in a proofread node, excluding editor-only uncertainty links."""
    if "uncertainty-marker" in classes(node):
        return ""
    result = node.text or ""
    for child in list(node):
        result += comparison_text(child)
        result += child.tail or ""
    return result

def displayed_text(node: ET.Element) -> str:
    """Return all rendered text, including linked uncertainty labels."""
    result = node.text or ""
    for child in list(node):
        result += displayed_text(child)
        result += child.tail or ""
    return result

def append_text(node: ET.Element, value: str) -> None:
    if not value:
        return
    if len(node):
        node[-1].tail = (node[-1].tail or "") + value
    else:
        node.text = (node.text or "") + value

def reconstruct(diff: ET.Element) -> tuple[str, str]:
    old: list[str] = []
    new: list[str] = []
    def walk(node: ET.Element) -> None:
        tag = node.tag.rsplit("}", 1)[-1]
        if node.text:
            if tag != "ins": old.append(node.text)
            if tag != "del": new.append(node.text)
        for child in list(node):
            walk(child)
            if child.tail:
                old.append(child.tail)
                new.append(child.tail)
    walk(diff)
    return "".join(old), "".join(new)

def load_rules(path: Path) -> tuple[str, list[str], dict[str, list[str]], re.Pattern[str]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    canonical = data.get("canonical")
    variants = data.get("variants")
    protected = data.get("protected_following", {})
    if not isinstance(canonical, str) or not canonical or not isinstance(variants, list) or not variants:
        raise ValueError("Rules require a non-empty canonical term and variants array")
    variants = sorted({v for v in variants if isinstance(v, str) and v and v != canonical}, key=len, reverse=True)
    if not variants:
        raise ValueError("No distinct variants to normalize")
    if not isinstance(protected, dict):
        raise ValueError("protected_following must be an object mapping variants to suffix arrays")
    protected = {str(k): [str(s) for s in v] for k, v in protected.items() if isinstance(v, list)}
    return canonical, variants, protected, re.compile("|".join(map(re.escape, variants)))

def is_protected(text: str, match: re.Match[str], protected: dict[str, list[str]]) -> bool:
    suffix = text[match.end():]
    return any(suffix.startswith(value) for value in protected.get(match.group(0), []))

def eligible_matches(text: str, pattern: re.Pattern[str], protected: dict[str, list[str]]):
    return [m for m in pattern.finditer(text) if not is_protected(text, m, protected)]

def render_diff(original: str, revised: str) -> tuple[ET.Element, int, int]:
    node = ET.Element(q("p"), {"class": "diff"})
    added = deleted = 0
    matcher = difflib.SequenceMatcher(a=list(original), b=list(revised), autojunk=False)
    for op, a0, a1, b0, b1 in matcher.get_opcodes():
        old, new = original[a0:a1], revised[b0:b1]
        if op == "equal":
            append_text(node, old)
        elif op == "delete":
            e = ET.SubElement(node, q("del"), {"class": "diff-deleted"})
            e.text = old
            deleted += len(old)
        elif op == "insert":
            e = ET.SubElement(node, q("ins"), {"class": "diff-added"})
            e.text = new
            added += len(new)
        else:
            if old:
                e = ET.SubElement(node, q("del"), {"class": "diff-deleted"})
                e.text = old
                deleted += len(old)
            if new:
                e = ET.SubElement(node, q("ins"), {"class": "diff-added"})
                e.text = new
                added += len(new)
    if reconstruct(node) != (original, revised):
        raise ValueError("Character diff failed bidirectional reconstruction")
    return node, added, deleted

def normalize_text(value: str, canonical: str, pattern: re.Pattern[str], protected: dict[str, list[str]]) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    def sub(match: re.Match[str]) -> str:
        if is_protected(value, match, protected):
            return match.group(0)
        token = match.group(0)
        counts[token] = counts.get(token, 0) + 1
        return canonical
    return pattern.sub(sub, value), counts

def find_diff(details: ET.Element) -> ET.Element:
    for p in details.iter(q("p")):
        if "diff" in classes(p):
            return p
    raise ValueError(f"Disclosure {details.attrib.get('id')} has no diff paragraph")

def make_details(old_details: ET.Element | None, original: str, revised: str, proofread_id: str) -> ET.Element:
    attrs = dict(old_details.attrib) if old_details is not None else {}
    attrs.pop("open", None)
    if not attrs.get("id"):
        suffix = proofread_id.removeprefix("rewritten-") or proofread_id or "paragraph"
        attrs["id"] = f"original-{suffix}"
    attrs["class"] = " ".join(sorted(classes(old_details) | {"source-comparison"})) if old_details is not None else "source-comparison"
    diff, added, deleted = render_diff(original, revised)
    attrs["data-added"] = str(added)
    attrs["data-deleted"] = str(deleted)
    details = ET.Element(q("details"), attrs)
    summary = ET.SubElement(details, q("summary"))
    label = ET.SubElement(summary, q("span"), {"class": "diff-label"})
    label.text, label.tail = "原文", " "
    plus = ET.SubElement(summary, q("span"), {"class": "diff-add"})
    plus.text, plus.tail = f"+{added}", " "
    minus = ET.SubElement(summary, q("span"), {"class": "diff-delete"})
    minus.text = f"-{deleted}"
    quote = ET.SubElement(details, q("blockquote"), {"class": "comparison"})
    quote.append(diff)
    return details

def normalize_node(node: ET.Element, canonical: str, pattern: re.Pattern[str], protected: dict[str, list[str]]) -> tuple[dict[str, int], int]:
    counts: dict[str, int] = {}
    def rewrite(value: str | None) -> tuple[str | None, int]:
        if not value:
            return value, 0
        updated, local = normalize_text(value, canonical, pattern, protected)
        for key, n in local.items(): counts[key] = counts.get(key, 0) + n
        return updated, sum(local.values())
    node.text, changed = rewrite(node.text)
    total = changed
    for child in list(node):
        if "uncertainty-marker" not in classes(child):
            child_counts, child_total = normalize_node(child, canonical, pattern, protected)
            for key, n in child_counts.items(): counts[key] = counts.get(key, 0) + n
            total += child_total
        child.tail, tail_count = rewrite(child.tail)
        total += tail_count
    return counts, total

def is_chapter(path: str) -> bool:
    name = PurePosixPath(path).name
    return name == "chapter.xhtml" or name.startswith("chapter-")

def ensure_reader_css(files: dict[str, bytes], manifest: dict[str, ET.Element], package_path: str) -> None:
    """Upgrade comparison placement without duplicating the stylesheet rule."""
    package_dir = posixpath.dirname(package_path)
    for item in manifest.values():
        if item.attrib.get("media-type") != "text/css":
            continue
        path = posixpath.normpath(posixpath.join(package_dir, item.attrib.get("href", "")))
        css = files.get(path)
        if css is None:
            continue
        if CSS_LAYOUT_MARKER.encode("utf-8") in css:
            continue
        files[path] = css.rstrip() + CSS_LAYOUT_RULES

def relocate_adjacent_comparisons(root: ET.Element) -> tuple[int, list[dict]]:
    """Move verified source disclosures before their matching proofread prose.

    The disclosure may follow editor-only uncertainty links within the same
    record. Its ID and revised side must still match the proofread paragraph.
    Unmatched or source-only disclosures are preserved and reported, never
    moved by proximity alone.
    """
    parents = {child: parent for parent in root.iter() for child in list(parent)}
    moved = 0
    exceptions: dict[str, dict] = {}

    def normalized_anchor(value: str | None) -> str | None:
        if not value:
            return None
        for prefix in ("edited-", "rewritten-", "source-comparison-", "comparison-", "original-", "orig-", "source-"):
            if value.startswith(prefix):
                return value[len(prefix):]
        return value

    def validate_pair(details: ET.Element, paragraph: ET.Element) -> None:
        source_id = details.attrib.get("data-source-id")
        proofread_source_id = paragraph.attrib.get("data-source-id")
        if source_id and proofread_source_id and source_id != proofread_source_id:
            raise ValueError(f"Adjacent diff source ID mismatch at #{paragraph.attrib.get('id')}")
        detail_key = normalized_anchor(details.attrib.get("id"))
        paragraph_key = normalized_anchor(paragraph.attrib.get("id"))
        if detail_key and paragraph_key and detail_key != paragraph_key:
            raise ValueError(f"Adjacent diff ID mismatch at #{paragraph.attrib.get('id')}")
        _, revised = reconstruct(find_diff(details))
        if revised not in {comparison_text(paragraph), displayed_text(paragraph)}:
            raise ValueError(
                f"Adjacent diff does not match proofread prose in #{paragraph.attrib.get('id')}"
            )

    def is_boundary(node: ET.Element) -> bool:
        tag = node.tag.rsplit("}", 1)[-1]
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "section"}:
            return True
        if tag == "p":
            node_classes = classes(node)
            return "proofread" not in node_classes and "uncertainty-jumps" not in node_classes
        return False

    def exception(details: ET.Element, paragraph: ET.Element | None, error: Exception | str) -> None:
        key = details.attrib.get("id") or f"element-{id(details)}"
        exceptions[key] = {
            "details_id": details.attrib.get("id"),
            "paragraph_id": paragraph.attrib.get("id") if paragraph is not None else None,
            "reason": str(error),
        }

    for paragraph in list(root.iter(q("p"))):
        if "proofread" not in classes(paragraph):
            continue
        parent = parents.get(paragraph)
        if parent is None:
            continue
        siblings = list(parent)
        index = siblings.index(paragraph)
        previous = siblings[index - 1] if index > 0 else None
        if previous is not None and previous.tag == q("details") and "source-comparison" in classes(previous):
            previous_key = normalized_anchor(previous.attrib.get("id"))
            paragraph_key = normalized_anchor(paragraph.attrib.get("id"))
            if previous_key is None or paragraph_key is None or previous_key == paragraph_key:
                try:
                    validate_pair(previous, paragraph)
                except ValueError as exc:
                    exception(previous, paragraph, exc)

        candidates = []
        for following in siblings[index + 1:]:
            if is_boundary(following):
                break
            if following.tag != q("details") or "source-comparison" not in classes(following):
                continue
            detail_key = normalized_anchor(following.attrib.get("id"))
            paragraph_key = normalized_anchor(paragraph.attrib.get("id"))
            if detail_key and paragraph_key and detail_key != paragraph_key:
                continue
            try:
                validate_pair(following, paragraph)
            except ValueError as exc:
                exception(following, paragraph, exc)
                continue
            candidates.append(following)

        for following in candidates:
            parent.remove(following)
            parent.insert(list(parent).index(paragraph), following)
            moved += 1

    for parent in root.iter():
        siblings = list(parent)
        for index, details in enumerate(siblings):
            if details.tag != q("details") or "source-comparison" not in classes(details):
                continue
            following = siblings[index + 1] if index + 1 < len(siblings) else None
            if following is None or following.tag != q("p") or "proofread" not in classes(following):
                exception(details, None, "No immediately following proofread paragraph")
                continue
            try:
                validate_pair(details, following)
            except ValueError as exc:
                exception(details, following, exc)

    return moved, list(exceptions.values())

def process_epub(input_path: Path, output_path: Path, rules_path: Path | None = None,
                 layout_only: bool = False) -> dict:
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite {output_path}")
    if layout_only:
        canonical, variants, protected, pattern = None, [], {}, re.compile(r"(?!)")
    else:
        if rules_path is None:
            raise ValueError("A rules file is required unless --layout-only is selected")
        canonical, variants, protected, pattern = load_rules(rules_path)
    changed = []
    relocated_comparison_blocks = 0
    layout_exceptions = []
    with zipfile.ZipFile(input_path, "r") as source:
        if source.testzip(): raise ValueError("Input EPUB CRC check failed")
        names = source.namelist()
        container = ET.fromstring(source.read("META-INF/container.xml"))
        rootfile = container.find(f"{{{CONTAINER}}}rootfiles/{{{CONTAINER}}}rootfile")
        if rootfile is None: raise ValueError("No OPF rootfile")
        package_path = rootfile.attrib["full-path"]
        package = ET.fromstring(source.read(package_path))
        manifest = {item.attrib["id"]: item for item in package.findall(f"{{{OPF}}}manifest/{{{OPF}}}item")}
        spine = package.find(f"{{{OPF}}}spine")
        if spine is None: raise ValueError("No OPF spine")
        spine_paths=[]
        for ref in spine.findall(f"{{{OPF}}}itemref"):
            item=manifest.get(ref.attrib.get("idref",""))
            if item is None or item.attrib.get("media-type")!="application/xhtml+xml": continue
            spine_paths.append(posixpath.normpath(posixpath.join(posixpath.dirname(package_path),item.attrib["href"])))
        files={name:source.read(name) for name in names}
        image_before=figure_before=0
        for path in spine_paths:
            if path not in files or not is_chapter(path): continue
            root=ET.fromstring(files[path]);parents={c:p for p in root.iter() for c in p}
            image_before += sum(1 for e in root.iter(q("img")))
            figure_before += sum(1 for e in root.iter(q("figure")))
            targets=[]
            for p in root.iter(q("p")):
                if "proofread" not in classes(p): continue
                prose=comparison_text(p)
                if eligible_matches(prose,pattern,protected): targets.append(p)
            for p in targets:
                old_text=comparison_text(p)
                new_counts,n=normalize_node(p,canonical,pattern,protected)
                revised=comparison_text(p)
                if n==0: continue
                parent=parents[p];siblings=list(parent);idx=siblings.index(p)
                candidates = [siblings[idx-1] if idx > 0 else None,
                              siblings[idx+1] if idx+1 < len(siblings) else None]
                adjacent = next((candidate for candidate in candidates
                                 if candidate is not None and candidate.tag == q("details")
                                 and "source-comparison" in classes(candidate)), None)
                if adjacent is not None:
                    original,old_revision=reconstruct(find_diff(adjacent))
                    if old_revision!=old_text:
                        raise ValueError(f"Existing diff doesn't match proofread prose in {path} #{p.attrib.get('id')}")
                else:
                    adjacent=None;original=old_text
                fresh=make_details(adjacent,original,revised,p.attrib.get("id",""))
                if adjacent is not None:
                    parent.remove(adjacent)
                idx=list(parent).index(p)
                parent.insert(idx,fresh)
                if reconstruct(find_diff(fresh))!=(original,revised): raise ValueError("Rebuilt diff mismatch")
                changed.append({"xhtml":path,"paragraph_id":p.attrib.get("id"),"source_id":p.attrib.get("data-source-id"),"variant_counts":new_counts,"normalized_occurrences":n,"original_unchanged":True})
            relocated, exceptions = relocate_adjacent_comparisons(root)
            relocated_comparison_blocks += relocated
            layout_exceptions.extend({"xhtml":path, **row} for row in exceptions)
            files[path]=ET.tostring(root,encoding="utf-8",xml_declaration=True)
        ensure_reader_css(files, manifest, package_path)
        output_path.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(output_path,"w") as dest:
            for info in source.infolist(): dest.writestr(info,files[info.filename])
    visible_left=blocks=0
    with zipfile.ZipFile(output_path,"r") as result:
        if result.testzip(): raise ValueError("Output EPUB CRC validation failed")
        if result.namelist()[0]!="mimetype" or result.read("mimetype")!=b"application/epub+zip": raise ValueError("mimetype must remain first")
        for name in result.namelist():
            if not name.endswith((".xhtml",".xml",".opf",".svg")): continue
            root=ET.fromstring(result.read(name))
            if any(e.tag==q("script") for e in root.iter()): raise ValueError(f"Script element found in {name}")
            if not is_chapter(name): continue
            parents={c:p for p in root.iter() for c in p}
            for p in root.iter(q("p")):
                if "proofread" not in classes(p): continue
                a=parents.get(p);inside=False
                while a is not None:
                    if a.tag==q("details"):inside=True;break
                    a=parents.get(a)
                if not inside: visible_left += len(eligible_matches(comparison_text(p),pattern,protected))
            for d in root.iter(q("details")):
                if "source-comparison" not in classes(d): continue
                diff=find_diff(d);old,new=reconstruct(diff)
                added=sum(len("".join(e.itertext())) for e in diff.iter(q("ins")))
                deleted=sum(len("".join(e.itertext())) for e in diff.iter(q("del")))
                summary="".join(d.find(q("summary")).itertext())
                m=re.fullmatch(r"\s*原文\s*\+(\d+)\s*-(\d+)\s*",summary)
                if m is None or (int(m.group(1)),int(m.group(2)))!=(added,deleted): raise ValueError(f"Diff counter mismatch in {name} #{d.attrib.get('id')}")
                if "open" in d.attrib: raise ValueError(f"Disclosure starts open in {name}")
                blocks += 1
        if visible_left: raise ValueError(f"{visible_left} user-approved variants remain in visible proofread text")
        image_after=figure_after=0
        for path in spine_paths:
            if path not in result.namelist() or not is_chapter(path): continue
            root=ET.fromstring(result.read(path));image_after+=sum(1 for e in root.iter(q("img")));figure_after+=sum(1 for e in root.iter(q("figure")))
        if (image_before,figure_before)!=(image_after,figure_after): raise ValueError("Image/figure resources changed")
    totals={}
    for row in changed:
        for variant,n in row["variant_counts"].items(): totals[variant]=totals.get(variant,0)+n
    return {"mode":"layout-only" if layout_only else "terminology-normalization","layout_status":"completed_with_exceptions" if layout_exceptions else "complete","input":str(input_path),"output":str(output_path),"rules":str(rules_path) if rules_path else None,"canonical":canonical,"variants":variants,"protected_following":protected,"changed_paragraphs":len(changed),"normalized_occurrences":sum(row["normalized_occurrences"] for row in changed),"variant_counts":totals,"relocated_comparison_blocks":relocated_comparison_blocks,"layout_exception_count":len(layout_exceptions),"layout_exceptions":layout_exceptions,"visible_unresolved_variants":visible_left,"comparison_blocks_revalidated":blocks,"image_refs_preserved":image_before,"figures_preserved":figure_before,"changed":changed}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True);ap.add_argument("--output",required=True);ap.add_argument("--rules");ap.add_argument("--layout-only",action="store_true");ap.add_argument("--report",required=True)
    a=ap.parse_args()
    if a.layout_only and a.rules: ap.error("--layout-only cannot be combined with --rules")
    if not a.layout_only and not a.rules: ap.error("--rules is required unless --layout-only is selected")
    report=Path(a.report);report.parent.mkdir(parents=True,exist_ok=True)
    result=process_epub(Path(a.input),Path(a.output),Path(a.rules) if a.rules else None,layout_only=a.layout_only)
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="changed"},ensure_ascii=False))
if __name__=="__main__":main()
