# Continuous word joining with the U4 SVM

Run from the repository root:

```powershell
python -m SmartSignLanguage.predict_join_u4 --serial-port COM3
```

This explicitly loads `sequence_5_100hz_U4_20261111_session_eval`, not the CTC
models. Calibration is unchanged. There is no physical rest-pose gate and no
8-second timeout. Signal validation remains enabled.

The word recognizer uses 150 real 100 Hz samples and predicts every 250 ms.
The joiner consumes every prediction, including candidates hidden by the old
two-confirmation display. A label must persist for at least 1,000 ms over at
least five consecutive predictions before it is added. These overlapping
observations are correlated and do not constitute independent confidence votes.

Different stable labels can follow each other without NONE. Holding a label
does not append repeated copies. Brief excursions to another label do not
re-arm the previous word. Stable NONE for 1,500 ms finishes the current sequence;
it is never inserted as a word. A repeat of the same word without another
accepted label or a NONE interval cannot yet be distinguished from holding it.

The reported BAN -> short TOI/KHOE oscillation -> stable KHOE pattern is covered
by a regression test using reconstructed prediction timing. It is not raw sensor
replay or a measured live success rate. An intentional stable TOI still passes,
as does a wrong TOI that stays stable long enough. Fast words can be missed.
This is a conservative temporal filter, not learned gesture boundary detection.

The model's label list supplies the vocabulary. `--model` can point to another
compatible five-flex model containing NONE; no BAN/KHOE phrase rules are used.
Adding labels to the model still requires collecting/training/evaluating those
labels and their transitions. More labels do not automatically preserve accuracy.

Only added words appear in `CHUOI TU`. Pending raw labels are retained in the
log, not presented as accepted text. R clears the sequence; Ctrl+C stops.
New `.runtime/svm_join` sessions include raw sensor rows, raw predictions,
joining decisions, calibration and the exact model hash. Interrupted data
clears the pending sequence rather than joining across the interruption.

Tests: `test_stable_word_sequence.py` (8) and `test_continuous_five.py` (10).
