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

## 2026-09-03 | session: implementation
**Did:** Applied D21 (channel-relative envelope cutoff, `f_cut_c = min(f_cut,
b_c)`, fourth order, second-order sections; the lowest channels put the
normalised cutoff near 4e-3 where tf-form coefficients are unreliable). Added
`envelope(method="none")`. Re-measured the Q03 table as asked and recorded it
there. Raised Q05, since answered as D24/D25. Reconciled the 2.53x lag ratio
Simon flagged.

**The 2.53x was my error, not any of the three candidates offered.** The
"envelope-LPF lag" column in the Q05 table was measured as `fb.envelope(...)`
against the modulator, so it was the *whole path* — gammatone, rectify,
lowpass — not the lowpass stage alone. Comparing a total-path measurement
against a single-stage analytic value produces the factor. Summing the stages
properly reconciles to within 1 per cent:

| f_c | b_c | gammatone n/(2 pi b) | Butterworth 2.61313/omega_c | analytic total | measured | ratio |
|---:|---:|---:|---:|---:|---:|---:|
| 196 | 46.7 | 13.63 | 8.90 | 22.53 | 22.50 | 0.999 |
| 479 | 77.9 | 8.17 | 5.34 | 13.51 | 13.50 | 0.999 |
| 953 | 129.9 | 4.90 | 3.20 | 8.10 | 8.12 | 1.003 |
| 3057 | 361.5 | 1.76 | 1.15 | 2.91 | 2.94 | 1.009 |

Note which gammatone constant that total uses: `n/(2 pi b_c)`, the group delay
at f_c, which governs a narrowband AM envelope. SPEC 3 specifies
`(order-1)/(2 pi b_c)`, the impulse-response envelope peak time, which governs
a click onset. They differ by `1/(2 pi b_c)`, 3.4 ms at 196 Hz. SPEC is right
for its purpose: test_F6 drives a click, and on the `"hilbert"` path the
current formula compensates to 0.00 ms residual. No change needed there.

**test_F6 spreads, recorded as D25 asks.** 16 channels, 150-6000 Hz, broadband
click:

| method | uncompensated | compensated | threshold |
|---|---:|---:|---:|
| hilbert | 10.75 ms | 0.00 ms | < 3.58 PASS |
| rectify_lowpass | 22.63 ms | 11.88 ms | < 7.54 FAIL |

That is Q05 quantified: compensation removes the gammatone lag exactly and
leaves 52 per cent of the skew on the rectify_lowpass path. The hilbert column
suggests the eventual threshold could be far tighter than 3.58 ms once D24 is
implemented; suggest revisiting after.

**Tests:** 31 passed, 50 failed, 1 skipped. Gained T2.4 (passes unchanged,
confirming E2 was already correct). Lost nothing; the new failure is test_F6,
which is D24 not yet implemented.

**Results written:** none.

**Blocked on:** nothing.

**Next:** two independent strands.
1. **D24** — `compensate_group_delay` must advance by the summed declared lag
   of every stage on the selected path, not the filterbank alone. Concretely:
   the shift currently happens inside `subbands`, which is upstream of the
   envelope stage and so cannot remove its lag; it needs to move to after the
   envelope stage, or `envelope` needs to apply the remainder. Envelope-stage
   lag is 0 for `"hilbert"` and `"none"`, and `2.61313/(2*pi*f_cut_c)` for
   `"rectify_lowpass"` (order-4 Butterworth DC group delay; the constant is
   `sum_k sin((2k-1)*pi/(2N))` for N=4). A stage that cannot declare its lag
   must raise, per SPEC 3. test_F6 is the check.
2. **E3 `TemporalContrast`** until T3.1-T3.4 pass, then E4 `ALIF` until
   T4.1-T4.4. E4 must wrap `_integrate_and_fire` rather than reimplement it, so
   the delta_a == 0 reduction of T4.1 holds by construction. E3 does not touch
   the front end, so it can proceed independently of strand 1.

