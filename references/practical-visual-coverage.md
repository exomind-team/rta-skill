# Practical lessons and visual teaching

Read for lesson classification, procedural illustrations, progressive frames, or a requirement to learn from the book without reopening course media. Preserve existing approved figures unless an identified issue requires revision. This reference defines a review method, not an automatic semantic validator.

## Discover lessons by teaching behavior

Inspect the complete publication scope, including examples, exercises, and question-and-answer lessons. Titles and keywords find candidates; neither a title lacking “practical” nor a keyword match decides the classification. Record `practical`, `not_practical`, or `unresolved` with source-based reasons. A sample lesson does not establish coverage of an entire course.

For each taught procedure, map only the components actually present in the source:

| Component | What the book needs |
|---|---|
| Goal and prerequisites | What the learner is trying to achieve and the required starting conditions. |
| Initial state | Relevant interface, body, equipment, material, or spatial state. |
| Critical action | What changes, where, and in what sequence. |
| Branch or constraint | Conditions that change the choice, order, or applicability. |
| Expected result | The observable output or state used to judge success. |
| Failure and recovery | Errors and corrections taught by the course. |

Link these items to source units, body paragraphs, and necessary figures. Record absent source components as gaps rather than filling every cell by invention. A tree-analysis lesson need not become an IDE tutorial simply because a programming tree appears on screen.

The table is a private coverage lens, not mandatory headings, a uniform lesson format, or a demand for the same number of states in every example. Preserve how this source actually teaches. Image counts can prioritize inspection but cannot establish that a procedure is understandable.

## Select states by teaching purpose

Use deck-extract for local candidates and the production workflow for commands, chronological metadata, crops, and timestamp checks. Inspect screen-sharing and physical demonstration scenes as well as conventional slides. pHash similarity, OCR rank, and the last frame in a sequence do not decide teaching relevance.

| Change between frames | Selection decision |
|---|---|
| Cursor, presenter motion, or incidental ink only | Usually keep one representative; confirm no meaningful annotation was lost. |
| Text builds toward one complete static explanation | Prefer a clear complete state when the build-up sequence itself adds no meaning. |
| Before/after states explain a modification | Keep both if readers need the contrast; describe what changed. |
| A short-lived dialog, intermediate result, or posture | Retain the necessary state even if a later frame looks more complete. |
| Distinct slides complete a conceptual comparison | One figure group, separate source images and timestamps, clear sublabels. |
| Error followed by correction | Preserve the sequence when it teaches diagnosis or recovery. |
| Transition, obstruction, or incomplete display | Seek a better source sample; do not repair unseen content by inference. |

Synthetic example: a lesson first shows a selected “Drafts” node, then a deletion confirmation, then a revised tree. One final tree picture cannot demonstrate all three states. Conversely, three frames differing only in cursor position do not teach three steps. Choose according to the procedure, not a fixed figure quota.

### A complete extraction run is not proof of visual coverage

A full-duration `deck-extract` run is a candidate inventory, not a faithful screen recording or proof that every teaching state was sampled. Sparse sampling, debounce, scene thresholds, repeated slides, and brief progressive UI states can leave holes even when every emitted file and manifest hash verifies correctly. In particular, an empty candidate window around a transcript anchor does not prove that nothing changed on screen.

For each visually dependent procedure and each P1 screen anchor, reconcile the candidate timeline against the reader/transcript locator. Inspect the nearest candidates, then verify the relevant source-video window with closer local sampling or direct playback. Check before, intermediate, and result states when the action depends on the transition. If the extractor missed a useful state, extract a directly verified source frame or record the visual gap; never substitute a much earlier/later frame as if it showed the anchored operation. For a requested complete page atlas, compare the retained pages with the visible sequence across the source video and record known omissions. Keep each timestamp's meaning explicit: a sampled frame time is not automatically the state onset, slide change, or audio/video synchronization point.

Report candidate coverage and verified teaching-state coverage separately. File counts, hashes, chronological sorting, and a successful full-course command establish integrity or candidate availability only; they do not establish that the book contains the visual information needed to follow the lesson.

For another invented example, two nodes are visible, a brief linking dialog displays separate direction fields, and a later graph shows a relationship. The temporary dialog may explain a choice that the final graph cannot show. Preserve it when needed, but do not infer an unseen click path, save action, automatic synchronization, or current software behavior from that state group. Source limitations should constrain the caption's claims as well as the prose.

Place required states beside the text that uses them. Keep exact source pages in the end atlas when requested and reuse identical packaged image resources. Do not make the learner search a full atlas to understand a critical body step. Grouped pictures must remain legible and stack at narrow widths; inspect the target reader rather than inferring usefulness from image resolution or valid paths.

## Match evidence without forcing agreement

Record source asset identity/hash, the depicted state, sample time or exact page, manuscript anchor, and why the figure supports that passage. The timestamp is a sample location unless a stronger temporal claim has been directly verified. Recheck anchors after substantive text changes.

Before first insertion and again after replacing or rebinding a figure, inspect the actual packaged image at readable resolution. Check that the visible tree title, branches, selected node, side panel, and current UI state agree with the nearby paragraph and with the caption/alt text; captions and alt text must describe the selected pixels, not an older frame, a filename, or an intended state. Anchor, hash, and timestamp checks prove identity and integrity, not semantic match. Correct or remove a stale figure claim even when its locator is valid.

A PPT page may be reused as a body illustration when its visible content directly supports the paragraph, even if no video sample time can be matched. Record the exact PPT page and atlas backlink, and keep video time `unknown`; do not imply that the page was visible at a particular point in the recording.

Give each medium authority only over what it shows: audio supports spoken words and acoustic turns; video supports visible actions, states, and annotations; a deck supports its own page content. ASR and OCR supply candidates. If a screen field says “Alias” while the transcript calls it a shortcut, retain the distinction or resolve it with explicit source review; do not manufacture a single consistent quotation. Similarity of topic or adjacent file order is insufficient to establish a match.

If a described photograph, interface, or posture is absent from the inspected sources, record what was checked and what remains missing. A cross-lesson figure may be offered as clearly labeled general reference, never as the missing subject of the current demonstration. Preserve the spoken guidance. Mark essential visual gaps as unresolved; do not claim that the complete lesson is reproducible or fill the gap with an invented image.

## Describe teaching-critical images for reading and Agents

Provide a concise identifying alt text. When essential meaning is not already carried by neighboring prose, add a checked description of the relevant labels and relationships: parent/child structure, arrows, comparison axes, marked changes, spatial arrangement, or action/result. Keep OCR transcription separate from inferred interpretation and identify illegible regions locally. Do not restate the entire chapter in every caption or dump raw OCR chrome into the reading flow.

Generate current Agent figure records from the approved figure map and manuscript. Distinguish image evidence from speech and editorial explanation. Link to the exact resource/page/frame and preserve unresolved differences. A chapter title plus an image filename is not an adequate description of a complex teaching diagram.

## Test book-only understanding

For a representative completed procedure, temporarily set aside the video and folded transcript. Using only the visible book, ask whether the learner can identify the start, perform the taught critical choices, recognize the result, and understand the provided reasoning. Check answers against the source. If a question exceeds the course, mark it out of scope rather than expanding the lesson silently.

Record the method and limits: an Agent walkthrough is not an observed human learning outcome, and a static posture image cannot establish that continuous motion or live feedback has been reproduced. Extend the review across every confirmed practical lesson before claiming full-course coverage.
