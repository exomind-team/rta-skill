#!/usr/bin/env python3
"""Rank and recover original/edited paragraphs with large deletions from a diff EPUB."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

X = "http://www.w3.org/1999/xhtml"
NS = "{" + X + "}"


def text(node: ET.Element) -> str:
    return "".join(node.itertext())


def reconstruct(diff: ET.Element) -> tuple[str, str, list[str], list[str]]:
    original, revised, deleted, added = [], [], [], []

    def walk(node: ET.Element) -> None:
        local = node.tag.rsplit("}", 1)[-1]
        value = node.text or ""
        if value:
            if local != "ins":
                original.append(value)
            if local != "del":
                revised.append(value)
            if local == "del":
                deleted.append(value)
            elif local == "ins":
                added.append(value)
        for child in list(node):
            walk(child)
            tail = child.tail or ""
            if tail:
                original.append(tail)
                revised.append(tail)

    walk(diff)
    return "".join(original), "".join(revised), deleted, added


def scan(epub: Path, threshold: int) -> tuple[list[dict], dict]:
    rows = []
    chapter_totals = defaultdict(lambda: {"flagged": 0, "deleted": 0, "added": 0})
    totals = {"disclosures": 0, "added_chars": 0, "deleted_chars": 0}
    with zipfile.ZipFile(epub) as archive:
        if archive.testzip():
            raise ValueError("EPUB ZIP failed CRC validation")
        for name in archive.namelist():
            if not name.endswith(".xhtml"):
                continue
            root = ET.fromstring(archive.read(name))
            heading = next((text(node) for node in root.iter() if node.tag in {NS + "h1", NS + "h2"}), name)
            for details in root.iter(NS + "details"):
                if "source-comparison" not in details.attrib.get("class", "").split():
                    continue
                diff = next((node for node in details.iter(NS + "p") if "diff" in node.attrib.get("class", "").split()), None)
                if diff is None:
                    raise ValueError(f"Missing diff paragraph in {name} #{details.attrib.get('id')}")
                original, revised, deleted_parts, added_parts = reconstruct(diff)
                deleted_chars = sum(map(len, deleted_parts))
                added_chars = sum(map(len, added_parts))
                totals["disclosures"] += 1
                totals["added_chars"] += added_chars
                totals["deleted_chars"] += deleted_chars
                key = (heading, name)
                chapter_totals[key]["deleted"] += deleted_chars
                chapter_totals[key]["added"] += added_chars
                if deleted_chars < threshold:
                    continue
                chapter_totals[key]["flagged"] += 1
                rows.append({
                    "chapter": heading,
                    "chapter_file": name,
                    "paragraph_id": details.attrib.get("id"),
                    "deleted_chars": deleted_chars,
                    "added_chars": added_chars,
                    "original_chars": len(original),
                    "revised_chars": len(revised),
                    "deletion_rate": deleted_chars / max(1, len(original)),
                    "original": original,
                    "proofread": revised,
                    "deleted_segments": deleted_parts,
                    "added_segments": added_parts,
                })
    rows.sort(key=lambda row: (-row["deleted_chars"], -row["deletion_rate"], row["chapter_file"], row["paragraph_id"] or ""))
    chapters = [
        {"chapter": key[0], "chapter_file": key[1], **value}
        for key, value in sorted(chapter_totals.items(), key=lambda item: (-item[1]["flagged"], -item[1]["deleted"], item[0][1]))
    ]
    return rows, {**totals, "flag_threshold_deleted_chars": threshold, "flagged_paragraphs": len(rows), "chapters": chapters}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epub", type=Path, required=True)
    parser.add_argument("--min-deleted-chars", type=int, default=100)
    parser.add_argument("--jsonl", type=Path, help="Write one full review record per line")
    parser.add_argument("--markdown", type=Path, help="Write a grouped, readable review file")
    parser.add_argument("--summary-json", type=Path)
    args = parser.parse_args()
    rows, summary = scan(args.epub, args.min_deleted_chars)
    if args.jsonl:
        args.jsonl.parent.mkdir(parents=True, exist_ok=True)
        args.jsonl.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Large-deletion review",
            "",
            f"Threshold: at least {args.min_deleted_chars} source characters removed. This is a triage signal, not a judgment of semantic loss.",
            "",
            "| Chapter | Flagged paragraphs | Deleted chars | Added chars |",
            "|---|---:|---:|---:|",
        ]
        for chapter in summary["chapters"]:
            if chapter["flagged"]:
                lines.append(f"| {chapter['chapter'].replace('|', '／')} | {chapter['flagged']} | -{chapter['deleted']} | +{chapter['added']} |")
        for row in rows:
            lines.extend([
                "",
                f"## {row['chapter']} · {row['paragraph_id']} · -{row['deleted_chars']} / +{row['added_chars']} · {row['deletion_rate']:.0%}",
                "",
                "Original:",
                "```text\n" + row["original"] + "\n```",
                "",
                "Edited:",
                "```text\n" + row["proofread"] + "\n```",
                "",
                "Deleted fragments:",
                "```text\n" + "\n…\n".join(row["deleted_segments"]) + "\n```",
            ])
        args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(rendered, encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "chapters"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