`features.featurise` and the four `corrupt` operators are still stubs and gate
G8 across all six encoders plus the four corruption tests — ten tests for a
small amount of work, worth doing early.

## 2026-09-03 | session: design
**Did:** Answered Q03, Q04, Q05 (D21-D25). Added test_F6.
**Open:** the 2.53x discrepancy between measured and analytic envelope-lowpass
lag must be resolved before compensation is implemented.
**Observation for later:** three channel-dependent timing biases in a row were
found by measurement, not by test failure. Front-end coverage is thin relative
to the encoders — the maths gives exact answers for encoders and only
inequalities for the front end. Review once E3 and E4 are green.
**Next:** E3 TemporalContrast (T3.1-T3.4), then E4 ALIF (T4.1-T4.4).

## 2026-09-03 | session: implementation
**Did:** Raised Q06 — equation (21) is written as a level condition with no
reset, proposal section 5.3 prose says "threshold crossings", and all four T3
tests pass under either reading. G3 is the discriminator. Measured five
candidate rules over G3's own theta sweep; only a reference-reset rule on `d`
gives event count a usable ~1/theta relation to theta. Recommended option 4
(lattice on `d`, reusing SPEC 4.3), with the T3.4 symmetry verification
recorded so the answer can be acted on without a round trip. E3 stopped
pending the answer.

**Correcting the entry above, which crossed with mine.** The design-session
entry of the same date lists as open: "the 2.53x discrepancy between measured
and analytic envelope-lowpass lag must be resolved before compensation is
implemented." That is **closed** — resolved in the implementation entry
immediately preceding it (commit fd2938a) and recorded in Q05. The 2.53x was
my measurement error, not a property of the filter: the Q05 column labelled
"envelope-LPF lag" was measured end to end through `fb.envelope(...)`, so it
was the whole path — gammatone, rectify, lowpass — compared against a
single-stage analytic value. Summing the stages reconciles to within 1 per
cent (22.53 ms analytic against 22.50 ms measured at 196 Hz, same at the other
three centre frequencies). **D24 is not blocked.** Noted here rather than by
editing the design entry, which stands as written.

**Tests:** 31 passed, 50 failed, 1 skipped. Unchanged — no source touched this
session.
**Results written:** none.
**Blocked on:** Q06 blocks E3 entirely. Nothing else.
**Next:** D24 (move group-delay compensation to cover the whole envelope path;
test_F6 is the check) and the `features`/`corrupt` stubs (ten tests) are both
unblocked and independent of Q06. E3 resumes when Q06 is answered.

## 2026-09-03 | session: design (second entry this date)
**Did:** Answered Q06 (D26-D29). E3's event rule is the SPEC 4.3
reference-lattice rule applied to `d`; equation (21) and the surrounding prose
of proposal section 5.3 rewritten accordingly, including an explicit statement
of the cost — E3's event count now scales with transient amplitude rather than
transient count. G3 strengthened to require a 4x span in event count, not only
monotonicity. The `alpha = exp(-dt/tau)` convention restated in SPEC section 1,
where a Layer 3 reimplementer will actually see it. Added `test_T3_5` (closed
form step response, 4 ON and 3 OFF) and `test_T2_6` (E2 silent on a constant
drive); corrected the `test_T3_1` docstring and the T3 block header. Raised Q07
on ON/OFF channel format, non-blocking. Added two file-discipline conventions
to CLAUDE.md.

**The stale entry above stands, and was not edited.** The implementation
session was right that my previous entry listed as open something its own
preceding entry had already closed; the two crossed. The correction was made in
the right place and by the right mechanism. What went wrong was mine and is
now fixed at the cause rather than the symptom: I restated a blocker in
NOTEBOOK, which is a record of belief at a point in time and cannot be closed
by the session that resolves the blocker. Blockers belong in QUESTIONS.md,
referenced from NOTEBOOK by number only. Both conventions are now written into
CLAUDE.md so this does not depend on either session remembering it.

