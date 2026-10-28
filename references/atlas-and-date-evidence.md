# PPT atlases, video figures, and date evidence

Load this reference when a course has PPTX files, video-derived illustrations, OCR/ASR date clues, or a requirement to preserve every source page. Source page retention and selected body illustrations solve different problems: do both when requested.

## Establish PPTX identity and geometry

For each deck, record its source SHA-256, slide count, stable source ID, and the mapping from slide number to atlas anchor. Inspect OOXML slide relationships and shapes rather than assuming that every deck is a normal native slide. For every page, record embedded media identity, pixel dimensions, crop rectangle, shape count and type, EMU position/size, slide background, and its layout/master/theme dependency. Keep cached master date fields separate from slide-level date fields.

Use a trusted local full-slide renderer when it can safely produce a verified output. If an invocation launches an application updater, modifies a shared profile, or fails to create the expected document, stop that route; do not allow an installation/update or change global settings just to render a deck.

Geometry reconstruction is a narrow fallback, not a general PPTX renderer. It is permitted only when **every page** has exactly one uncropped embedded raster, no other slide-level visual object, identical known placement, a known native canvas size, and a fully resolved background. Preserve the original raster bytes and hash; record the output canvas dimensions, derived image hash, geometry, background source, and method. Verify the derivation against a real renderer on a representative deck using the same template, and get independent page/hash review. State that the result is an OOXML-derived geometric reconstruction, not an Office-rendered page. If one condition fails or a master/layout element could carry visible content and cannot be resolved, stop and report the page gap; do not fill it with a guessed blank margin.

The full atlas keeps every source page, including pages not selected for inline illustration. Inline figures should explain neighboring prose and link to their exact atlas page; atlas entries should link back to the relevant body figure or paragraph when one exists. Keep exact source page numbers and per-page hashes. Page order is a navigation order, never proof of video timing.

Every atlas entry must visibly show its time status in the normal reading flow, outside folded disclosures. If a page has a visually accepted page-specific match, label it as a `sample_time` and state that the point is not a verified onset or visible interval. If no page-specific match was accepted, print `视频采样时间：未知`; do not leave an empty time field or borrow the timestamp of a neighboring body-only frame. Store the page status in XHTML metadata (`data-source-id`, `data-page-number`, `data-sample-time`, `data-time-status`) and run `scripts/label_atlas_times.py` to render/check the visible line. This helper formats existing evidence only; it cannot promote OCR, page order, similarity scores, or topic adjacency into a match, and its check does not prove CSS visibility in the target reader.

## Video-derived figures

Use the pinned local `deck-extract` wrapper described in the main skill to find candidate frames, then inspect the contact sheet, reject duplicates/transitions, and verify each retained frame against the source video and nearby transcript. Preserve the raw frame, detection index, source video hash, and candidate timestamp. Group successive animation states only when they form one teaching unit; retain each constituent image and label. Do not promote a sampled timestamp into a slide onset or visible interval without direct playback verification.

## Recording-date candidates

Keep `recording_date`, screenshot clock, file creation/modification time, download/export time, transcription time, and book-production time in distinct fields. A date or time found by OCR/ASR is a locator candidate, not a confirmed recording date. For each candidate keep the raw text, exact source page/segment, source asset hash, embedded image/frame hash, full-page render hash, OCR bounding box/confidence, manual full-resolution reading, timezone status, interpretation, and competing evidence. Preserve both OCR output and manual reading; never overwrite one with the other.

An in-frame desktop clock may show the screen capture time rather than when the course was recorded. A cached PowerPoint master date is template metadata until it is shown to be instantiated and relevant. A container timestamp can mean encoding/remux time. Relative speech such as "today" or "last year" cannot be converted without a verified calendar anchor. File-system timestamps and download names are organization metadata, not recording-date evidence.

Maintain `sample_time`, `visible_interval`, and `verified_onset` separately. `sample_time` means a sampled candidate location. A PPT page can remain `sample_time: unknown` even when a separate video-only body figure has a candidate timestamp. Do not copy a body-frame time to a PPT page without a source-specific match. ASR segment/VAD boundaries are not word timings or verified visual intervals.

Until an independent source or direct recording evidence confirms the date, keep the candidate status explicit, preserve the original course order, and do not sort the collection by it. OCR date patterns and contact sheets prioritize human review; they do not make that decision automatically.
