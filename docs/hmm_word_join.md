# Experimental word-state decoder

Command from repository root:

```powershell
python -m SmartSignLanguage.predict_join_hmm --serial-port COM3
```

This is a different decoder from `predict_join_u4` (SVM label debounce) and
`predict_word_ctc` (CTC). It models each word with five ordered Gaussian-emission
states, plus a shared background state. An unrestricted word-loop graph permits
any word ordering and repeated words. No known-sentence whitelist is used.

Initialization uses isolated words. Sentence training then uses Viterbi alignment
constrained by the user's confirmed token order; it does not cut sentences into
equal-length words. This is approximate latent alignment, not verified boundaries.

Online decoding retains state hypotheses and appends a word only when their
completed-word prefixes agree. Holding a final state cannot append another copy;
repeating a word requires traversing its states again. There is no mandatory rest
between words, no 1-second stable-label gate, and no 8-second turn limit.
Stable best-path background with no pending best-path words ends a sequence.
Enter can finish already committed words; it cannot force an undecided word.

Invalid ADC samples or missing data break the current segment. They are not
interpolated or silently classified. The log retains raw rows and error details.
New words cannot safely be inferred during a GPIO-33 zero-signal interval.

## Evaluation, not a claim of deployment success

The diagnostic model `word_hmm_u4_phrases_v1` trains on 188 trials and selects
transition/emission settings on 72 validation trials. Validation includes a
separate isolated-word session and same-session phrase holdouts. Results:

- Validation: 66/72 complete recordings correct, WER 0.077.
- BAN KHOE validation: 3/4; TOI KHOE validation: 4/4.
- TOI CAM_ON BAN validation: 0/4 (BAN omitted).
- Previously inspected separate test sessions: 48/81 correct, WER 0.378.
- Separate-session TOI KHOE test: 2/20. Generalization remains poor.

The live checkpoint `word_hmm_u4_phrases_full_v1` refits all 341 available
recordings with validation-selected settings. Training fit is 267/341, WER
0.203: these are training numbers, not test accuracy. The earlier diagnostic
checkpoint and report are preserved; no accuracy is claimed for the full refit.

Replay on the old 306-second SVM glove log emits ordered tokens including
TOI CAM_ON BAN and BAN KHOE at some intervals. The exact intended gestures were
not annotated, so this does not prove these outputs correct. The replay encounters
746 invalid rows/interruptions, predominantly the already documented GPIO-33
problem. See `.runtime/continuous_words/hmm_replay.json`.

All five words share the same architecture. Extending the vocabulary requires
new data, alignment/training and fresh held-out tests, not adding phrase rules.
Unknown gestures may still be misclassified; Gaussian scores are not calibrated
confidence. This remains an experimental attempt to address segmentation rather
than merely hiding transient predictions.