**Observation, extending the one in my previous entry.** That entry noted three
channel-dependent timing biases found by measurement rather than by test
failure. Q06 is a fourth finding of the same shape, but with a different cause
worth separating out: the front-end cases were thin *coverage*, whereas here
the coverage existed and the *gate was the wrong shape*. G3 asserted
monotonicity because monotonicity is easy to assert, when the property the
study needs is dynamic range. A generic gate that encodes a necessary condition
will be passed by things that fail the sufficient one, and there is no amount
of care in writing the implementation that catches that — only re-deriving what
section 6.4 actually requires. Worth a pass over G1-G8 with that question asked
of each, once E3 and E4 are green.

**Tests:** none run — no environment here. Expect `test_T2_6` to pass
immediately against the existing E2, `test_T3_5` to fail until D26 is
implemented, and G3 to be unaffected for E1 and E2 (spans about 16x).
**Results written:** none.
**Blocked on:** nothing. Q07 is open but blocks nothing until packaging.
**Next (implementation session):** E3 under D26 until T3.1-T3.5 pass, then E4
until T4.1-T4.4. D24 and the `features`/`corrupt` stubs remain unblocked and
independent.

## 2026-09-03 | session: implementation (second entry this date)
**Did:** Applied the design session's Q06 patch from `q06_patch.tar` and
committed it unedited as b9f3988 with the `[spec]` marker; tar left untracked.
Before committing, verified the unpack destroyed nothing, since an unpack over
the working tree is indistinguishable at a glance from accidental clobbering:
HEAD matched `origin`, the diff was 441 insertions against 34 deletions, and
every one of those deletions was a deliberate replacement — `APPLY.md` rewritten
as the patch's own instruction sheet, `**Answer:** (awaiting design session)`
replaced by the answer, equation (21) and proposal 5.3 rewritten per D26, the
G3 and T3.1 docstrings corrected per D27 and D29. The gitignored paths a
restore-from-GitHub could not have recovered (`data/`, `.venv/`) were not in the
tar. Recording this because the reflex to restore was the wrong one and would
have destroyed D26-D29 and the Q06 answer.

**Tests:** 32 passed, 51 failed, 1 skipped. Gained `test_T2_6`, which passes
against the existing E2 unchanged; lost nothing; the new failure is `test_T3_5`,
which is D26 not yet implemented. Both as the patch predicted.

**CI on b9f3988:** `protected-files` **success** — the `[spec]` marker accepted
the SPEC/test changes. `known-answers` failure at 51 failed, 32 passed, 1
skipped, *identical to local*. Worth stating rather than dismissing as the
expected red: a clean runner neither session configured reproduces the local
counts exactly, so the 51 failures are genuinely unimplemented code (E3-E6,
`features`, `corrupt`) and not local state propping anything up. It also
confirms `test_T2_6` passes in a clean environment.

**Results written:** none.
**Blocked on:** nothing. Q07 open, blocks nothing until packaging.
**Next:** E3 under D26 until T3.1-T3.5 pass, then E4 wrapping
`_integrate_and_fire` so the `delta_a == 0` reduction of T4.1 holds by
construction. D24 and the `features`/`corrupt` stubs remain unblocked and
independent of both.

## 2026-09-03 | session: implementation (third entry this date)
**Did:** Implemented E3 `TemporalContrast` under D26 — equations (18)-(20) with
`alpha = exp(-dt/tau)` per D28, both filters initialised to `drive[:, 0]`, then
the SPEC 4.3 reference-lattice rule applied to `d` with the lattice anchored at
`d = 0`. Added the `reference_update` argument SPEC 4.4 specifies and the
constructor was missing. Committed as 6d69374.

**E2's event loop is now shared with E3 rather than copied**, as
`_reference_lattice(sig, dt, C, refractory, reference_update, r0)`; E2 passes
`r0 = drive[:, 0]`, E3 passes `r0 = 0`. The reasoning is D26's own: it makes
E2-against-E3 a single-factor contrast in which equation (20) is the whole of
the difference, and that is only true of the study if it is true of the code —
two copies could drift apart with no test noticing, because each encoder would
still pass its own block. Logged as D30. The refactor was verified
bit-identical for E2 before committing: events and reference traces compared
elementwise across both `reference_update` variants, with and without
refractory, and on a 155359-event case that stresses the lattice index. Eight
cases, all identical.

