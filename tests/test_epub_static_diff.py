from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

SKILL = Path(__file__).resolve().parents[1]
TRANSFORM = SKILL / "scripts" / "epub_static_diff.py"
AUDIT = SKILL / "scripts" / "audit_deletions.py"
X = "http://www.w3.org/1999/xhtml"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
OPS = "http://www.idpf.org/2007/ops"


def q(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def text(node: ET.Element) -> str:
    return "".join(node.itertext())


def make_fixture(path: Path, *, front_document_name: str = "preface.xhtml") -> bytes:
    ET.register_namespace("", X)
    ET.register_namespace("dc", DC)
    ET.register_namespace("epub", OPS)
    files: dict[str, bytes] = {}

    container = ET.Element("{urn:oasis:names:tc:opendocument:xmlns:container}container")
    roots = ET.SubElement(container, "{urn:oasis:names:tc:opendocument:xmlns:container}rootfiles")
    ET.SubElement(roots, "{urn:oasis:names:tc:opendocument:xmlns:container}rootfile", {
        "full-path": "OEBPS/package.opf", "media-type": "application/oebps-package+xml"
    })
    files["META-INF/container.xml"] = ET.tostring(container, encoding="utf-8", xml_declaration=True)

    pkg = ET.Element(q(OPF, "package"), {"version": "3.0", "unique-identifier": "pub-id"})
    metadata = ET.SubElement(pkg, q(OPF, "metadata"))
    ET.SubElement(metadata, q(DC, "identifier"), {"id": "pub-id"}).text = "urn:synthetic:test"
    ET.SubElement(metadata, q(DC, "title")).text = "Synthetic lesson"
    ET.SubElement(metadata, q(DC, "language")).text = "en"
    manifest = ET.SubElement(pkg, q(OPF, "manifest"))
    for ident, href, media in [
        ("preface", front_document_name, "application/xhtml+xml"),
        ("chapter1", "chapter-001.xhtml", "application/xhtml+xml"),
        ("chapter2", "chapter-002.xhtml", "application/xhtml+xml"),
        ("nav", "nav.xhtml", "application/xhtml+xml"),
        ("style", "style.css", "text/css"),
        ("img", "images/sample.svg", "image/svg+xml"),
    ]:
        ET.SubElement(manifest, q(OPF, "item"), {"id": ident, "href": href, "media-type": media})
    spine = ET.SubElement(pkg, q(OPF, "spine"))
    ET.SubElement(spine, q(OPF, "itemref"), {"idref": "preface"})
    ET.SubElement(spine, q(OPF, "itemref"), {"idref": "chapter1"})
    ET.SubElement(spine, q(OPF, "itemref"), {"idref": "chapter2"})
    files["OEBPS/package.opf"] = ET.tostring(pkg, encoding="utf-8", xml_declaration=True)

    def html(title: str, body: ET.Element) -> bytes:
        root = ET.Element(q(X, "html"), {"lang": "en"})
        head = ET.SubElement(root, q(X, "head"))
        ET.SubElement(head, q(X, "title")).text = title
        ET.SubElement(head, q(X, "link"), {"rel": "stylesheet", "type": "text/css", "href": "style.css"})
        root.append(body)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    preface_body = ET.Element(q(X, "body"))
    ET.SubElement(preface_body, q(X, "h1")).text = "Synthetic lesson"
    ET.SubElement(preface_body, q(X, "p")).text = "Synthetic preface."
    files[f"OEBPS/{front_document_name}"] = html("Preface", preface_body)

    body = ET.Element(q(X, "body"))
    section = ET.SubElement(body, q(X, "section"), {"id": "s01"})
    ET.SubElement(section, q(X, "h1")).text = "Lesson 1"
    quote = ET.SubElement(section, q(X, "blockquote"))
    ET.SubElement(quote, q(X, "p"), {"id": "p0001", "class": "original"}).text = "A <sample> & note is old."
    ET.SubElement(section, q(X, "p"), {"id": "edited-p0001", "class": "rewritten"}).text = "A <sample> & note is new."
    unchanged = ET.SubElement(section, q(X, "blockquote"))
    ET.SubElement(unchanged, q(X, "p"), {"id": "p0002", "class": "original"}).text = "This paragraph stays the same."
    figure = ET.SubElement(section, q(X, "figure"))
    ET.SubElement(figure, q(X, "img"), {"src": "images/sample.svg", "alt": "Synthetic image"})
    caption = ET.SubElement(figure, q(X, "figcaption"))
    caption.text = "Synthetic source page 3."
    files["OEBPS/chapter-001.xhtml"] = html("Lesson 1", body)

    old_chapter = ET.Element(q(X, "body"))
    ET.SubElement(old_chapter, q(X, "h1")).text = "Previously reviewed chapter"
    previous = ET.SubElement(old_chapter, q(X, "details"), {
        "id": "previous-p0001", "class": "source-comparison",
        "data-added": "3", "data-deleted": "3",
    })
    previous_summary = ET.SubElement(previous, q(X, "summary"))
    label = ET.SubElement(previous_summary, q(X, "span"), {"class": "diff-label"})
    label.text, label.tail = "原文", " "
    plus = ET.SubElement(previous_summary, q(X, "span"), {"class": "diff-add"})
    plus.text, plus.tail = "+3", " "
    ET.SubElement(previous_summary, q(X, "span"), {"class": "diff-delete"}).text = "-3"
    previous_quote = ET.SubElement(previous, q(X, "blockquote"), {"class": "comparison"})
    previous_diff = ET.SubElement(previous_quote, q(X, "p"), {"class": "diff"})
    ET.SubElement(previous_diff, q(X, "del"), {"class": "diff-deleted"}).text = "old"
    ET.SubElement(previous_diff, q(X, "ins"), {"class": "diff-added"}).text = "new"
    unrelated = ET.SubElement(old_chapter, q(X, "details"), {"id": "editorial-note"})
    ET.SubElement(unrelated, q(X, "summary")).text = "Editorial note"
    ET.SubElement(unrelated, q(X, "p")).text = "This folded note is not a source diff."
    files["OEBPS/chapter-002.xhtml"] = html("Previously reviewed chapter", old_chapter)

    nav = ET.Element(q(X, "html"), {"lang": "en"})
    nav_head = ET.SubElement(nav, q(X, "head"))
    ET.SubElement(nav_head, q(X, "title")).text = "Contents"
    nav_body = ET.SubElement(nav, q(X, "body"))
    nav_el = ET.SubElement(nav_body, q(X, "nav"), {q(OPS, "type"): "toc"})
    ol = ET.SubElement(nav_el, q(X, "ol"))
    li = ET.SubElement(ol, q(X, "li"))
    ET.SubElement(li, q(X, "a"), {"href": "chapter-001.xhtml#s01"}).text = "Lesson 1"
    li2 = ET.SubElement(ol, q(X, "li"))
    ET.SubElement(li2, q(X, "a"), {"href": "chapter-002.xhtml"}).text = "Previously reviewed chapter"
    files["OEBPS/nav.xhtml"] = ET.tostring(nav, encoding="utf-8", xml_declaration=True)
    files["OEBPS/style.css"] = b"body { line-height: 1.5; } blockquote { margin-left: 1em; }\n"
    files["OEBPS/images/sample.svg"] = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1" viewBox="0 0 1 1">'
        b'<rect width="1" height="1" fill="#f00"/></svg>'
    )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
    return hashlib.sha256(files["OEBPS/images/sample.svg"]).digest()


