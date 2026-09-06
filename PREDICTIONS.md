# Pre-registered predictions

Recorded before the corresponding runs, per §7 of the validation protocol.
Do not edit an entry once its run has started. A contradicted prediction
requires a written investigation in NOTEBOOK.md before the result is used.

| # | Date | Prediction | Status |
|---|------|-----------|--------|
| P-01 | 2026-08-20 | E4: T1 accuracy rises and T2 accuracy falls as adaptation strength increases | amended 2026-09-06, superseded by P-01a; see the note below |
| P-01a | 2026-09-06 | E4: T2 accuracy falls monotonically with adaptation strength, and T1 accuracy is non-monotone with an interior maximum | PENDING SIGN-OFF |
| P-02 | 2026-08-20 | E3: strongest on T3; poor on T2, possibly close to useless | open |
| P-03 | 2026-08-20 | E5: strongest on T2 by a wide margin; likely dominated at matched budget | open |
| P-04 | 2026-08-20 | E6: dominates the low-rate end of the T1 front; poor on T3 | open |
| P-05 | 2026-08-20 | E2: strong on T3; its case rests on format symmetry, not peak accuracy | open |
| P-06 | 2026-08-20 | P1: temporal information index high for T2 and T3, moderate for T1 | open |
| P-07 | 2026-08-20 | P2: the three tasks degrade under different corruption operators | open |
| P-08 | 2026-08-20 | Parameters (channel count, spacing, compression) matter more than choice of scheme | open |

---

## Amendment note, P-01 to P-01a (2026-09-06)

**PENDING SIGN-OFF. The implementation session must not treat P-01a as live
until this marker is removed by Simon.** The original P-01 stays visible above
and is not deleted.

P-01 predicted T1 accuracy rising with adaptation strength. That rests on E4
emphasising onsets more strongly as `delta_a` grows, and the measurement in Q10
shows it does not. Onset emphasis, taken as the ratio of steady-state to
first inter-spike interval, peaks near `delta_a = 1` and falls away on both
sides: strong adaptation suppresses the second spike as well as the steady
state, so the onset interval lengthens from 8 ms to 139 ms across the sweep and
the two rates re-converge. A sweep spanning the peak could therefore confirm or
contradict P-01 depending only on which side of it the swept points fell.

P-01a states the shape the mechanism actually predicts. It is a stronger
commitment than the original, not a weaker one: an interior maximum on one task
alongside a monotone decline on the other is much harder to satisfy by accident
than a pair of monotone trends.

**Provenance, which is the whole of the case for amending rather than
restricting.** The information came from E4's step response on a synthetic
drive — no dataset, no probe task, no labels, no run started, and nothing that
could have been read off an outcome. §7 forbids editing an entry once its run
has started; no E4 run has started.

**A constraint on the sweep that follows.** The peak sits near `delta_a = 1`
for a step to 3.0 with `theta_0 = 1`, `tau_m = 0.02`, `tau_a = 0.1`. Its
location depends on `V_inf/theta_0` and on `tau_a/tau_m`, so it will move on
real speech envelopes and a grid chosen from the synthetic measurement will not
transfer. The peak must be relocated on the actual drive distribution before
the E4 sweep range is fixed, and that calibration is a recorded pre-run step
under D35 rather than an informal look — otherwise choosing a range that
straddles the peak is indistinguishable from tuning.