**Margins rather than passes**, since a green test says only that the answer
was inside the tolerance:

| quantity | measured | required | margin |
|---|---|---|---|
| T3.5 `d_max` vs closed form | 5.98e-07 | < 1e-4 | 167x |
| T3.5 sampled below continuous | 5.98e-07 below | > -1e-9 | correct sign |
| T3.5 residual at m=4 | 0.104801 | < theta = 0.2 | m=5 would need d >= 1.0 |
| T3.5 `d` at end of signal | 6.74e-03 | > 2e-10 | 7.5 orders |
| G3[E3] span | 888, 432, 191, 69, 0 | >= 4x | 12.9x to the lowest non-zero |
| G4[E3] shift error | 1.4e-16 s | < 2*dt = 1.25e-04 | 12 orders |
| G7b[E3] min ISI | 16.2 ms | >= 3.94 ms | 4.1x |

An Euler pole would put `d_max` at 0.9070919, which is 22.9x the T3.5
tolerance, so that assertion does discriminate the discretisation as D28
intends. The G3 counts reproduce the design session's predicted 888, 432, 191,
69, 0 exactly.

**One thing added beyond the spec:** `tau_slow <= tau_fast` now raises. Inverted
time constants flip the sign of equation (20), which exchanges the ON and OFF
channels silently rather than failing — the shape of error this project has
been repeatedly bitten by. Flagging it because it is a constraint SPEC 4.4
states as a condition but does not require to be enforced.

**Two numbers in `test_T3_5`'s docstring do not reproduce.** Raised as Q08, not
fixed — the file is the design session's. Neither affects an assertion or a
conclusion; both are values a Layer 3 reimplementer would hand-check against.

**Tests:** 43 passed, 40 failed, 1 skipped, from 32/51/1. The eleven newly
green are T3.1-T3.5 and G1/G2/G3/G4/G7/G7b for E3. Failure sets were diffed
before and after, not just counted: nothing that passed before fails now.
G8[E3] stays red on the `features` stub.
**Results written:** none.
**Blocked on:** nothing. Q07 and Q08 are open and block nothing.
**Next:** E4 `ALIF` wrapping `_integrate_and_fire` so T4.1's `delta_a == 0`
reduction holds by construction. D24 (whole-path group-delay compensation,
test_F6 the check) and the `features`/`corrupt` stubs remain unblocked and
independent of it. Stopping here rather than continuing into E4 so that one
encoder at a time reaches review, per section 10 of the validation protocol.

## 2026-09-03 | session: design (third entry this date)
**Did:** Reviewed the E3 implementation at 6d69374 and answered Q08. Corrected
three numbers in `test_T3_5`'s docstring (D33), added `test_T3_6` (D31), and
made SPEC 4.4's `tau_slow > tau_fast` condition a required raise (D32).

**I read `src/spikeenc/encoders.py` during this review, and `test_T3_6` was
written afterwards.** This breaks the no-sight rule that §3 of the validation
protocol rests on, so it is recorded here, in the file header, and in the test's
own docstring rather than left for someone to infer. The test is derived from
equations (20)-(21) and I believe nothing in it came from the code, but that
belief is precisely the assurance the rule exists to avoid having to accept. A
reader weighing how much independent evidence the suite provides should discount
`test_T3_6` relative to its neighbours. The alternative was to withhold the test
to protect the appearance of the discipline, which would have cost the substance
of it: the single-factor contrast of D26 became true by construction under D30
and was tested by nothing.

