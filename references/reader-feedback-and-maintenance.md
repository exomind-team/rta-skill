# Reader feedback and post-delivery maintenance

Read this when a reader returns after receiving an EPUB or another RTA publication
with a problem, correction, usage result, or new preference. This is an explicit
feedback path, not telemetry: do not monitor readers or create a standing tracking
system. Keep any real feedback and review evidence in the private project workspace.

## Treat the report according to what it establishes

Feedback directly establishes what this reader observed or requested. It does not
automatically establish that the source is wrong, that a course claim is false, or
that every reader will have the same experience.

| Report kind | Example | First response |
|---|---|---|
| Reader display or navigation | A reading system drops a color cue or a link is hard to find. | Reopen the exact edition in the reported reader, theme, and device when available. Check the relevant navigation, XHTML, and style. |
| Text or editorial quality | A reader finds leftover stutter or supplies a clearer edit. | Compare the exact original, edited text, and diff. Separate a local correction from a reusable editing preference. |
| Source support | A caption, claim, or figure mapping appears unsupported. | Resolve the current source unit and inspect the cited evidence's identity and scope independently. A file existing or its digest matching does not prove that it supports this target. |
| Practical sufficiency | A reader cannot complete a procedure from the book. | Treat this as a real report about that attempt. Check whether the source shows the needed states and actions; do not fill gaps from general knowledge and mark the source as sufficient. |
| Edition preference | The reader wants a different comparison order, shorter link label, or deeper table of contents. | Record the preference against the edition and apply it to the requested revision; it does not require inventing a source claim. |
| Rights or privacy concern | A reader identifies exposed personal or restricted material. | Hold the affected asset or publication scope while checking the source and release boundary. |

## Follow the smallest traceable repair path

1. **Bind the report.** Identify the exact edition and EPUB SHA-256, then locate the chapter, EPUB href/fragment, source-unit ID, or figure. For a display issue, note the reader/version/theme only when known. If the target edition or location is unclear, ask only for the missing locator.
2. **Keep feedback separate from source evidence.** Preserve the reader's report in the private project note. Do not paste private feedback, personal history, course excerpts, or real identifiers into public Skill fixtures.
3. **Classify and reproduce.** Distinguish a content claim from a reader experience or preference. Reproduce against the named edition where possible. If it cannot be reproduced, say so and keep the cause unresolved.
4. **Return to the source when meaning is at issue.** Check whether the requested change is supported by the recording, transcript, slide, or authored source. A sampled frame supports a visible state at that sample; it does not establish the action between samples. A user-provided correction is a candidate until its source and intended editorial scope are understood.
5. **Limit the repair.** Preserve the previous publication. Revise only affected source records, prose, figures, style, or navigation. If the current edition has a project manifest, use its dependency bindings to invalidate only affected checks.
6. **Check the new candidate.** Run the validators required by the change and bind results to the new EPUB hash. Use `scripts/rta_scope_diff.py` with an explicit allowlist to detect unrelated ZIP-member changes:

   ```bash
   python scripts/rta_scope_diff.py --before prior.epub --after candidate.epub --policy project-local-allowed-changes.json
   ```

   `SCOPE_PASS` proves the package-member scope only; it does not prove semantic correctness. For claim checks, `scripts/rta_trial.py audit-claims --records normalized.jsonl --claims claims.json --reviews reviews.json` can verify an explicit review sidecar is bound to exact normalized input rows; `REVIEW_BINDING_READY_NOT_TRUTH_VERIFIED` still does not prove the reviewer was correct or actually inspected the source.
7. **Close the loop clearly.** Report the old and new edition identities, what changed, which checks ran and their scope, and anything still open. Distinguish “repaired and rechecked” from “reader confirmed.” Never say the issue is resolved for all readers based on one device or one person's experience.
8. **Generalize only when the evidence supports it.** A repeated or clearly reusable preference may become a Skill rule. Add only invented, minimal regression examples to the public repository; keep real course and reader evidence private.

Use the smallest existing project checkpoint or review note that can hold these
facts; do not create a second dashboard or make readers fill out a mandatory form.
If a project-local note is useful, record only what applies:

```text
Edition and EPUB SHA-256:
Target unit / EPUB locator:
Feedback category and observed effect:
Source check or reader environment:
Disposition and changed scope:
Checks rerun and their scope:
New candidate SHA-256:
Remaining uncertainty / reader confirmation:
```

## Synthetic end-to-end example

A reader reports that inserted text is hard to distinguish because their reader
does not preserve the EPUB's color styling. The report is bound to the exact EPUB
hash and paragraph anchor. The editor confirms that the wording and original-to-edit
diff are intact, adds a non-color cue to the inserted text, rebuilds a new candidate,
and uses `rta_scope_diff.py` to confirm that only the declared style/XHTML and
edition-metadata members changed. The exact target reader is checked again. The
report can then say “the package diff is in scope; the target-reader sample passed”
without claiming that every reading system behaves the same.

If a later reader says a pair of sample images implies a continuous action, keep
that interpretation open unless a continuous source interval or procedure replay
supports it. Rewording the caption to describe the two observed states is a scoped
repair; it does not make the action sequence known.
