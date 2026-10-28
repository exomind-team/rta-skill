# Course editions and source relationships

Read when continuing a book across versions, comparing cohorts, replacing a source, or combining course editions. A publication revision and a course/source edition are separate identities. Keep acquisition/download tooling outside this workflow; receiving another file does not authorize cloud processing or replacement of a published attachment.

## Establish what changed

Identify the prior and current book version and artifact hash, course/cohort, lesson, recording identity, available ordering/date evidence, and source hashes before replacing material. A higher book version does not establish a new cohort, and a newer cohort is not merely a newer book revision. Similar titles, higher resolution, and recent download times do not establish the same recording or a newer course. Classify the actual source relationship:

| Relationship | Consequence |
|---|---|
| Same recording, different encode/resolution | Verify representative content and any timing offset; a cleaner image can replace its matched counterpart. Do not assume identical timestamps after edits or trimming. |
| New recording/cohort of the same course | Align teaching content before merging; give it an independent source identity. |
| Slides, audio, transcript, or notes derived from a recording | Record the parent and derivation where known; preserve separate medium identities. |
| Student notes or second-hand compilation | Use as a lead or explicitly attributed supplement, not proof of the teacher's speech. |
| Unknown relationship | Preserve both, investigate only the part needed, and do not silently substitute. |

Keep page identity, paragraph correspondence, temporal alignment, and interpretation as separate findings. A high-confidence page identification may still have unknown video time. A verified image hash proves identity, not the proposed caption or conceptual relationship.

## Reuse verified work across book versions

Start from the last accepted manuscript, EPUB, source map, and review evidence. Carry a verified unit forward when its source identity and the dependencies behind its acceptance are unchanged. Reuse the existing source hash, stable IDs, approved glossary/rules, candidate identity, and review report; reopen only the affected unit and downstream outputs when one of those dependencies changes. A filename or matching lesson title alone is not evidence that prior work still applies.

Keep source identity distinct from publication identity. A corrected proofread paragraph based on the same recording is a book revision: compare it with that recording's frozen source and preserve the earlier publication snapshot. A re-recorded lesson or another cohort is a different source edition, even when it teaches the same concept. It needs its own source IDs, hash, locators, and transcript/review evidence. Reuse a prior explanation as a mapping or research lead, not as the new cohort's source text.

For cross-version comparison, retain both publication identities and create the smallest useful unit map between them. Label each relation as unchanged on the same source, editorially revised on the same source, re-recorded or cohort-changed, added, retired, or uncertain. Keep source changes and editorial changes as separate deltas. A static original-to-edited `+/-` diff is appropriate only when both sides derive from the same frozen source unit; across cohorts, show an attributed edition comparison or parallel excerpts and do not present different lecturer wording as an editor's change. Keep uncertain alignments visible instead of forcing a match.

## Use a newer backbone where the course is substantially continuous

For closely related cohorts, prefer the verified newer course's structure and current explanation as the backbone when consistent with the user's edition preference. Compare actual teaching units, not titles alone. Map equivalent explanations, older-only cases/exercises, updated procedures, explicit retractions, unresolved contradictions, and genuinely new material. Use the smallest useful mapping; this is a private alignment aid, not a requirement to reshape every lesson.

Retain useful older-only teaching content as a compact, explicitly attributed insertion at its conceptual location. For example, a short label such as `往期补充·某期` can identify the source without repeating an editorial notice in every paragraph. Explain the convention once at the front. Keep its original voice, its own frozen transcript/diff, source IDs, and matched images; never synthesize a single allegedly spoken paragraph from two recordings. If no natural insertion point exists, use a linked supplement rather than interrupting a procedure.

An older menu, recommendation, or claim that the newer course changes must remain historical or be contrasted explicitly. Do not present both as simultaneous current instructions. If the sources do not resolve a contradiction, preserve attribution and uncertainty; do not invent reconciliation. Updating the software description is a distinct editorial layer, not permission to rewrite historical speech as current behavior.

## Decide when to make separate books

An initial project policy can be: newer backbone plus marked older-only supplements while the course remains substantially aligned; prefer separate EPUBs when more than about one third of comparable chapters are materially reorganized. Apply the user's chosen policy without asking again for routine placements, and retain the estimate and reasons privately.

The one-third boundary is a practical signal, not a universal score or a blind release switch. First align equivalent chapters, accounting for splits and merges. A single added opening chapter does not make every later chapter “reordered” just because its numeric position shifts. State the old/new chapter counts, comparison granularity, affected units, and uncertainty. Assess changes to teaching sequence and prerequisites, not only renaming. With ten comparable units and four materially reorganized units, the initial policy favors separate books; with one newly inserted opening unit and nine continuing in their prior order, do not count nine moves. These counts are invented examples, not automatic formulas.

Major changes in assumptions, audience, or procedures can also make an integrated book confusing despite a small chapter count. Explain the exception and keep edition boundaries visible instead of manipulating the denominator to force a preferred result. When evidence is insufficient, deliver the verified backbone as a bounded candidate and keep the disputed merge pending rather than silently mixing or blocking the whole book.

## A synthetic reader story

A fictional workshop's newer cohort teaches a revised folder workflow. A prior cohort also contains a useful case about recovering a wrongly filed sketch; the newer recording never discusses that case. A combined book follows the newer workflow, then inserts the older case at the relevant decision with a brief cohort label. Its old screenshot remains identified as an earlier interface. The reader can follow one main course and still benefit from the unique case, without mistaking the old menu for the current one. If the newer cohort instead teaches a different prerequisite sequence across much of the course, two independently navigable books preserve that distinction better.

This story explains a decision, not a required narrative format or evidence about a real course.

## Keep the current edition interpretable

Namespace locators by recording/cohort so identical lesson or paragraph numbers cannot collide. Keep the cross-version map with the private project evidence; do not merge prior drafts or review history into the current Agent projection. Record links from retained supplements to their source and backbone location. An older-course supplement intentionally included in the current book belongs in the current Agent export with its historical attribution; superseded draft text and editorial iteration logs do not. See [editorial fidelity](editorial-fidelity.md) for person consistency, [atlas evidence](atlas-and-date-evidence.md) for time limits, and [review/recovery](review-and-recovery.md) for affected checks.
