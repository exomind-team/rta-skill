# Artifact-bound review and recovery

Read when work spans batches, resumes after interruption, or approaches delivery. Keep these private records outside the reusable skill repository. Use the smallest record that makes the actual dependencies and remaining work clear; this is guidance, not a new mandatory publishing service.

An [optional project manifest](project-workspace.md) can expose current references and component-bound review reuse. Work directly from existing paths when the adapter is absent or inappropriate. Do not create telemetry or a second tracking system merely to resume a book. Keep content acceptance, reading-edit completion and procedural learning checks distinct from mechanical validity.

## Bind conclusions to examined artifacts

A review should identify its lesson/source-unit scope, input hashes or immutable revision identifiers, method, findings, unresolved issues, and the output it validates. For a packaged candidate, record its EPUB SHA-256. Include figure-map and manuscript identities when they affect the conclusion. An older report, filename version, or folder called “final” is not evidence for a different artifact.

Carry check kind and examined scope into every acceptance summary, not just the
linked report. For example: “PASS — glossary replacements in three changed units;
oral editing, case retention and audio not reviewed.” Never shorten this to “lesson
review passed.” Reuse the existing report/checkpoint fields; missing scope is
unknown until the old report is inspected, not a reason to repeat the whole course.

Track checks separately: structural validation, source-to-text review, acoustic checking, procedure/figure coverage, Agent projection consistency, and target-reader inspection. “Second pass complete” must say which of these occurred. Do not label a self-review independent or a text-only review audio-verified.

Name checks for the behavior measured, not the desired conclusion. `pronoun_marker_scan` can report observed markers; it cannot certify `source_to_proofread_person_consistency`. A retained exercise keyword does not establish all exercise conditions or quantities. Link substantive acceptance to source-based review scope and findings. Keep `not_performed`, `pending`, `failed`, and a scoped pass distinguishable; do not fill an overall success field from file existence, expected counts, or a declared status. Resource hashes establish identity/integrity, not semantic truth. A target-reader finding applies to the inspected package and reader mode, not every rebuild.

