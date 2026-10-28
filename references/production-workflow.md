# Knowledge-publication production workflow

Use this reference when producing a complete study book or coordinating more than one source type. Keep the main skill entrypoint concise; this file carries the details that do not apply to every EPUB edit.

## 1. Inventory and source map

Use [source routing](source-routing.md) for PDFs, websites, authored material, or mixed sources. Reuse a sufficient existing source list; a small task does not require a new project framework. An [optional project manifest](project-workspace.md) helps when discovery or repeated review is costly. For the declared publication scope, record the necessary subset of:

- transcript files and their lesson/chapter relationship;
- requested published articles/essays, original article metadata, local HTML/Markdown capture, and referenced image assets;
- video source, duration, and any known transcript timestamps;
- slide decks and page counts;
- available prior manuscript or EPUB versions;
- the destination for editable text, media extracts, preview, and final EPUB.

For new source replacements or related course cohorts, read [course editions](course-editions.md) before combining sources. Establish same-recording variants, new recordings, derived materials, and second-hand notes independently. A newer backbone with labeled older-only supplements can preserve one readable course; substantial restructuring may call for separate books under the agreed edition policy.

Map each manuscript paragraph to a stable paragraph ID and source locator. Map figures to a slide page or a verified video timestamp. If a timestamp cannot be established, cite the slide or say the timing is unknown. The file's position in a folder is not temporal evidence.

Keep a public article's author, original title, publication/update date, account, URL, capture path, and source hash as its own source identity. Article publication dates are not course recording dates. When such articles are requested for the opening, place them before the lesson sequence as clearly attributed chapters; keep their original order and voice, and explain the source convention once rather than calling them transcripts or merging their claims into the lecture layer. See [`published-article-sources.md`](published-article-sources.md) for completeness and asset checks.

Treat attached handouts, reading lists, and tool guides as authored sources separate from spoken-course text. Record each file's hash, title, source date when known, page count, and page-level extraction/render provenance. Use page text or OCR to locate possible course relationships; a shared module title, chapter number, or topical match alone does not establish a page-to-lesson mapping. Keep cross-course citations, Agent-generated examples, and independent reference lists in separately attributed appendices unless the lecturer actually teaches them as part of the course. For a text-based PDF, a page-numbered text layer can be a compact, searchable appendix; label it as extraction if it has not been editorially checked. Add full page images where visual layout, diagrams, or exact page appearance carry meaning, and make the page index, image, and current Agent record point to the same stable source-page ID. A handout's unvisited hyperlinks remain unverified references, not current tool recommendations.

Treat each source ID as a content-correspondence contract, not only a diff anchor. Check that the proofread wording under that ID actually derives from the same source unit and that neighboring units have not been shifted, duplicated, or omitted. A reversible row-level diff can still pass when the wrong proofread paragraph is paired with an ID, because it tests the strings rather than their semantic correspondence.

## 2. Manuscript and editing

Keep the lesson sequence the user requested. Establish the book's conventions in a short preface: what the body contains, how headings were assigned, how uncertain transcription is shown, and how figures are sourced. Do not repeat the same editorial explanation in each chapter.

Keep distinct editorial layers. A source paragraph may be followed by a revised paragraph, or a comparison edition may expose the original only after a user expands a disclosure. Stable source IDs must survive either layout. Preserve a record of material edits and unresolved words outside the reader flow.

Use source-shaped, reviewable batches with needed neighboring context and explicit source-ID ownership. These are processing boundaries, not a fixed teaching or paragraph template. Preserve person consistently with the source, including impersonal statements, singular/plural voice, questions, and quoted speakers; do not manufacture first-person intention.

For a user-approved course glossary, normalize only the current proofread projection. Preserve the source layer and original side of every comparison. Guard genuine longer words that share a prefix with a homophone; keep the glossary and correction manifest in the private work area. Mark a lexical uncertainty resolved only when the approved rule fully answers it; if the record contains another ambiguity, retain that remainder and annotate only the term resolution.

For books with complete slide atlases, keep the lesson chapters in one uninterrupted reading sequence. Put a short index near the beginning that links to the Agent-reading guide and each atlas appendix; put the guide in the back matter immediately before the atlases, and place the full atlases at the very end of the reading order. The Agent-readable export is a projection of the current edition only: current proofread text, stable IDs, and current locators. Keep superseded editions, prior baselines, and iteration/change history in private working records, not in the book's current Agent export.

