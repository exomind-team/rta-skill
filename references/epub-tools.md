# EPUB helper contracts

Read for static comparisons, course-scoped terminology normalization, or helper
behavior. Use reader experience for presentation choices and production workflow
for a complete book. A format-only revision preserves the chapter/figure arrangement.

## Static original-to-edited comparison

```bash
python scripts/epub_static_diff.py --input source.epub --output revised.epub
python scripts/audit_deletions.py --epub revised.epub --markdown deletion-review.md --jsonl deletion-review.jsonl
```

The comparison helper expects each source paragraph as `blockquote > p.original`,
with its edited `p.rewritten` immediately after the blockquote. An original-only
block is treated as unchanged. This is a helper input contract, not a required
source format or permission to pair unrelated paragraphs. Adapt other layouts
explicitly and validate paragraph/source correspondence before using it.

The helper displays edited prose by default and gives changed pairs a native,
initially closed `details.source-comparison`. `原文 +N -M` counts characters added
and removed in the direction original → edited; unchanged paragraphs receive no
empty disclosure. Preserve the user's requested placement of the original entry
and edited prose. By default, place the collapsed entry right-aligned immediately
before the proofread paragraph. Follow the user's requested placement.
Keep editorial notes outside source blockquotes, and explain
recurring conventions once rather than labeling every paragraph.

Differences are precomputed with `diff-match-patch` and serialized as XHTML nodes,
with special characters escaped. Do not paste a library's unchecked HTML string.
Keep additions green and bold without underlining, deletions red and struck
through, and equal text uncolored. Bold/strike-through remain usable if the reader
suppresses colors; underline can be mistaken for reader annotations. Test actual
light/dark reader modes rather than assuming stylesheet values are rendered.

The EPUB must use no script elements, JavaScript event attributes or runtime diff
calculation. Validate original and edited reconstruction, source pairing, counters,
default collapse, asset identity and unaffected structure. Reconstruction proves
the paired strings, not their semantic correspondence or source coverage.

The deletion auditor examines only `details.source-comparison`, leaving ordinary
notes alone. Its default 100-character threshold is adjustable; review output
includes originals, edited text, deleted fragments and chapter locators. Counts
triage review and never establish that a deleted example or condition is dispensable.

Run the spoken-text lint after each editing batch:

```bash
python scripts/audit_oral_editing.py --input reader-editor.json \
  --output-json work/oral-lint.json --output-markdown work/oral-lint.md --strict
```

It flags paragraphs lexically unchanged from source/ASR after punctuation is
removed, `呃`/`嗯`, repeated filler runs (including `啊啊`), and selected adjacent
repetitions. It does not flag ordinary sentence-final `啊`. This is a deterministic
review queue, not an auto-cleaner: affirmative responses, emphasis, self-correction,
and meaningful particles may be valid. Resolve findings in the text or write
project-local `{"decisions":[{"finding_id":"…","context_sha256":"<digest from the finding>","decision":"keep","reason":"…"}]}`
entries for contextually reviewed retentions, then rerun with `--decisions` and
`--strict`. Do not place real excerpts, course paths, or adjudication records in
the reusable skill. `oral-edit-lint/1.1` retains punctuation-only signals as `info`
and counts them separately; they do not block `--strict` or require keep entries.
Residue without a current bound keep remains open and returns exit code 2. Old
unbound keeps do not close it. Revalidate their actual local context before copying
the digest; never auto-stamp old decisions. The digest covers source/prose and
immediate neighbors, using lesson/source identity where available. Supply a stable
course/lesson ID for movable inputs without source metadata; otherwise the parent
directory is the fallback namespace. Unrelated chapter edits and candidate filename
changes do not invalidate a local decision. If a reason depends on more distant
context or a changed editorial rule, revisit it explicitly. The Markdown queue
groups residue signals by paragraph; exact spans and IDs remain in JSON.
A clean lint is not proof of fidelity, adequate editing or source coverage.

## Apply an explicitly approved terminology rule

```bash
python scripts/normalize_epub_terms.py --input source.epub --output revised.epub --rules work/glossary.json --report work/normalization-report.json
python scripts/normalize_epub_terms.py --input source.epub --output layout-revised.epub --layout-only --report work/layout-report.json
```

The private rule file contains `canonical`, `variants`, and optional
`protected_following` suffixes for distinct longer words. The helper changes only
visible `p.proofread` text, leaves source quotations and linked uncertainty markers
intact, rebuilds paired static diffs, and checks reconstruction, counters, image
counts and JavaScript absence. Review paragraph IDs and variant counts; update
uncertainty notes and other dependent manuscript/Agent records separately. Do not
assume this EPUB helper updates the upstream manuscript automatically.

Use `--layout-only` when existing source-comparison entries need repositioning but
no terminology edits are requested. It moves a `details.source-comparison` from
after its matching proofread paragraph, including across an intervening editorial
uncertainty-jump paragraph in the same block, to immediately before it. Stable IDs
and the revised-side text must match. It leaves all text/diff/image bytes unchanged
and installs the right-aligned reader style. Ambiguous or unpaired comparison
blocks stay in place and appear as layout exceptions; review those before claiming
the migration is complete. Ordinary disclosures are ignored. The report separates
moved pairs, package-wide revalidation and unresolved layout exceptions.

Keep real course glossaries and transcripts outside the reusable skill. The
synthetic `tests/test_normalize_epub_terms.py` checks implementation behavior, not
whether a terminology rule was appropriate for a particular course.

## Actual delivery boundary

Validate the actual package and inspect the target reader. A browser or synthetic
test complements that check. Preserve annotation-bearing versions; verify a
Zotero stored attachment against the delivered local SHA-256 when import is
authorized. Check its full-text indexing cap before claiming late chapters are
searchable. Do not change shared reader preferences as a side effect of validation.
