# Lab notebook

Append-only, newest at the bottom. One entry per working session, from either
the implementation session or the design session.

Template — copy this block, do not reformat it:

```
## YYYY-MM-DD | session: implementation | code | design
**Did:**
**Tests:** (which passed, which failed, which are new)
**Results written:** (paths, and manifest entries added)
**Blocked on:**
**Next:**
```

---

## 2026-08-20 | session: design
**Did:** Proposal v2 issued incorporating Oliver's answers (D01-D11). Battery
reduced to three tasks; information-theoretic metrics added; E7 marked
provisional; accent-diversity risk added to stage two.
**Tests:** none yet — repository not created.
**Results written:** none.
**Blocked on:** TIMIT licence (O2); corpus specifics (O1).
**Next:** create repo, write interface spec and Layer 1 known-answer tests,
then implement the common front end and E1.

## 2026-08-20 | session: design
**Did:** Wrote SPEC.md (interface contract), tests/test_known_answers.py (Layer 1
suite, ~45 tests derived from equations 4-29), tests/conftest.py, CI workflow,
and the GitHub conventions section of CLAUDE.md. Verified every expected value
in the test suite arithmetically and independently of any implementation.
**Tests:** none pass — spikeenc does not exist yet. Expected: the suite was
written before the code, deliberately.
**Results written:** none.
**Blocked on:** nothing. Implementation can begin.
**Next (implementation session):** read SPEC.md, then build in this order —
(1) SpikeTrain and metrics, (2) Filterbank, until F1-F5 pass, (3) E1, until
T1.1-T1.3 pass, (4) E2, until T2.1-T2.5 pass. E2 is where the sharpest tests
are; do not move on until they are green.

## 2026-09-02 | session: implementation
**Did:** Implemented `metrics`, `frontend.Filterbank`, `encoders.LIF` (E1) and
`encoders.SendOnDelta` (E2), in that order, one commit per green step. Front
end is FIR: each channel's taps are equation (4) sampled and truncated where
the envelope has decayed to ~4e-7 of peak, so what F1 and F2 check is what
`subbands` actually convolves with. Impulse responses normalised to unit
magnitude at f_c via the DTFT at f_c rather than an FFT bin, so normalisation
does not depend on the requested `n_samples`. E1's integrator is a module-level
`_integrate_and_fire` so E4 can share it rather than duplicate it, as SPEC 4.5
requires; no adaptation machinery added, E4 is not in scope. Applied D17
(refractory clamps to reset, drive discarded), D18 (integer lattice index) and
D19 (group delay uncompensated by default, `compensate_group_delay` shifts each
channel by (order-1)/(2*pi*b_c)).

Before this, verified the repo after Simon's cleanup: `.venv` no longer
tracked, `.git` back to 288K from 98M, `.gitignore` and CI present, D17-D19
committed.

**Tests:** 30 passed, 50 failed, 1 skipped, from 0/80 at session start.
Green: F1-F5; T1.1-T1.3; T2.1 (all four signals), T2.2, T2.3, T2.5;
`test_event_rate_definitions`, `test_vector_strength_extremes`,
`test_decoded_information_bounds`; and G1, G2, G3, G4, G7, G7b for both E1 and
E2. Every remaining failure is an unimplemented module (E3-E6, `features`,
`corrupt`) except T2.4, which is Q04.

Margins, since a bare pass is not evidence: F1 worst peak error 0.00098 against
a 0.01 limit; F3 ERB-rate step CV 3.5e-15 against 1e-6; F4 correlation 0.988
against 0.95; F5 energy ratio 0.876 in a 0.2-20 window; T1.1 ISI 0.0138750 s
against the closed form 0.0138629 s, error 1.2e-5 s inside a 9.4e-5 s
tolerance, the residual being sample quantisation at 222 steps of 62.5 us;
T1.3 exactly 200 events in 1 s at refractory 0.005 with min ISI 0.005 s.

**Two things worth flagging rather than smoothing.**

1. T2.2 initially produced 359 events against a predicted 400. Cause was not a
   tuning matter: the drive peak is exactly 1.0, the reference sits at 9C =
   0.9, and equation (14) asks whether u - r >= C. In exact arithmetic
   1.0 - 0.9 = 0.1 >= 0.1 and the event fires; in doubles the subtraction
   yields 0.09999999999999998 and it does not. Dropping the crest costs two
   events per half cycle because the descent then starts one step in. Fixed by
   measuring outstanding steps as (u-r0)/C - m, avoiding the cancellation, plus
   a 1e-9 tolerance in lattice units (D20). The tolerance can only fire an
   event early, never late, so it tightens the equation (16) bound rather than
   loosening it, and T2.1 still passes on all four signals.

2. `envelope(method="rectify_lowpass")` is covered by no test — F4 exercises
   `"hilbert"` only — and was returning mostly carrier at my original 1 kHz
   second-order default: correlation 0.37 against a known modulator at a 953 Hz
   channel. It would have shipped looking fine. Changed to 300 Hz fourth-order,
   which is sound above ~500 Hz and still poor below. Equation (9) specifies a
   single cutoff for the bank, so the fix that works everywhere is a spec
   question, raised as Q03 with measurements.

**Results written:** none. No sweep run, nothing added to `results/manifest.json`.

**Blocked on:** nothing blocking. Q03 (equation (9) cutoff) blocks only the
envelope-method sweep. Q04 (T2.4 premise) blocks only that assertion.

**Next:** E3 `TemporalContrast` until T3.1-T3.4 pass, then E4 `ALIF` until
T4.1-T4.4. E4 should wrap `_integrate_and_fire` rather than reimplement it, so
that the delta_a == 0 reduction of T4.1 is true by construction. `features` and
`corrupt` are still stubs and gate G8 and the four corruption tests.
