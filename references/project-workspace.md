# Optional project workspace

Use for many sources, expensive rediscovery, repeated review, or a difficult handoff.
Small tasks can use the existing files directly. Like an optional code index, this
workspace accelerates navigation; it is not a prerequisite or a second orchestrator.

Reuse an existing inventory/checkpoint when it already answers these questions:
what scope is being published, where sources are, what is current, what passed,
what remains, and what to do next. Do not create a parallel management system.
Sources may remain at their original paths. An optional arrangement is:

```text
project/
  project.json          # Current references; one clear entry point
  manuscript/           # Editable records and chapter text
  assets/               # Extracted derivatives; originals may live elsewhere
  review/               # Scoped evidence and unresolved issues
  output/               # Readable EPUB milestones
  cache/                # Rebuildable optional index/preview material
```

These names are suggestions. Source kinds, tool choices and future steps remain
open-ended. The calling Agent selects and schedules tools, assigns one writer per
artifact, and coordinates resource use. Model providers are a project choice.

## Optional manifest adapter

`scripts/project_state.py` reads the following small schema. Unknown source kinds
and extra metadata are allowed. Relative file paths resolve from the manifest,
not the shell's current directory. Store remote URLs separately from local paths.

```json
{
  "schema_version": "knowledge-project/1",
  "project_id": "synthetic-study",
  "sources": [{"id": "source-a", "kind": "scanned_pdf", "path": "sources/a.pdf"}],
  "artifacts": [{
    "id": "chapter-a", "kind": "reading_manuscript", "path": "manuscript/a.json",
    "depends_on": ["source-a"],
    "checks": [{
      "kind": "source_to_text", "status": "passed",
      "scope": "chapter-a visible prose against source-a; no audio or figure review",
      "inputs": {"source-a": "<actual source SHA-256>", "chapter-a": "<actual manuscript SHA-256>"},
      "report": {"path": "review/a.md", "sha256": "<actual report SHA-256>"}
    }]
  }],
  "current": {"manuscript": "chapter-a"}
}
```

The digest placeholders illustrate the fields; they are not valid verification
values. Register applicable glossary/rule files and figure maps as dependencies
when they affect a check. Separate text, figure-map, style and package artifacts
so a CSS change does not invalidate an unchanged text review. Each stored check
must cover its target and declared dependency lineage; its report is also bound.

```bash
python scripts/project_state.py /project/project.json
python scripts/project_state.py /project/project.json --artifact chapter-a --verify
```

The first command is cheap reference inspection, not proof of unchanged bytes.
The second explicitly hashes the selected check's evidence. It never starts ASR,
OCR, a model, a task scheduler or network activity. Missing optional manifests
produce `NOT_PRESENT`, allowing work from actual files. Invalid manifests need
correction or bypass; they do not invalidate source content.

A reusable hash binding means a recorded acceptance still names the same evidence;
it does not independently establish the truth of the stored reviewer claim.
Do not change a reviewer result to passed because files exist or hashes match.
The adapter preserves `kind`, `scope` and `declared_status` separately. A legacy
check with no explicit kind/scope can have `binding: matched` but stays
`reusable: false`; inspect its existing report and record its real scope before
reuse. The adapter does not parse or endorse that report. Do not rerun the review
merely to recover a scope already stated there.
Even with `reusable: true`, reuse only that declared check within its examined
scope; compare it with the current required scope rather than treating this flag
as whole-chapter acceptance. Scope is reviewer metadata, not automatically endorsed.

## Incremental work and builds

Keep current references small; historical attempts stay private and need not be
loaded during ordinary work. Keep resolved findings attached to the reviewed
revision so they are not repeatedly rediscovered against a later file.

Edit and review structured chapter records before rebuilding an entire illustrated
volume for every wording fix. Generate a chapter preview when layout needs checking;
build the whole EPUB at a useful reading/integration milestone. Final package
validation still applies to the actual delivered EPUB. Reuse the same image bytes
for body figures and atlas entries.

Optional indexes are disposable derived material. Their absence or failure must
leave direct source reading, source validation and EPUB creation available. Do
not silently omit content because an index search returned no match.

Telemetry, stage ledgers and metrics-reading are off by default. If the user
explicitly requests a project-specific ledger, keep it limited to that project's
requested fields; this does not enable skill benchmarking. Use maintainer
experiments only for an explicit skill-performance investigation.
