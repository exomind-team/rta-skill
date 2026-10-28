from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile
import importlib.util

SKILL = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL / "scripts" / "audit_deletions.py"
spec = importlib.util.spec_from_file_location("audit_deletions", MODULE_PATH)
assert spec and spec.loader
audit_deletions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_deletions)


class AuditDeletionsTests(unittest.TestCase):
    def test_ignores_non_comparison_details_in_full_book(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            epub = Path(directory) / "sample.epub"
            xhtml = b'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body>
<h1>Sample lesson</h1>
<details id="note"><summary>Ordinary note</summary><p>Not an original comparison.</p></details>
<details id="p001" class="source-comparison"><summary>Original +1 -1</summary>
<blockquote class="comparison"><p class="diff">A<del class="diff-deleted">B</del><ins class="diff-added">C</ins></p></blockquote>
</details>
</body></html>'''
            with zipfile.ZipFile(epub, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("OEBPS/chapter-001.xhtml", xhtml)

            rows, summary = audit_deletions.scan(epub, threshold=1)

            self.assertEqual(summary["disclosures"], 1)
            self.assertEqual(summary["deleted_chars"], 1)
            self.assertEqual(summary["added_chars"], 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["paragraph_id"], "p001")
            self.assertEqual(rows[0]["original"], "AB")
            self.assertEqual(rows[0]["proofread"], "AC")


if __name__ == "__main__":
    unittest.main()
