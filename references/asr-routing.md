# Local ASR routing and evidence limits

Load this reference only when a course lacks a usable transcript, needs a bounded transcript comparison, or the user requests local speech recognition. If an acceptable transcript already exists, freeze it as a named source layer and do not re-transcribe the entire course merely because another model is available.

## Choose the route by evidence

1. Inventory local audio/video and every existing transcript, including its producer, language, speaker labels, time semantics, file hash, and lesson identity. Keep Tongyi, Baidu, FunASR, subtitles, and human revisions as separate source layers; never silently replace one with another.
2. Use an already available local pipeline on a bounded representative lesson or section before scaling. A local FunASR route is one candidate for Mandarin-dominant speech with English technical terms; tool support and a successful prior run do not establish quality on a new recording. Keep dated model/configuration/environment findings and exact tested scope in project-local experiment records rather than embedding one project's sample counts as timeless skill capabilities. Reuse an existing offline model cache when available. Do not install model dependencies globally or upload private audio to cloud ASR without explicit authorization.
3. Run only one heavy GPU ASR pipeline at a time. For Chinese-primary/English-secondary/miscellaneous-other language settings, keep language labels as routing hints rather than claims about recognition accuracy. Retain source identity, model/configuration, cache mode and failure evidence needed to reproduce or resume the actual run. Existing tools may retain natural timing/resource metadata, but ordinary ASR does not require new telemetry tasks. Measure elapsed/peak resources when an explicit comparison or performance investigation calls for them; see [maintainer experiments](maintainer-experiments.md).
4. Compare systems by returning to audio or a reliable human-checked source. A difference between two recognizers is a disagreement candidate, not evidence that either output is correct. Measure error rates only when a human-verified reference exists.

## Speaker and time limits

- Do not call a lesson single-speaker or multi-speaker from the file format, channel count, or transcript punctuation. Confirm actual speaker changes acoustically. A prior successful transcription run does not establish diarization quality; leave speaker identity unresolved when it has not been verified.
- A model's sentence segments or VAD boundaries can be retained as candidate locators. They are not verified utterance end times, word-level alignment, or slide onsets. Do not use audio duration to claim that the final sentence ends at that exact time.
- If a meeting has real speaker turns, keep speakers anonymous until voice-to-person identity is authorized and verified. If separation quality is uncertain, preserve the original overlapping/uncertain span rather than merging voices.

## Discussions, voice Q&A, and speaker-aware pilots

When sources contain or may contain actual exchanges, choose a pipeline capable of associating transcript spans with speaker turns, not plain ASR alone. Transcription, diarization (who spoke when), and identifying a person's name or teaching role are separate capabilities, even if one tool packages them together. Check current official model/tool documentation and a local sample before selecting or claiming a route; do not designate a permanent best model. If reliable separation is unavailable, preserve a transcript candidate with unresolved turns and local limits rather than converting every utterance into the teacher's voice.

Use the recording's actual conditions to choose a small pilot. Useful cases include these; do not manufacture all of them for a course that lacks them:

| Actual case | What to check against audio |
|---|---|
| One continuous speaker | False splits, long pauses, specialist names, numbers, negation, and mixed-language terms. |
| Two speakers in Q&A | Short questions, interruptions, the return to the same voice, and answers attached to the right question. |
| Several people in discussion | Speaker merges/splits, quiet voices, overlap, and continuity across processing chunks. |

Use neutral per-recording labels such as `speaker_01` until identity or role is supported. Do not carry a label into another recording as if it identified the same person. If files are chunked, check cross-chunk speaker correspondence instead of concatenating unrelated local label numbers. Teacher-quoted student words are not an acoustic speaker change; a real student's first-person story is not the teacher's autobiography. Keep both acoustic evidence and any role-attribution evidence when the distinction matters.

Record model/revision, diarization configuration, device, sample locators, turn boundaries and their time semantics, overlap handling, and what was actually listened to. Do not force the diarizer to a guessed speaker count merely to match a `1/2/many` routing hint. Evaluate source-to-proofread voice consistency after editing as well as acoustic turns before it.

Compare recognizers on the same audio and review disagreement candidates. Report CER/WER only with a human-verified reference and a stated normalization policy. Report a diarization metric only with annotated speaker/time reference and stated overlap/boundary scoring conventions; otherwise provide concrete observed attribution failures with locators. Speed, transcript length, punctuation, and inter-system disagreement are not accuracy scores. Keep measured environment capabilities separate from routing recommendations and carry limitations into the candidate's private review status.

## Review before EPUB integration

Treat generated ASR as raw candidate material. Keep source IDs, segment order, timestamps with their precise semantics, and the original text unchanged. Route uncertain names, numbers, negations, terminology, quotations, and speaker changes to a localized uncertainty register. Use a second recognizer only for a specific unresolved risk, not as a substitute for hearing or a human reference. Record which material was machine-generated, which was edited, and which was acoustically reviewed.
