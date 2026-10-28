# Published article sources in course EPUBs

Read this reference when the user wants public articles, essays, or long-form posts included as an introduction, overview, or separately attributed companion chapter in a course EPUB.

## Identify the source layer

- Preserve the article's original title, author/byline, account, publication date, later update date when present, original URL, local capture path, and SHA-256 for each file or asset bundle. Record a retrieval date only when it is known; otherwise mark it unknown and keep local file-modification time separate.
- Keep article publication/update dates separate from course recording dates, upload dates, transcript dates, and EPUB production dates.
- Treat a public article as its own authored text source, not as an ASR transcript or proof of what was said in a course recording. Do not blend it into the teacher's spoken prose or use it to silently correct the lecture.
- For an opening section, put requested article chapters before the course lessons and give them ordinary TOC entries. Keep their original title, paragraphs, headings, quotations, lists, references, and voice. Explain once that these are the author's public articles and not course transcripts; avoid repeating editorial tags throughout the text.

## Check capture completeness

Inventory available Markdown, HTML/MHTML, PDF, Word, and image-asset folders before converting. When a complete local HTML capture exists, prefer it as the XHTML conversion source; use its asset directory and a matching Markdown capture for independent comparison. Do not treat a Markdown export, a publisher's word-count badge, a successful download, or the presence of a final paragraph as proof of lossless capture.

Compare extracted article text across available formats after normalizing only markup, whitespace, and equivalent typographic encoding. Also compare title/byline/date, heading and paragraph sequence, quotations, lists, tables, footnotes/citations, inline image positions and captions, and the ending. Record missing or conflicting spans and the exact files checked. Similarity scores and character counts are triage signals, not semantic acceptance. Say “lossless” only when the full source scope and meaningful structure/assets have been checked; otherwise describe the narrower verification performed.

Exclude HTML elements hidden with `display:none` from the reader-facing body, and record their count and text separately. Captures may contain zero-width placeholders inside hidden spans; do not turn these into visible manuscript text. Do not strip text from visible elements. For comparison only, document any capture-specific zero-width or Markdown-formatting normalization and verify the visible HTML body against the independent capture.

When extracting HTML, use a parser that recognizes void elements such as `img`, `br`, and `meta`, and track the exact article-content container so parsing does not spill into page chrome. Count image-reference occurrences, distinct referenced assets, and files in the asset directory separately: repeated article images may reuse one asset, while page-shell or recommendation images may be present but unreferenced. Do not package orphaned files unless their relationship to the article is established.

When the source URL is available and local captures disagree or are incomplete, use the web-access skill for read-only source verification. If the page or its assets cannot be retrieved, retain the local capture as a bounded source and record the gap; do not invent or silently omit missing material.

## Preserve images and links

- Inventory each image reference in source order, its caption/alt text, local asset path if present, and file hash. Distinguish decorative logos from figures that carry claims, examples, diagrams, or steps.
- EPUB output should not depend on remote image URLs. Include available local assets, preserve their sequence and meaningful captions, and reuse identical bytes where possible. Do not re-encode or deduplicate merely similar images without checking whether annotations differ.
- If an article references an image whose bytes are unavailable, keep the text and source locator, record the missing asset visibly or in a clearly linked source note, and do not imply that the illustrated material is present. Fetch public assets only from the identified source page and within the user's requested scope.
- If the source has no descriptive `alt` text, preserve the image in place and record the missing description. Do not invent image meaning or imply that OCR was performed; state the limitation once in the Agent-reading guide when the images may carry information.
- Keep citations and outgoing URLs usable. Preserve the destination or show a concise source link; do not copy raw tracking parameters into normal prose when a clean canonical URL is available.

## Convert HTML captures without losing source context

- Extract only the article container (for WeChat captures, commonly #js_content) with an HTML-aware parser that handles void elements. Keep source order and semantic markup; sanitize page-shell classes and layout CSS while preserving meaningful emphasis, paragraph breaks, image captions, links, and typography.
- HTML and Markdown may identify the same image differently: HTML can use a relative local path such as ./assets/name.png, while Markdown carries the original remote URL. Resolve each HTML path through the per-occurrence asset inventory (usually by its local filename), then compare the ordered source-URL sequence. Matching sets or counts alone do not prove that inline images occur in the right places; duplicate occurrences matter.
- If the HTML contains nonstandard video/audio/player elements that Markdown omits, inventory them at their exact position. Convert unsupported players to a compact local card with meaningful title, creator, duration, and available author-provided description, plus a link back to the article. Do not embed signed/expiring media URLs or require remote media for core reading. Keep player-card text distinct from the article body's text comparison.
- Some Markdown renderers leave literal formatting markers when the source has adjacent emphasis boundaries. If rendering Markdown changes the text or emphasis, use the verified HTML structure for the chapter and keep Markdown as the independent comparison source; do not silently publish parser artifacts.
- When converting a capture with hidden nodes, compare the XHTML body with the visible article container after excluding those hidden nodes and excluding separately identified player fallback cards. Record how many hidden nodes/characters were omitted. Preserve the original visible image order even when no image-level alt/OCR is available, and disclose that gap to Agent readers.
- After HTML-to-XHTML conversion, extract the emitted body text and compare it with the source article container, excluding only clearly identified fallback cards added for unsupported players. Validate ordered image mapping, local file hashes, XHTML well-formedness, internal fragments, and all local links before packaging.

## Build and review

Create a source-to-EPUB manifest for each article with its source file hashes, text-comparison scope, paragraph/heading counts, image-reference and packaged-asset counts, unresolved gaps, and final chapter locator. Keep detailed diffs, selector strings, and diagnostics in private working records.

Validate that article chapters precede course lessons as intended, TOC links resolve, XHTML is well formed, local images and hyperlinks resolve, no remote dependency is required for core reading, and the packaged text reflects the checked article source. If only a Markdown capture exists, label its verification as local-file integrity and structure review rather than source-to-original verification.

The current Agent-readable export may include an article chapter only when it is intentionally part of this book edition. Preserve its distinct publication-source attribution and date. Exclude superseded article captures and editorial iteration history.