**On the review itself.** The lattice arithmetic was traced by hand against the
T3.5 case rather than inferred from the green test. Truncation toward zero is
the correct rounding — `floor` would overshoot on the OFF side, moving the
reference past the signal and leaving a residual of the wrong sign — and the
tolerance is applied as `sign(step) * tol`, so it widens the emit condition
symmetrically in both polarities rather than biasing one. The 4 ON / 3 OFF
asymmetry falls out of `step = d/theta - m` giving -0.9663 at m = 1. The filter
initialisation is right in a way that is easy to get subtly wrong: `y` is set to
`u[:, 0]` and the loop then updates at i = 0, so `y[0] == u[0]` exactly and
`d[:, 0]` is zero. Initialising to zero and starting at i = 0, or initialising
to `u[0]` and starting at i = 1, both look reasonable and both shift the step
response by a sample.

**D30 is endorsed and the usual objection does not apply.** Sharing one routine
between two things being compared normally risks hiding divergence. Here it runs
the other way: T2 and T3 are now two independent known-answer blocks aimed at
the same code, so a bug in the lattice rule has more chances of being caught,
not fewer. The bit-identity check across eight cases before committing,
including a 155359-event case stressing the integer index, was the right
control.

**Tests:** none run — no environment here. `test_T3_6` should pass immediately
against 6d69374, since D30 makes it true by construction; if it fails, the two
encoders have already diverged and that is the finding. The three docstring
corrections change no assertion.
**Results written:** none. `results/manifest.json` is still an empty entries
array, correctly — nothing has been swept.
**Blocked on:** nothing. Q07 open with Oliver, blocks nothing until packaging.
**Next (implementation session):** E4 `ALIF`. E3's Layer 1 is complete; its
Layer 2 and Layer 3 are not, `G8[E3]` is still red on the `features` stub, and
D24 is unimplemented, which matters to E3 specifically because it sits on the
envelope path where the lag is largest.

## 2026-09-04 | session: implementation
**Did:** Applied the Q08 patch from `q08_patch.tar.gz` and committed it unedited
as fc7e6d2 with the `[spec]` marker. Inspected before applying, by extracting to
a scratch directory and diffing against the working tree rather than unpacking
over it — an unpack is indistinguishable at a glance from clobbering, and only a
diff distinguishes them. All six deletions were deliberate replacements; no test
was lost (45 to 46); D30 and my 2026-09-03 entry were present in the incoming
files, so the drop was built on current state.

**On the stale-state worry that prompted the check.** The E3 work was committed
at 22:22Z on the 3rd but not pushed until 09:24Z on the 4th, so GitHub showed
the pre-E3 state for eleven hours. The design session read after the push — its
DECISIONS.md contains D30 and it answers Q08 — so nothing was built on a stale
read. Worth recording because the gap was invisible from either side: a commit
that exists locally and a commit the other session can see are different things,
and only the push time separates them.

**Raised Q09**, non-blocking. `test_T3_6`'s docstring says the SPEC 4.4
initialisation makes `d[:, 0]` exactly zero. Measured over 200000 random inputs
at four tau pairs, it is exactly zero about 97 per cent of the time and one ulp
off otherwise — the two filter outputs are separately rounded reconstructions of
`u_0` and need not agree bit for bit. It is exactly zero for the drive the test
uses, so the test passes on the stated ground rather than on tolerance. The
worst residue is 2.6e-15 in lattice units against the 1e-9 tolerance, six orders
clear, so nothing needs changing.

**On `test_T3_6`'s provenance,** which the patch flags itself: it was written by
a session that had read `encoders.py`, and under D30 it is true by construction,
since both encoders call the same routine on the same signal with the same
anchor. It cannot fail while that structure holds. That is not an objection —
it is a regression guard against the structure being undone, which is what it
says it is — but it should not be counted as independent Layer 1 evidence that
E3 is correct. The T3 block minus T3.6 is what carries that.

**Tests:** 44 passed, 40 failed, 1 skipped, from 43/40/1. `test_T3_6` passes
against 6d69374 unchanged. The three docstring corrections change no assertion.
**Results written:** none.
**Blocked on:** nothing. Q07 and Q09 open, neither blocking.
**Next:** E4 `ALIF` wrapping `_integrate_and_fire`, as a separate session per
Simon. D24 and the `features`/`corrupt` stubs remain unblocked and independent.