class EpubDiffTests(unittest.TestCase):
    def test_preserves_existing_comparisons_and_ignores_other_disclosures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.epub", root / "output.epub"
            make_fixture(source)

            result = subprocess.run(
                [sys.executable, str(TRANSFORM), "--input", str(source), "--output", str(output)],
                capture_output=True, text=True, check=True,
            )
            data = json.loads(result.stdout)

            self.assertEqual(data["changed_pairs"], 1)
            self.assertEqual(data["validation"]["preserved_comparison_details"], 1)
            self.assertEqual(data["validation"]["total_comparison_details"], 2)
            with zipfile.ZipFile(output) as archive:
                chapter = ET.fromstring(archive.read("OEBPS/chapter-002.xhtml"))
                comparisons = [
                    node for node in chapter.iter(q(X, "details"))
                    if "source-comparison" in node.attrib.get("class", "").split()
                ]
                notes = [
                    node for node in chapter.iter(q(X, "details"))
                    if "source-comparison" not in node.attrib.get("class", "").split()
                ]
                self.assertEqual(len(comparisons), 1)
                self.assertEqual(len(notes), 1)
                self.assertNotIn("open", comparisons[0].attrib)

    def test_uses_front_index_when_book_has_no_preface_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.epub", root / "output.epub"
            make_fixture(source, front_document_name="front-index.xhtml")

            result = subprocess.run(
                [sys.executable, str(TRANSFORM), "--input", str(source), "--output", str(output)],
                capture_output=True, text=True, check=True,
            )
            data = json.loads(result.stdout)
            self.assertTrue(data["preface_updated"])
            with zipfile.ZipFile(output) as archive:
                front = ET.fromstring(archive.read("OEBPS/front-index.xhtml"))
                notes = [
                    node for node in front.iter(q(X, "p"))
                    if "source-diff-convention" in node.attrib.get("class", "").split()
                ]
                self.assertEqual(len(notes), 1)
                self.assertIn("原文到校读版", text(notes[0]))

    def test_static_diff_roundtrip_privacy_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "synthetic.epub", root / "synthetic-diff.epub"
            image_digest = make_fixture(source)
            report = root / "validation.json"
            result = subprocess.run(
                [sys.executable, str(TRANSFORM), "--input", str(source), "--output", str(output), "--title", "Synthetic lesson diff", "--report", str(report)],
                capture_output=True, text=True, check=True,
            )
            data = json.loads(result.stdout)
            self.assertEqual(data["changed_pairs"], 1)
            self.assertEqual(data["unchanged_paragraphs"], 1)
            self.assertEqual(data["validation"]["scripts"], 0)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["validation"]["passed"], True)

            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist()[0], "mimetype")
                self.assertEqual(archive.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
                chapter = ET.fromstring(archive.read("OEBPS/chapter-001.xhtml"))
                details = list(chapter.iter(q(X, "details")))
                self.assertEqual(len(details), 1)
                self.assertNotIn("open", details[0].attrib)
                self.assertEqual(details[0].attrib["id"], "p0001")
                proofread = next(
                    node for node in chapter.iter(q(X, "p"))
                    if node.attrib.get("id") == "edited-p0001" and "proofread" in node.attrib.get("class", "").split()
                )
                parent_map = {child: parent for parent in chapter.iter() for child in list(parent)}
                siblings = list(parent_map[proofread])
                self.assertLess(siblings.index(details[0]), siblings.index(proofread))
                self.assertEqual(text(details[0].find(q(X, "summary"))).split(), ["原文", "+3", "-3"])
                self.assertEqual(text(details[0].find(q(X, "summary")).find(q(X, "span"))), "原文")
                diff = next(node for node in details[0].iter(q(X, "p")) if "diff" in node.attrib.get("class", "").split())
                self.assertIn("diff-added", next(diff.iter(q(X, "ins"))).attrib["class"])
                self.assertIn("diff-deleted", next(diff.iter(q(X, "del"))).attrib["class"])

                def side(element: ET.Element, omit: str) -> str:
                    pieces = []
                    def visit(node: ET.Element) -> None:
                        if node.tag.rsplit("}", 1)[-1] != omit and node.text:
                            pieces.append(node.text)
                        for child in list(node):
                            visit(child)
                            if child.tail:
                                pieces.append(child.tail)
                    visit(element)
                    return "".join(pieces)

                self.assertEqual(side(diff, "ins"), "A <sample> & note is old.")
                self.assertEqual(side(diff, "del"), "A <sample> & note is new.")
                self.assertEqual(hashlib.sha256(archive.read("OEBPS/images/sample.svg")).digest(), image_digest)
                self.assertTrue(any(node.attrib.get("id") == "p0002" and "proofread" in node.attrib.get("class", "") for node in chapter.iter(q(X, "p"))))
                css = archive.read("OEBPS/style.css").decode("utf-8")
                self.assertIn("details.source-comparison > summary", css)
                self.assertIn("text-align: right", css)
                self.assertIn("list-style-position: inside", css)
                self.assertIn("data-color-scheme=dark", css)
                self.assertRegex(css, r"ins\.diff-added\s*\{[^}]*font-weight\s*:\s*700")
                self.assertRegex(css, r"ins\.diff-added:not\(:link\):not\(:visited\)\s*\{[^}]*font-weight\s*:\s*700\s*!important")
                self.assertNotIn(b"<script", archive.read("OEBPS/chapter-001.xhtml"))

            jsonl, markdown = root / "audit.jsonl", root / "audit.md"
            subprocess.run(
                [sys.executable, str(AUDIT), "--epub", str(output), "--min-deleted-chars", "1", "--jsonl", str(jsonl), "--markdown", str(markdown)],
                capture_output=True, text=True, check=True,
            )
            row = next(
                json.loads(line)
                for line in jsonl.read_text(encoding="utf-8").splitlines()
                if json.loads(line)["paragraph_id"] == "p0001"
            )
            self.assertEqual(row["original"], "A <sample> & note is old.")
            self.assertEqual(row["proofread"], "A <sample> & note is new.")
            self.assertTrue(markdown.exists())

    def test_refuses_to_overwrite_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "synthetic.epub"
            make_fixture(source)
            before = source.read_bytes()
            failed = subprocess.run(
                [sys.executable, str(TRANSFORM), "--input", str(source), "--output", str(source)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
