# Word joining audit, 2026-11-11

## Confirmed defects

- The first live GRU kept its hidden state across minutes, although training
  examples were 1.5–3 second recordings. A 148.87 second captured stream produced
  blank on all 3,722 processed blocks. Restarting inference on short windows
  produced tokens. This demonstrates a train/runtime mismatch, not correct words.
- Rolling preview then replaced the whole displayed transcript every 250 ms.
  In the second log it changed 169 times over 337.95 seconds. That implementation
  was a preview, not a transcript assembler.
- The baseline recognizer itself is weak: greedy decoding got 45/81 complete
  held-out recordings correct, and only 1/20 TOI KHOE recordings correct.
  Display stabilization cannot repair classification accuracy.
- No intended gestures/timestamps were supplied for the two live logs. Their
  output changes can be measured, but their word accuracy cannot be computed.

## Implemented behavior

The default `python -m SmartSignLanguage.predict_word_ctc --serial-port COM3`
now uses fixed-origin turns instead of rolling preview. It measures a rest pose
after calibration; distinct movement/pose change sustained for 120 ms begins a
turn, retaining 200 ms preroll. There is no rest requirement between words.

Returning to the measured rest pose for 1 second ends the turn. Quiet movement
alone is insufficient: flex shape and gravity direction must also match rest.
A held static sign outside the rest pose therefore does not end the turn.
A sign physically indistinguishable from rest remains a fundamental ambiguity.

The whole turn is decoded once using CTC prefix beam search (width 10), with no
sentence whitelist. Empty results or tokens whose best-alignment peak score is
below 0.70 are rejected, not partly pasted into a sentence. This score is an
experimental model-score threshold, NOT calibrated accuracy/confidence. A wrong
token with a high score can still pass. No grammar is used to invent missing words.

Loss of samples rejects the turn. Turns over 8 seconds are rejected and require
returning to rest; they are not cut at an arbitrary word boundary. The current
model is not validated for arbitrary-length signing. No TTS is enabled.

The former rolling mode remains available explicitly as `--preview` for diagnosis.
Raw rows, output events, model hash and the measured rest profile are logged.

## Evidence and reproducibility

- `python -m unittest discover -s tests -p '*ctc*.py'`: decoder, causal feature
  parity, repeated tokens, gaps, static signs, endpoint timing and split tests.
- `python -m SmartSignLanguage.audit_ctc_logs --output <report.json>` replays old
  logs. Old files lack a measured rest profile, so first-second estimates are
  explicitly marked; unstable estimates are rejected. This is not a live test.
- `.runtime/continuous_words/decoder_v1.json` compares decoding on unchanged
  recordings. Beam improves validation WER from 0.40 to 0.36, while test exact
  matches remain 45/81. Test WER changes from 0.489 to 0.478. These previously
  inspected test recordings are diagnostic, not a new blind evaluation.
- Training experiments and their trial membership remain in separate model
  folders; original sensor CSVs and existing models are preserved.

## Training experiments and promotion decision

Both new experiments ran 220 epochs, selecting checkpoints by validation only.
`word_ctc_u4_phrases_v2` uses robust scaling, up to 0.8 seconds of background
context, and frame-normalized empty-target loss. It scored 18/81 diagnostic test
recordings correctly (WER 0.700); it was not promoted.

`word_ctc_u4_phrases_v3` retains standard scaling and the original loss weighting,
adding at most 0.2 seconds of background context. Validation on the comparable
60 isolated-word examples improved to 45/60 versus baseline 40/60. However,
diagnostic test greedy results were 42/81 (WER 0.511), and beam results 43/81
(WER 0.522), versus baseline beam 45/81 (WER 0.478). This model was not promoted
either. The default remains the original checkpoint, with repaired turn handling.

Replay of the second old log with the new turn handler and original checkpoint
yielded 19 starts, 18 uncertain outcomes and one unfinished turn, with no accepted
results. With v3 it yielded 3 results and 15 uncertain outcomes; there are no
gesture annotations to tell whether those 3 results are correct. These logs also
lack the new explicit end-of-turn rest protocol. It would be misleading to call
either replay a successful live recognition fix. The changes repair software
mechanics but do not establish usable recognition accuracy.

## Research informing the repair

- [CTC, Graves et al.](https://www.cs.toronto.edu/~graves/icml_2006.pdf): paths
  collapse blanks and adjacent repeated labels; CTC blank is not physical rest.
- [Online CSLR, Zuo et al., EMNLP 2024](https://aclanthology.org/2024.emnlp-main.619/):
  online recognition requires a designed training/inference pipeline. Merely
  sliding an isolated recognizer does not establish correct continuous signing.

These papers do not validate this glove or this small dataset. The software
changes address confirmed decoding/runtime defects; recognition quality still
requires separate labeled evaluation.