An illustrative private record (field names may follow the project's existing schema):

```json
{
  "lesson_id": "sample-lesson",
  "artifact_hashes": {
    "manuscript_sha256": "<actual digest>",
    "figure_map_sha256": "<actual digest>",
    "epub_sha256": "<actual digest>"
  },
  "checks": {
    "text_source_review": "passed_with_linked_uncertainties",
    "audio_review": "not_performed",
    "target_reader": "pending"
  },
  "unresolved_ids": ["sample-uncertainty-01"]
}
```

Use real digests in project records; the illustrative strings above are not validation values. A passed check is scoped, not a certificate that the entire course is complete.

## Invalidate only affected checks

| Change | Checks to revisit |
|---|---|
| Edited wording or source-unit split/merge | Meaning, source correspondence, diffs/counters, affected figure anchors, current Agent text, changed layout. |
| Figure choice, timestamp, crop, or anchor | Source identity, evidence/time semantics, local references, relationship descriptions, coverage and target-reader layout. |
| CSS or disclosure structure only | Affected XHTML, no-JS/default collapse, theme contrast, selection and annotation behavior; preserve unrelated semantic checks. |
| Source media/transcript replacement | Establish a new named source layer; revisit all dependent assertions instead of silently replacing the frozen baseline. |
| Relevant editing rule or glossary changed | Recheck only the affected acceptance scope, even if prose bytes did not change. An unrelated skill/documentation revision does not invalidate content or image reviews. |
| Rebuilt EPUB | Validate the actual package and bind delivery/reader checks to its hash; reuse unchanged component reviews only when dependency identity is established. |

Derive progress and summaries from current records where feasible. A mismatch between an audit's anchor and the EPUB is a stale-evidence issue to resolve against the current candidate, not a reason to trust either blindly. Stable IDs plus a short quote/context can assist relocation; they do not guarantee migration of reader-specific annotations.

Keep one current entry showing the readable artifact, accepted/pending scopes and
next visible result. Derive its counts from that edition's records; a historical
purpose/status sentence must not override newer current references. Do not combine
package validity, editorial cleanup, source coverage and reader inspection into
one completion percentage or add another dashboard to explain them.

Keep those relocation quotes, surrounding context, and hashes in private records or appropriate non-displayed metadata; do not repeat them in the reading flow. See [reader experience](reader-experience.md) for reader-facing uncertainty and source navigation.

## Resume and hand off with the next action visible

Read this section when a session resumes, an application restarts, or another authorized worker takes over. Reuse one small project-local checkpoint or current manifest; do not create a parallel tracking system merely to satisfy this list. It should let the next worker find:

- the agreed product, publication scope, edition policy, and the current bounded milestone;
- the verified source inventory and the exact current manuscript, figure map, Agent projection, and candidate paths/identities where they exist;
- completed checks and their actual scope, linked uncertainties, stale or pending checks, and real blockers;
- the last verified checkpoint, a concrete next action and command/tool path when useful, and who owns an output if concurrent work exists;
- the active resource constraints and the task-owned temporary resources eligible for later cleanup.

This is a recovery aid, not a mandatory book section, chapter template, or permission to message other tasks. Do not restart processing or duplicate downloads from a stale progress sentence. If nothing executable is currently running, do not infer that all artifacts are absent or invalid. Inspect the checkpoint and its referenced outputs, verify the affected dependencies, then resume the smallest useful unfinished step. Keep historical logs privately without making the current checkpoint narrate every past attempt.

## Recover verified work, not optimistic status

After interruption, inspect the current inputs, output manifests, referenced assets, and last successful checkpoint before resuming. An exit code, file existence, growing length, or old `complete` status alone does not prove completion. For frame batches, compare source fingerprints and extraction parameters and verify referenced nonempty files; validate recorded sizes and hashes when present. Legacy manifests without hashes support only existence-based checking, which must not be described as hash verification. A source path/size/mtime fingerprint is not a source-content hash.

The bundled extractor records per-frame sizes and SHA-256 for new results. Its batch helper refuses to skip missing, truncated, or hash-mismatched outputs. It preserves conflicting completed directories for inspection rather than overwriting them automatically. Avoid rerunning expensive media extraction solely because a progress note is stale.

When implementing new output writers, write to task-owned staging paths, validate before promotion, and keep failed artifacts distinguishable from candidates. Existing helpers may have weaker post-write validation; inspect the helper before claiming transactional publication. No guarantee here covers concurrent writers: coordinate a single writer per output and do not replace another task's files.

## Deliver readable milestones without expanding the critical path

Identify the next useful EPUB before opening more research branches. A bounded chapter preview or a coherent full-volume candidate may be appropriate according to the agreed task. Preserve source fidelity and required teaching figures within the declared coverage; do not call a picture-only atlas or an incomplete selection a finished course. Never remove examples or essential visual steps merely to meet a delivery date.

At the milestone, give a real EPUB path and identity, covered lessons, meaningful changes, and a brief honest statement of remaining checks. If superseding a previously shared preview, use a distinct candidate identity/filename while preserving the user's requested book version. Unperformed target-reader inspection, acoustic checks, or optional conformance tools must not be reported as passed. Required final checks still gate the final claim; a clearly scoped preview can be useful before those are complete.

Optional application stories, new ASR comparisons where a usable source already exists, a broader historical-source search, or a new general tool should not hold a readable milestone indefinitely. Keep them in later work unless they resolve an actual teaching-completeness blocker. Integrate completed, independently reviewed pieces instead of repeatedly reopening them without a changed dependency. Changing skill instructions alone does not update any existing EPUB or validate an older candidate.

Run [reader review samples](reader-experience.md) for relevant layout changes, then inspect representative content in the target reader when available and authorized. Record the delivered edition rather than relying on an older successful sample. Do not start an import, a reader preference change, or another task's work merely because it would help validation.

## Resources and cleanup

Run one heavy media pipeline at a time by default; inspect current physical RAM, CPU load, and available disk on the actual output/cache volumes. Follow user/project thresholds rather than embedding one machine's limits in the reusable skill. Reduce batches or checkpoint and pause when needed; do not infer a crash diagnosis from resource percentages alone.

Before cleanup, distinguish sources, current deliverables, minimal reproduction/evidence records, and rebuildable intermediates. Verify the final deliverable and its dependencies first. Delete only task-owned material within verified paths and already-authorized scope; release only this task's ended processes or model instances, never unrelated applications or shared caches. Do not automatically cancel another task's timers or agents. Preserve sufficient source IDs, hashes, parameters, and decisions to reproduce the edition without retaining every failed preview.

## After-delivery feedback

When a reader reports an issue after delivery, use
[`reader-feedback-and-maintenance.md`](reader-feedback-and-maintenance.md). Keep
the report tied to the exact EPUB hash and locator, then invalidate only the
dependent checks. A package-scope pass or metadata label is not a semantic or
reader-experience pass. Keep real feedback private and add only generic synthetic
regression cases to this Skill.

## Release assertions and limits

Check the actual package, not just upstream JSON: ZIP/XML, metadata/navigation, local references, frozen original/current text reconstruction, diff counters and collapsed defaults, preserved assets, required inline states, end-atlas order/resource reuse, a visible `sample_time` or explicit unknown status on every atlas page, current-only Agent projection, and no JavaScript. EPUB conformance tools do not establish teaching completeness or correct image placement. Inspect the target reader for the edition actually delivered; import to Zotero only within the user's edition-specific authorization.

Where semantic evaluation is needed, keep small invented challenge cases for swapped-but-fluent paragraphs, lost negation, changed claim strength, unsupported causal additions, or mismatched figure subjects. Evaluate them from the source; do not replace semantic review with keyword assertions or claim automated tests prove meaning preservation. Technical regression tests should exercise observable failure behavior such as a missing referenced frame or an altered asset after a prior successful batch.