Make time status explicit on every atlas page: an accepted page-specific `sample_time` or `视频采样时间：未知`. A blank timestamp line does not tell the reader whether the page was checked. After building the package, run `python scripts/label_atlas_times.py --input source.epub --output labeled.epub`, then `python scripts/label_atlas_times.py --input labeled.epub --check`. This helper reads page-level XHTML metadata and adds only a visible status line; it neither finds matches nor verifies their evidence. Continue with normal ZIP/XML, metadata, asset-hash, and target-reader validation on the labeled output.

For factual or dense course material, distinguish the lecturer's claim from an externally checked fact. A transcription cleanup does not itself verify a lesson's research, dates, software versions, or causal claims.

Use [reader experience](reader-experience.md) to decide which metadata belongs in ordinary reading, consultation layers, Agent records, or private debugging files. An optional application index or vivid editorial scenario must preserve the source presentation and disclose its derivation; it is not a prerequisite for delivering the course text.

### Incremental reuse, preflight, and batching

- When a lesson or asset has passed review, register the frozen-source, applicable rule/glossary, candidate, and review-report hashes. Reuse the accepted chapter while those dependencies stay unchanged. Reopen only the affected lesson or downstream artifact when a dependency changes; do not re-run expensive media extraction just because the session resumed.
- Run schema-specific structural preflight before independent semantic review. For the bundled reader-editor v1–v3 contract: `python scripts/validate_reader_editor_candidate.py candidate.json --report review/preflight.json`. The supported names are `reader-editor/1.0.0`, `reader-editor-v2` and `reader-editor-v3`; an optional lowercase alphanumeric/hyphen project prefix is accepted for existing inputs using this same contract. A namespace does not select a different schema or bypass checks. Add `--markdown candidate.md --require-markdown` only when that companion manuscript is part of the actual build/review route. Other contracts/versions return `NOT_APPLICABLE_SCHEMA`; use matching checks, not a false content failure or a forced intermediate format.
- The bundled preflight verifies source paths/hashes, exact-once IDs across body/dispositions, source order and raw reconstruction, punctuated-ASR reconstruction from its own layer, both diff replays, empty-diff consistency, unique normalization spans at their diff-projected positions, section/reference closure and declared counts. Flattened section record IDs must equal paragraph order; assignments and source ranges cannot move backward or overlap. Active uncertainties need nonblank spans, exact source anchors and reader links. Resolved/empty entries belong outside the active uncertainty layer.
- When companion Markdown is used, each section/record/uncertainty anchor occurs once in candidate order and uncertainty targets/counts match. **Each whole anchored prose block must match its candidate `reader_text`, not merely contain the expected sentence.** This narrow projection permits HTML inline presentation, entities and whitespace normalization, and excludes closed `<details>` source blocks; inline Markdown stays literal on both sides. It is not a general Markdown renderer. Keep ancillary headings/figures/notes outside the record block or use the actual renderer's scoped check. Missing/mutated/extra body text fails even when anchors and links still pass.
- For direct JSON → XHTML or another layout, validate record-by-record body text in that actual render layer and its current Agent export. Do not create unused Markdown just to invoke this helper, or assume its pass checks an EPUB it never opened. Candidate/Markdown and validator hashes identify exactly what the helper examined. Mechanical PASS does not establish editorial cleanup, case retention, semantic/acoustic fidelity, visual teaching coverage or reader behavior. Fix relevant failures before review; rerun only affected checks when inputs or checker behavior change.
- After stripping only ` [†](#...)` uncertainty-link tokens from each `reader_text`, require the remaining body to equal `proofread_text` exactly. The presentation diff must not introduce or restore wording; link target and count validation remain separate checks. This prevents a replay-valid but stale reader projection from replacing edited lesson text.
- After building the EPUB and freezing the current Agent JSONL export, run `python scripts/validate_epub_projection.py --epub candidate.epub --agent-jsonl agent-readable-current.jsonl --report review/epub-projection.json`. Add `--page-atlas-manifest page-atlas-manifest.jsonl` when the package has a complete slide-page atlas. This read-only check validates ZIP CRC and the required EPUB `mimetype`, parses packaged XML, matches body-figure IDs and chapter locations to current `body_figure` records, checks present source ID/unit attributes, image hrefs/bytes/declared alt text, resolves each uncertainty locator to exactly one nonempty target, compares appendix sections with current uncertainty records, and checks any displayed `N项未决记录` count. With a slide-page manifest, it also reconciles page anchors and page sets in the manifest's atlas documents and verifies each displayed page-image href and SHA-256. Video-frame galleries are separate unless represented in that source-page manifest. The helper currently recognizes root-level `record_type` values `body_figure`, `uncertainty`, and `source_page`; nested envelopes or other schemas return `NOT_APPLICABLE_SCHEMA` instead of treating zero recognized records as a pass. Use a matching schema-specific adapter/check for those exports. Run this after package assembly and before release review; repeat only when the EPUB, current Agent export, atlas manifest, or checker changes. A PASS proves these mechanical bindings for the supplied files only. It does not prove semantic completeness, audio truth, video timing, practical-step sufficiency, image usefulness, reader behavior, or rights clearance. The JSON report names those limits; keep its status and scope intact when reporting progress.
- When a page-atlas manifest gives local source paths, the projection validator checks external SHA-256 values when those files are available. `pptx_path` pairs with `pptx_sha256`; `source_image_file` pairs with `source_image_sha256`; `uncropped_render_file` pairs with `uncropped_render_sha256`; `full_page_image_file` uses `full_page_image_file_sha256`, or falls back to the uncropped digest only when both fields name the same file. The packaged display image remains checked separately through its EPUB href and `full_page_image_sha256`. Relative paths resolve beside the manifest first, then under each supplied `--external-asset-root`; pass one root per extraction/source base when required. A reachable file with a mismatched digest fails; an external path that is missing, belongs to another platform, or has no digest is reported as a warning because the package may still be structurally usable while its external source closure is unverified. These checks establish byte identity only, not source legitimacy, timestamp correctness, or visual teaching value.
- Validate an Agent uncertainty projection against the packaged book, using the current output contract without assuming a universal JSONL schema. For each body uncertainty ID, follow its actual chapter href/locator to the note target; keep resolution scoped to the current volume and source ID because short IDs may repeat across sources or volumes. Where a format stores IDs without inline hrefs, resolve them through the corresponding chapter/source locator within that same scope. Require exactly one matching current record per body reference, a real target file and fragment, and nonempty explanatory text that lets an Agent understand and back-check the issue. If the format exposes target_found, derive it from that actual lookup. Check the reverse direction too: reject cross-volume records, missing records, duplicate/ambiguous targets, and unreferenced aliases. Do not let a global dictionary keyed only by a bare ID overwrite one source's note with another's; compare the record's source identity, text, and locator with the exact linked XHTML entry.
- For a legacy or unsupported candidate schema, the matching targeted gate must replay both text layers independently: frozen source → proofread text, then proofread text → reader text. Require each replay to equal the corresponding visible string, and verify every remaining reader link resolves to its active uncertainty record. When resolving an uncertainty, remove its stale display-layer diff and link as well as its register entry; a correct source diff alone does not prove that the reader view is current. Keep this a scoped mechanical check, not a semantic or acoustic PASS.
- Before independent text review, run the existing spoken-text lint on changed records, with repeated `--input` for a batch and `--strict` for the residue gate. Reuse the current context-bound decisions and accepted review evidence where dependencies match. Resolve meaningful case/condition/causal omissions through [source-to-book and book-to-source review](editorial-fidelity.md), not a lint score, deletion threshold, or source-ID count. Preserve the review's check kind and exact scope in batch summaries.
- Process independent lessons in reviewable batches. Keep one writer per artifact; while an independent reviewer checks a preflight-passed lesson, the editor can prepare the next batch. Final release uses only components accepted for the promised scope. A clearly identified chapter or volume preview may include pending review scopes and local gaps; do not present a REVISE/pending component as accepted. Follow [readable milestones](review-and-recovery.md#deliver-readable-milestones-without-expanding-the-critical-path) rather than withholding every preview until final release checks are complete.
- Run frame extraction, slide-atlas preparation, and OCR as a separate candidate lane when useful. Reuse existing verified outputs when source and tool/parameter hashes match. Keep candidate images and OCR separate from accepted figures; bind images to stable paragraph IDs only after the text passes, and confirm teaching purpose, privacy, and exact image identity before insertion.
- Telemetry is off by default: do not require the publishing Agent to keep stage metrics, repeatedly read logs, or explain every elapsed interval. If the user explicitly requests a project timing ledger, record only the requested fields; that is project reporting, not a skill benchmark. Existing tools may retain natural run metadata. Use [maintainer experiments](maintainer-experiments.md) only for explicitly requested skill-performance diagnosis/optimization. A project-specific time goal by itself does not enable detailed telemetry.
- Review structured chapter records before rebuilding a large illustrated volume after every wording fix. Use a chapter preview when layout needs checking, and a complete EPUB at a useful reading/integration milestone. Reuse unchanged component acceptance by its actual dependency identity; the final delivered package still needs its own structural and target-reader checks. Keep closed findings tied to their examined revision so a stale omission report does not trigger duplicate edits.

## 3. Illustration selection

Start with the actual gap, not another full image pass. If source, image, purpose,
anchor and relevant review dependencies are unchanged, reuse the accepted mapping.
Locate new or uncertain evidence through existing slide text/OCR, captions, page
and time records first. Read only the relevant pixels to establish a new teaching
figure or settle an unresolved relationship; use a local video window when the
required transient state is missing. Detector silence is not evidence of absence.
Reuse the resulting mapping in body, atlas and Agent descriptions. Requested full
atlases still retain all source pages; cost savings come from avoiding repeated or
unrelated reads, not silently omitting pages. Decide whether an action is taught
or merely incidental before expanding it into a procedure or collecting more frames.

Generate contact sheets or slide thumbnails when a deck has many pages. Candidate images should explain the neighboring text, preserve legible labels, and carry a concise caption plus the source page or time. Avoid uncertain timestamp matches. After insertion, inspect representative chapters at normal and narrow reader widths; don't assume a valid image path means a useful figure.

### Practical-course visual coverage

Use [`practical-visual-coverage.md`](practical-visual-coverage.md) for full-scope classification, goal/action/result mapping, progressive-state selection, missing visual evidence, and book-only walkthroughs. Required teaching states belong beside the prose; an end atlas and a fixed figure count do not establish practical coverage. The following extraction commands locate candidates, not automatically approved illustrations.

### Recommended local video frame extraction: unattended insertion remains pending

Recommend [the PyPI `deck-extract` package](https://pypi.org/project/deck-extract/), pinned to the tested release `0.1.1`, as the local first choice for candidate frame extraction. The wrapper checks for the CLI before running. If absent, recommend the optional requirements file in an isolated environment; the package processes local videos and does not use cloud visual analysis. Run:

```bash
python scripts/extract_video_frames.py lesson.mp4 work/lesson-frames --fps 1 --threshold 0.90 --debounce 2
```

The wrapper requests only PNG frames and timestamp metadata (`--no-pdf --no-pptx --no-zip`). It preserves the package's raw `slides_metadata.json` and writes a second, timestamp-sorted `slides_chronological.json`; each normalized row retains its source detection index and the image filename. This sorting is necessary because the tested detector can update an earlier slide record while merging incremental build-ups, leaving raw metadata in a non-chronological order.

For multiple videos, create a private JSON inventory with one `{ "chapter_id": "src001", "video": "..." }` row per lesson and run:

```bash
python scripts/extract_video_batch.py --manifest work/videos.json --output-root work/frames \
  --extractor-script scripts/extract_video_frames.py --tool deck-extract \
  --fps 1 --threshold 0.90 --debounce 2
```

The batch helper commits each completed lesson directory only after its sorted manifest matches the source path, available size/mtime fingerprint, and extraction parameters, and its referenced image files pass integrity checks. New manifests include per-frame byte counts and SHA-256; reruns check those fields and refuse to skip altered or missing frames. Legacy manifests lacking image hashes receive existence-only verification, recorded as `frame_verification` in batch status. Size/mtime is not a source-content hash. The helper archives interrupted staging output, writes `batch_status.json`, and keeps a per-lesson log. Keep the inventory, logs, media, and extracted frames outside the skill repository.

Pilot runs on local lecture videos found duplicate presenter/scene frames, blank transition frames, and repeated slides. Treat every detection as a candidate: create a contact sheet, visually reject false positives and incomplete builds, then seek the source video around each selected time to verify the picture and its surrounding transcript. The timestamp is a sampled candidate location, not a guaranteed slide-onset timestamp. The wrapper does not crop a screen area or decide which image belongs in the book.

For a large candidate set, local OCR can rank slide text against nearby proofread paragraphs and flag likely duplicates of figures already in the same chapter. Filter obvious desktop/editor chrome from OCR ranking while retaining the original screenshot for review. Do not automatically suppress a frame because a similar phrase or slide exists in another chapter; the surrounding lesson may give it a different role. Use OCR rank and perceptual-hash distance only to prioritize review: OCR can miss diagrams or small labels, and a text-matched frame with a visibly different image may carry new lecturer annotations. Confirm each retained frame visually and record its exact paragraph anchor.

Use the [optional evidence index](evidence-index.md) to query existing OCR, text and frame/page metadata when repeated browsing is costly. Do not rerun OCR or create an index when direct source reading is faster. A reduced-resolution video scan followed by original-resolution extraction is an unverified candidate optimization; see maintainer experiments before altering the tested extraction route. The current extractor already uses FFmpeg and reduced-size comparison, so simply naming those techniques does not establish an improvement.

If an otherwise useful screen-share frame contains application chrome, crop only when the slide bounds are clear and the crop preserves the complete title, labels, annotations, and diagrams. Keep the raw frame, and record the crop as a derivative:

```bash
python scripts/crop_video_frame.py work/raw.png work/crop.png --box 0.10 0.13 0.82 0.84
```

The box is normalized left/top/right/bottom. Add `source_frame` and `crop_box_normalized_ltrb` alongside `image` in the approved mapping. The timestamp verifier compares neighboring samples to `source_frame` and also shows the EPUB crop. If the overlay hides slide content or the boundary is uncertain, use the raw frame or omit it.

When a matching original PPTX is available, compare its page with the video frame using slide text, visuals, and the verified video time before selecting it. Prefer a direct page render only when the page is an exact match and is cleaner or more legible; record the deck path, SHA-256, page number, and the video timestamp used to identify it. Inspect whether the PPTX page is native slide content or a rasterized screen-share capture first: exporting a rasterized WPS screenshot will preserve its toolbars and presenter overlay. In that case, follow the crop checks above, and omit the image if a presenter window covers meaningful slide content. Never infer a page match from filenames or neighboring file order alone.

When a course slide changes progressively, inspect neighboring detections together. Choose one clear state only when intermediate changes add no teaching meaning; retain a necessary dialog, choice, before/after contrast, or failure/correction even if the final frame looks cleaner. ±2-second verification samples belong in a temporary montage, not as repeated book illustrations. Two distinct but complementary slides may form one conceptual figure group: keep each original image as a separate `<img>`, give them compact sublabels, record each timestamp, and use one caption to explain their relationship. Do not flatten, redraw, or replace source frames merely to make the layout compact. Verify the group at a narrow viewport so the images stack without horizontal scrolling.

Prefer a legible framework, worked example, diagram, or lecturer annotation that adds information to the nearby prose. Opening/title screens, blank transitions, desktop-share mistakes, and repeated closing text usually do not earn a place when the book already carries that material; retain them only when the image itself adds a useful structure or emphasis.

After review, describe only approved frames in a private mapping file, then insert them without changing transcript text:

```json
{
  "figures": [{
    "figure_id": "fig-src001-01",
    "chapter_id": "src001",
    "chapter_title": "Lesson title",
    "anchor_id": "edited-p0001",
    "source_video": "path/to/lesson.mp4",
    "source_video_sha256": "optional SHA-256",
    "caption": "A concise explanation of the figure group.",
    "frames": [
      {"image": "work/frame-a.png", "timestamp": "00:12:34", "label": "First state", "alt": "Description"},
      {"image": "work/frame-b.png", "timestamp": "00:13:02", "label": "Complementary state", "alt": "Description"}
    ]
  }]
}
```

When reusing a video entry in `sources.xhtml`, set `existing_source_video` to the exact path, provide its containing `existing_source_section_id`, and give the figure's `source_id`. The tool searches only inside that named lesson/source section; a unique path somewhere else in the book is not enough to establish provenance. If the section contains more than one matching entry, also provide `existing_source_id` for the exact path element. If the intended section has no matching video entry, use `source_video` to add a new source record instead of borrowing an adjacent lesson's entry.

If a directly matched video frame and PPT atlas page show the same teaching image, avoid packaging a duplicate: on that frame, set `reuse_epub_asset` to the existing package path and `reuse_epub_asset_sha256` to its current hash, while retaining the matched video `source_frame`, timestamp, and frame hash. The helper verifies and reuses that OPF asset. Set `atlas_page_href` on the figure for reciprocal body/atlas links. For a separately reviewed page-to-video match, add a top-level `page_time_matches` entry with the exact atlas page, sample time, local video/frame paths and hashes, and review evidence; this updates only that page's `data-time-status` and visible sample label. The helper records the supplied match but never decides whether the match is semantically correct.

Run `python scripts/insert_video_figures.py --input source.epub --output revised.epub --mapping work/approved-frames.json`. It refuses to overwrite either input or output, places each figure after the edited paragraph and only a following disclosure whose ID matches that paragraph (such as `p001` after `edited-p001`), adds media to the OPF, and links captions to a video-source appendix. This also preserves original-first layouts: it will not mistake the next paragraph's disclosure for the current paragraph's. Group members remain separate source images and stack in the reading flow. Review the generated report and open the EPUB in its target reader.

Every inserted video frame, including a single-frame figure, displays its candidate sample time beside the image. Keep “candidate sample point” distinct from slide onset or continuous visibility; the time is a locator for replay, not a claim that the slide began at that instant.

Before insertion, check every approved timestamp in the source video:

```bash
python scripts/verify_video_frames.py work/approved-frames.json work/timestamp-check --offset 2
```

The helper extracts frames at `t-2` and `t+2` with local FFmpeg, compares pHash to the selected frame, and writes compact contact sheets plus a JSON report. The distance threshold is only a visual-stability hint; inspect flagged changes and check each frame's surrounding lesson context. These verification samples are temporary and do not enter the EPUB unless explicitly listed in the approved mapping.

**Status: recommended local frame extractor; unattended insertion remains 尚待完善.** The wrapper helps locate candidate frames; automatic selection and transcript alignment are not yet reliable enough for unattended EPUB insertion. Another project with the same name, [`equipai/deck-extract`](https://github.com/equipai/deck-extract), is a YouTube download/transcript pipeline and does not replace the local-video PyPI package. Pin the intended package and keep human visual and transcript review in the loop. If a video-to-PPT export provides no per-slide timecodes, cite its page and mark video timing unknown unless manual playback verifies it.

## 4. EPUB assembly and comparison

For static-diff and glossary-helper commands, input contracts and safeguards, read [EPUB tools](epub-tools.md). Do not assume an arbitrary HTML layout is supported by a helper designed for specific paragraph pairs.

Use reflowable XHTML chapters unless the source requires another layout. Ensure the package has a unique identifier, title, language, and modified date. The OPF manifest and spine must include all reading documents and assets; the navigation document must resolve to the chapter IDs. Store `mimetype` as the first, uncompressed ZIP member.

For the original-to-edited mode, character diffs are aligned from source to edited prose. Store added and deleted character counts on each details element and verify that the displayed `+N -M` values equal the actual `<ins>` and `<del>` text lengths. The word “original” in the summary identifies the left-hand side of the comparison; `+` and `-` describe the change from original to edited text.

When revising selected chapters in an EPUB that already contains source-comparison disclosures, rebuild those target units from the frozen source and remove their superseded disclosures before running the helper. Existing closed comparisons elsewhere in the book may remain; the helper validates their summaries, counters, and nonempty reconstruction while checking the package-wide totals. Ordinary `<details>` notes are not source comparisons and are left alone. Do not feed the helper a mixture of new source pairs and stale comparison blocks for the same unit.

Keep images that support the prose next to the relevant lesson text, and link each to its exact atlas page with a return link. If the inline figure and atlas entry use the same image, point both XHTML documents to the same packaged image resource rather than storing duplicate bytes or re-encoded copies. Use a separate resource only for an intentional, traceable derivative that materially improves legibility or framing.

Diffs must remain distinguishable in the actual target theme: additions in bold,
deletions struck through, equal text plain. Color is supplementary; a reader that
suppresses it can still pass if these differences and the disclosure entry remain
usable. If color is rendered, verify foreground/background contrast together.
Reuse an accepted layout when its relevant dependencies are unchanged; do not
repeat CSS experiments solely to force colors through reader overrides.

## 5. Large-deletion audit

Group review items by course and chapter. Include paragraph ID, added and deleted character counts, original length, original paragraph, edited paragraph, and exact deleted fragments. Aggregate the number of flagged paragraphs and deleted characters by chapter so a person can choose where to start. State the threshold and remind readers that length is a triage signal, not an automatic judgment of information value.

If flags saturate a chapter, use the semantic risk checks in `editorial-fidelity.md` to prioritize without exempting unflagged or lower-priority units. A lost condition or negation can matter more than hundreds of removed fillers. Record source-to-book coverage separately from whether new book statements are supported.

## 6. Versioning and Zotero

### Rebuildable source history for repeated EPUBs

When a series produces many candidate packages and repeated binaries consume
meaningful storage, consider a private, project-local Git repository for the
**pre-package source closure** instead of committing every generated EPUB. First
inventory the inputs and check available space; do not initialize a repository at
a broad parent that would sweep in unrelated courses, recordings, credentials, or
temporary evidence.

Track the exact materials needed to reproduce a candidate: accepted manuscript or
reader-editor records, source and figure maps, edition/source manifests, build
scripts, dependency locks, styles/fonts, and any required package assets. A hash or
path to an external file does not make that file reproducible; retain required
inputs in an authorized private source store and bind their hashes. Reuse unchanged
files across commits so Git can share identical objects and delta-compress suitable
text inputs.

Before copying sources, inventory both content identity and the exact paths the
builder resolves. A hash-matching transcript elsewhere in the repository does not
satisfy a candidate-relative path dependency. Prefer a supported canonical path map
when it preserves the candidate's source identity and build behavior; otherwise
retain the required path-preserving copy and record its origin/hash in a closure
manifest. Git stores identical blobs once, but each required checkout path still
occupies worktree space. Compare this cost with the complete input closure ceiling
before committing; do not widen the repository to unrelated source media or review
caches.

Treat checkout filters as build dependencies. Git line-ending normalization can
change byte hashes even when text looks identical. For files whose exact bytes are
bound into the candidate (such as a reader JSON projection or frozen JSONL), either
disable text conversion with narrow `.gitattributes` rules or deliberately
normalize before computing the closure hashes and all downstream bindings. Verify
the recorded file hashes from a clean detached checkout before building. For
relocated images, keep the original source path/hash as provenance and add a
repository-relative build path to a hash-identical copy; the builder should resolve
that copy from the plan's directory and verify its hash.

Use explicit paths rather than `git add .` until ignore rules and `git status`
confirm that source files are included and generated outputs/credentials are not.
Commit one accepted pre-package state and tag its edition. Verify from a clean
detached worktree, with output written outside tracked source paths:

```bash
git init <private-source-repo>
git -C <private-source-repo> add <explicit-source-closure> <build-scripts> <lockfiles>
git -C <private-source-repo> status --short
git -C <private-source-repo> commit -m "source: <edition>"
git -C <private-source-repo> tag -a <edition>-source <commit>
git -C <private-source-repo> worktree add --detach <clean-build-dir> <edition>-source
<build-command> --input-root <clean-build-dir> --output <outside-repo-output.epub>
```

Record the commit/tag, build command and resulting hash; remove only the clean
build worktree after its checks pass. Keep the private source repository local
unless a remote is explicitly authorized.

Keep generated EPUBs, split volumes, extraction caches, and scratch outputs outside
the repository by default. Use narrow output paths in `.gitignore`; do not broadly
ignore source formats just because a source may also use `.epub`, `.json`, or an
image extension. A compressed EPUB is a ZIP binary and may not delta-compress well;
Git LFS also stores whole-file objects, so measure before placing generated
packages there.

For each candidate, record a commit or tag, clean/dirty state, edition and source
cohort, exact build command, tool/dependency versions, source/input hashes, build
report, and output SHA-256 in the private candidate manifest. Build from a clean
checkout of that commit. Pin fonts, locale, timestamps, ZIP member ordering and
compression where the toolchain allows. Compare the rebuilt EPUB's SHA-256 with
the recorded output; if it differs, investigate before calling the build
byte-reproducible. Do not overwrite an earlier candidate.

Normalize generated package metadata as well as ZIP metadata. In particular,
check whether the toolchain writes wall-clock values into OPF `dc:date` or
`dcterms:modified`; also derive stable package identifiers from the bound source
closure and keep any duplicated identifier (such as NCX `dtb:uid`) synchronized.
An EPUB can have identical chapter/assets while these metadata values still make
the complete package hash differ.

If no prior output hash is available, build twice from clean checkouts of the same
tag to separate paths and compare the complete EPUB SHA-256. Deterministic ZIP
metadata includes the first, uncompressed `mimetype` member's timestamp and
creator-system fields as well as member order, compression settings, and timestamps
for the remaining entries. Matching extracted member contents alone does not prove
that the EPUB file itself is byte-identical. Keep one verified output; treat an
identical second build as scratch and remove it only after the candidate and its
retention dependencies are inventoried.

Only consider removing an existing generated artifact after the source commit and
all required inputs are present, a clean rebuild passes the package checks and
matches the recorded hash, and no Zotero attachment, annotation, delivery, or
other retention requirement depends on that exact file. Preserve exact binaries
when byte identity cannot be regenerated or is needed for an imported/delivered
snapshot. Keep the Git history private; inspect tracked files, ignored files, and
reachable history before any remote or public release.

Report reproducibility and reclaimed storage as separate outcomes: a byte-identical
clean rebuild proves that the source closure can reproduce the artifact, but does
not itself prove that any space was freed. Before removing a candidate, search
current candidate manifests and review bindings for the exact path/hash, and
confirm that no annotation, delivery, evidence, or active toolchain depends on it.
If a cleanup action is blocked, report the candidate and its status without claiming
reclamation. When cleanup is permitted, record the exact removed bytes and measure
available space before and after.

Treat an imported EPUB as an annotation-bearing publication snapshot. Semantic Versioning identifies a book publication revision; record its course cohort and source recordings separately. For changes in source cohort or recording, keep source identities distinct and use the [course-editions](course-editions.md) mapping workflow. Use a new Zotero book item for a new publication edition unless the user specifically requests another operation. Verify:

1. the item is in the intended collection;
2. its child attachment is an imported/stored EPUB copy;
3. the stored attachment SHA-256 equals the delivered local file;
4. the reader opens the intended version;
5. the full-text index length and its configured cap.

Keep draft EPUBs and large audit reports in the chosen working directory, not in a personal notes vault unless requested.

Name editions with Semantic Versioning notation (`vMAJOR.MINOR.PATCH`) in both the EPUB filename and its visible title. Use the version explicitly requested by the user and do not overwrite an earlier edition or its Zotero attachment.

For release review or recovery across batches, read [`review-and-recovery.md`](review-and-recovery.md). Bind findings to actual manuscript/map revisions and candidate hashes; recheck affected dependencies after changes. Generate the current Agent projection from the same approved manuscript/figure records when feasible. Do not let a stale summary stand in for inspection of the current package.

Use that reference's resume/handoff section after interruption and its readable-milestone section to keep optional research from delaying a useful bounded EPUB. For format changes, [reader experience](reader-experience.md) describes a fictional sample set and target-reader checks. Keep semantic acceptance, observed keyword scans, package conformance, and reader inspection separately named and scoped.

## 7. Synthetic test pattern

Tests should create a tiny temporary EPUB with invented text such as “A sample note.” and “A revised sample note.” Include one unchanged paragraph and one changed paragraph containing `<`, `&`, and `>` characters. Verify the output XML, exact reconstruction of both sides, counter values, default-collapsed details, preserved resource hashes, and no script elements. Never put real course excerpts or real identifiers in test fixtures.
