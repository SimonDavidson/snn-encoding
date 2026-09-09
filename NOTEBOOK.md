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

## 2026-09-04 | session: implementation (second entry this date)
**Did:** Implemented E4 `ALIF`, equations (22)-(23), by generalising
`_integrate_and_fire` rather than writing a second neuron. The threshold became
`theta_0 + a` with `a = rho*a + delta_a*s[n-1]`, reading the same one-step-lagged
`fired` the hard reset already reads, and E1 now calls that routine with
`delta_a=0.0`. SPEC 4.5 asks for bit-identity at `delta_a == 0`; routing both
encoders through one path makes it structural, since `rho*0.0` is `0.0`,
`delta_a*s` is `0.0` for either `s`, and `theta_0 + 0.0` is `theta_0` to the
bit. There is no branch on `delta_a` anywhere, so the property cannot be broken
by an edit that touches only one encoder. Same reasoning as D30 for E2/E3.

**The refactor moved E1's code path, so it was verified rather than asserted.**
45 cases — nine drives (constant, saturating, ramp, sine, step, noise,
speechlike, all-zero, negative) crossed with five parameter sets including two
with `refractory > 0` — dumped before the change and compared after: 180 arrays,
35708 events, identical bit for bit, `v` traces included. Failure sets were
diffed before and after as well, not merely counted; nothing that passed before
fails now.

**Refractory and adaptation:** Simon ruled that `a` keeps decaying through the
refractory period and is not incremented within it (D34). I had flagged it as
an implementation judgement call; it is unobservable in the comparison runs
where SPEC 4.5 fixes `refractory = 0.0`, but `test_G7b[E4]` runs at 4 ms and a
Layer 3 reimplementation has to make the same choice to agree event for event.

**`test_T4_3` fails and I believe the test is wrong. Raised as Q10, not
touched.** The encoder reproduces the analytic ALIF: at `delta_a = 0` the ISI is
8.13 ms against the closed form 8.11 ms, and at `delta_a = 0.5` the first
post-step ISI is 13.13 ms against a hand-solved crossing of 13.1 ms. Three
readings of equation (23) — literal, add-then-decay, increment-at-own-sample —
give *identical* early/late counts, so no implementation choice is in play.

Two separate defects, and the second is the one that matters. The estimator
`early/max(late,1)` inverts once `late` hits zero: the ratio becomes `early`,
which falls with `delta_a`, so a neuron firing once at onset and never again
scores 1.00, exactly what no adaptation scores. But the underlying claim is
false too. Re-measured on 5 s with 200 ms windows so the counts are adequate
and the steady state is genuinely reached, onset emphasis `ISI_ss/ISI_1` runs
1.00, 2.11, 2.38, **2.45**, 2.14, 1.51, 1.16 over `delta_a` = 0, 0.25, 0.5, 1,
2, 4, 8. It peaks near `delta_a ~ 1` and decays either side, and the test's two
adapting points, 0.5 and 2.0, straddle the peak. Adaptation from the first
spike suppresses the second, so strong adaptation lengthens the onset ISI
(8 ms to 139 ms) as well as the steady-state one and the two rates re-converge.
Steady-state *suppression* is monotone — that is `test_T4_4`, and it passes —
but the onset-to-steady-state *contrast* is not.

**This bears on P-01,** which predicts T1 accuracy rising and T2 falling "as
adaptation strength increases". If the onset emphasis underneath that is
non-monotone with a peak near `delta_a = 1`, a sweep spanning the peak could
confirm or contradict P-01 according to which side its points land on. The E4
sweep range should be chosen with the peak located first. `PREDICTIONS.md` not
edited — §7 forbids it once a run has started, and the restatement is the
design session's call in any case.

**Tests:** 53 passed, 31 failed, 1 skipped, from 44/40/1. The nine newly green
are `T4_1`, `T4_2`, `T4_4` and `G1/G2/G3/G4/G7/G7b[E4]`. `G8[E4]` stays red on
the `features` stub, as it does for every encoder. `T4_3` red — Q10.
**Results written:** none.
**Blocked on:** nothing for implementation. Q10 blocks declaring E4's Layer 1
complete and blocks choosing the `delta_a` sweep range. Q07 and Q09 open,
neither blocking.
**Next:** E5 `PhaseLocked` as a separate session, one encoder per review gate.
D24 (whole-path group-delay compensation, `test_F6`) and the `features` and
`corrupt` stubs remain unblocked and independent of it — the `features` stub
alone is holding six `G8` tests red across all encoders.

## 2026-09-04 | session: implementation (third entry this date)
**Did:** Pushed the E4 work and opened issues #1-#3 for Q10-Q12 on Simon's
instruction. Then, E5 being blocked, implemented `spikeenc.corrupt` (SPEC §7,
all four operators) and `spikeenc.features.featurise` (SPEC §5, equation 32).

**E5 was not started, and the reason is Q11.** Before writing any of it I
simulated the SPEC §4.6 deterministic rule directly — upward zero crossings of
the subband, gated by envelope > threshold, then refractory — on the `test_G3`
drive. The declared RATE_PARAM moves the event count 7116 to 6864 across the
16x sweep, a span of 1.04x against D27's required 4x. It is the Q06 failure
shape exactly: the count is bounded by the subband's zero-crossing rate, which
is a property of the carrier, and `threshold` only gates quiet passages, of
which this drive has few (envelope p25 = 0.266 against a top threshold of 0.20).
Proposal §5.5 nominates `lambda_max` for the stochastic form, but equation
(25)'s `lambda_max` and `z_0` are not constructor arguments, so the mode that
has a working rate parameter cannot express it. Q12 records two further gaps:
which envelope gates the crossings, and what parameters the LIF fallback above
`f_lock` uses. Measured without writing the encoder, so nothing needs undoing
when the answers arrive.

**`featurise` checked against the defining equation, not against its test.** The
shipped version accumulates recursively, `phi[k] = phi[k-1]*exp(-hop/tau) + ...`,
which is O(N+F) rather than O(N*F). The closed form
`exp(-t_k/tau) * cumsum(exp(t_j/tau))` was rejected: `exp(t/tau)` overflows a
double at t/tau ~ 710, which is 3.6 s of audio at the default tau. Compared
against a literal double-sum transcription of equation (32) on E1, E3 and E4
trains, the worst relative error is 9.4e-16, a few ulp. Order invariance is
bit-exact under permutation rather than merely inside the test's rtol=1e-10,
because events are lexsorted before anything is accumulated — summation over a
set is order-invariant in exact arithmetic and not in floating point, and
`test_G8` is precisely a test of that. `split_polarity=False` reproduces the ON
and OFF halves folded together to 1.1e-16.

**`test_corrupt_delete_retains_expected_fraction` fails on its precondition,
not on the operator. Raised as Q13, not touched.** The fixture yields 275
events where the guard requires more than 500. `delete` itself is right:
retention is 0.7382, inside the 0.65-0.75 window. E1's 275 is exact — identical
at 2x, 4x, 8x and 16x oversampling, so no events are being lost between
samples — and the per-channel spread 12/48/84/131 is what `drive_for`'s
0.6/0.8/1.0/1.2 scaling predicts at theta = 1.0. The guard is not spurious: at
N = 275 the window is +/-1.81 binomial sd and holds for 93.1 per cent of seeds,
against +/-2.44 sd and 97.7 per cent at N = 500. `duration=8.0` would give 551.

**Tests:** 60 passed, 24 failed, 1 skipped, from 53/31/1. Seven newly green:
the three working corruption operators and `G8` for E1-E4. `G8[E5]` and
`G8[E6]` stay red on the encoder stubs rather than on `features`, which is
correct. Failure sets diffed, not counted; no regressions.
**Results written:** none.
**Blocked on:** E5 blocked on Q11 and Q12 (issues #2, #3). Q10 (#1) blocks
declaring E4's Layer 1 complete. Q13 blocks one test's green tick and nothing
else. Q07 and Q09 open, neither blocking.
**Next:** E5 once Q11 and Q12 are answered — the constructor signature is in
question, so writing it first would risk rework. Unblocked and independent
meanwhile: D24 whole-path group-delay compensation (`test_F6`), and E6 `TTFS`,
whose SPEC §4.7 I have not yet read against its T6 block. The remaining 24
failures are E5 (7), E6 (8), T6 (3), T5 (4, three of which need E5), F6 (1)
and Q13's precondition (1).

## 2026-09-05 | session: implementation
**Did:** Session opened after a reboot. Established state per the CLAUDE.md
startup sequence: nothing had drifted, 60/24/1 exactly as the last entry left
it, working tree clean, `main` level with `origin/main`. Design session is
token-limited for about three days (Simon), so the plan is to work the
unblocked queue rather than wait.

**Probed E6's rate parameter before writing the encoder, as Q11 taught. It
fails D27, and not for the reason `test_G3` predicts. Raised as Q14, issue
#5.** At the registry's `e_min = 1e-6` the 16x sweep gives 792 events at every
one of the five points — exactly the ceiling `n_ch * n_frames` — for a span of
**1.000x**. Frame energy on `drive_for` runs min 6.24, median 286, max 1852, so
`1e-6` sits 6.8 decades below the quietest frame and gates nothing at all.

But `e_min` is a working rate parameter, unlike E5's `threshold`. Swept where
the energies actually live it moves the count 792 -> 744 -> 640 -> 534 -> 401
-> 186 -> 78 -> 0. So `test_G3`'s docstring, which names E6 as the foreseeable
D27 casualty whose count is "structurally fixed" and prescribes taking matched
budgets from channel count or frame rate, does not describe E6. This is a
default in the wrong place. I cannot fix it: the value lives in
`tests/conftest.py` and SPEC 4.7, both design-session files, and there is no
change in `src/` that turns the test green. Q14 offers an absolute retune (any
base in 205.8-462.8 clears 4x; midpoint 308.8 gives 7.1x) against a relative
`e_min` as a fraction of max frame energy, which is scale-free — verified
identical counts across five decades of drive scale — and which would also
define the `E_max` that equation (28) needs and SPEC 4.7 does not supply. The
relative form needs a strict `>` gate: written `>=` it emits 392 events on
silence, because `E_max` is 0 there and `0 >= 0` holds. Both forms pass G4.

**Then D24, whole-path group-delay compensation. `test_F6` green.** The defect
was as SPEC section 3 describes it: compensation lived inside `subbands`, and
`envelope` called `subbands` and then added lowpass lag downstream that nothing
removed, so the flag reported alignment while leaving most of the skew. Measured
stage budget on a broadband click, 16 channels, 150-6000 Hz:

| stage | onset spread across the bank |
|---|---:|
| gammatone lag alone, analytic | 10.76 ms |
| hilbert envelope, measured | 10.75 ms |
| rectify_lowpass envelope, measured | 22.63 ms |
| extra spread contributed by the lowpass | 11.88 ms |

The lowpass is the larger contributor at every channel — 12.62 ms against the
gammatone's 11.46 ms at channel 0 — exactly as D21 predicted it would be once
the cutoff became channel-relative. Compensating the gammatone alone removed
48 per cent of the skew. SPEC section 3 predicted "roughly two thirds" would be
left in place; the measured figure is 52 per cent.

**`test_F6` margins, which its docstring asks to be recorded so the thresholds
can be tightened later:**

| method | uncompensated | compensated | test limit | margin | residual |
|---|---:|---:|---:|---:|---:|
| hilbert | 10.75 ms | 0.00 ms | 3.58 ms | 57.3x | 0.0% |
| rectify_lowpass | 22.63 ms | 2.50 ms | 7.54 ms | 3.02x | 11.0% |

The 2.50 ms residual is the declared DC group delay under-reading the lag a
rectified carrier burst actually experiences: the lowpass lag measured from the
click is about 1.09x the gammatone lag, while the declared DC value is 0.87x
it. SPEC section 3 anticipates this — compensation is exact only for components
slow relative to the stage bandwidths — so I have implemented the declaration
SPEC specifies and measured what it achieves rather than tuning the declaration
to flatter the test. Any T3 result taken with compensation on should quote the
2.50 ms.

**The restructuring removed a second defect that no test detected.** Old code
shifted the subband before the Hilbert transform; new code takes the envelope
first and shifts once at the end. Those are not the same operation, because the
shift truncates and zero-pads and `hilbert` is a global FFT: the pad
discontinuity rang back through the channel. Against an envelope scale of
1.9e-2, the old and new compensated hilbert paths differ by 1.6e-2 in the pad
region, 5.0e-3 in the first `lag` samples and 2.2e-4 in the interior — about
1 per cent of envelope amplitude, everywhere, in a path that looked correct.
`test_F6` could not see it because it measures peak position and the ringing
moves amplitude, not the peak. Nothing had run with compensation on, so no
result is affected.

**Implementation choice worth a Dnn if Simon agrees, D20-shaped.** The lowpass
lag is taken as the first moment of the designed filter's impulse response,
`sum(n*h[n]) / sum(h[n])`, which is the DC group delay exactly and is computed
from the digital filter actually used. `scipy.signal.group_delay` needs
transfer-function coefficients, which SPEC section 3 records as numerically
unreliable at these normalised cutoffs; the analog Butterworth prototype
ignores bilinear prewarping. The prototype agrees to within 0.6 per cent worst
case (1.0000 at the low channels, 0.9940 at channel 15), which is ~60 us
against a 2.50 ms residual, so a Layer 3 reimplementation choosing either route
lands in the same place.

**Verified rather than assumed.** Failure sets diffed against the pre-patch
run, not counted: exactly `test_F6` removed, nothing introduced. Uncompensated
`subbands` and all three `envelope` methods are bit-identical to the pre-patch
code, as is the compensated `subbands` path, so the default path every current
test uses has not moved. The compensated `envelope` paths change, which is the
point. The D24 raise clause fires for an undeclared method rather than
returning zero. The lowpass lag is computed from the `f_cut` and
`lowpass_order` actually passed, not from a cached default, so a non-default
cutoff cannot silently compensate by the wrong amount.

**Tests:** 61 passed, 23 failed, 1 skipped, from 60/24/1. One newly green:
`test_F6`. No regressions; failure sets diffed.
**Results written:** none. See the open question about experiment records at
the end of this entry.
**Blocked on:** E5 on Q11/Q12 (#2, #3). E6's Layer 1 on Q14 (#5) — though the
encoder itself is writable now, since T6_1-T6_3 all construct with `e_min=0.0`
and are indifferent to the default. Q10 (#1) blocks declaring E4 complete and
bears on P-01. Q13 (#4) blocks one test. Q07, Q09 open, neither blocking.
**Next:** E6 `TTFS` is the largest unblocked block of work — writable now,
leaving only `test_G3[E6]` red pending Q14. `results/` is still empty and no
manifest entry has ever been written; Simon has raised the record-keeping
question and it needs settling before the first sweep, not after.

## 2026-09-05 | session: implementation (second entry this date)
**Did:** Built the run-provenance machinery Simon asked for after the
record-keeping question at the end of the previous entry. D35, D36 added.

**The state I found.** The reasoning record is in good order — NOTEBOOK
append-only, DECISIONS at D34, QUESTIONS at Q14, and PREDICTIONS P-01 to P-08
dated 2026-08-20, which is to say pre-registered before any run, the part that
cannot be retrofitted. The experimental record was empty, which was correct so
far: no experiment has run, and everything to date is Layer 1 verification. But
the *machinery* was also absent — `results/manifest.json` held a schema and an
empty `entries` list, and `configs/` and `scripts/` did not exist as
directories. The first sweep would therefore have been the first test of the
plumbing as well as the first result.

**The gap that mattered more.** The probe measurements of the last few sessions
are results in everything but name, and they lived only as prose and tables in
NOTEBOOK and QUESTIONS, produced by scripts in a session-scoped scratchpad that
is deleted when the session ends. The sharpest case is the 2.50 ms group-delay
residual: SPEC section 3 *requires* it be quoted alongside any T3 result taken
with compensation on, and asked "how did you get 2.50 ms" the honest answer
this morning was "it is written in the notebook".

**What was built.** `spikeenc.provenance.record` writes the data file and the
manifest entry together or does neither, so a result cannot be produced without
being registered. Configs are JSON — no yaml in the environment, no new
dependency, and configs are committed and reviewed so they need to diff
cleanly. Small results are JSON under `results/` and committed; bulk arrays go
to `.npz`, which `.gitignore` already excluded, so numbers that reach the paper
stay in the repository while large arrays stay local.

**Two guards, the second of which I did not anticipate needing.** The obvious
one refuses to record from a dirty tree, since "commit hash at time of run"
names a state that never produced the numbers if the tree has moved. But
`git status --porcelain --untracked-files=no` ignores untracked files, and a
brand-new script is untracked — so the first version of the check would have
happily recorded a result against a commit that did not contain the script that
produced it. `assert_committed` now separately requires the script and the
config to be tracked and unmodified. It fired correctly on the first run
attempt, which is how I found it.

**Worked example, and it earned its keep immediately.**
`scripts/measure_group_delay_residual.py` with
`configs/front_end_group_delay_residual.json` records the D24 residual. Running
it exposed a defect in my own helper: `json.dump` emits `Infinity` and `NaN` as
a non-standard extension, so the hilbert margin — undefined, since the residual
is exactly zero — was written as `Infinity` into a file meant to be committed
and read by other tools. A strict parser rejects it. `_jsonable` now maps
non-finite floats to null and `json.dump` runs with `allow_nan=False` as a
backstop. This is exactly the argument for establishing the convention on
something small first: the defect would otherwise have surfaced in the first
real sweep.

Both botched intermediate runs were removed rather than superseded, because
neither had been committed — there was no record to preserve, and the measured
numbers never changed, only their serialisation. Recording that here rather
than leaving it silent.

**Recorded:** `results/front_end_group_delay_residual.json` and its `.npz`,
manifest entry `front_end_group_delay_residual`, commit `2017ecf`, seed 0. The
stimulus and the whole path are deterministic, so the three-seed rule does not
apply — there is nothing for a seed to vary — and the config says so rather
than leaving a reader to wonder why one seed was enough.

**Tests:** 61 passed, 23 failed, 1 skipped. Unchanged — this session's work
added no test and broke none.
**Results written:** `results/front_end_group_delay_residual.json`,
`results/front_end_group_delay_residual.npz`, registered in
`results/manifest.json` as the first entry that file has ever held.
**Blocked on:** unchanged — E5 on Q11/Q12 (#2, #3), E6's Layer 1 on Q14 (#5),
Q10 (#1) on declaring E4 complete, Q13 (#4) on one test. Design session
token-limited until about 2026-09-08.
**Next:** E6 `TTFS` is the largest unblocked block — writable now, since
T6_1-T6_3 all construct with `e_min=0.0`, leaving only `test_G3[E6]` red
pending Q14. Item 3 of the record-keeping proposal is *not* done: the Q03
envelope table, the Q11 1.04x measurement, the Q14 energy distribution and the
`featurise` accuracy check are still notebook prose with no committed script
behind them. They should be retro-fitted while the method is still fresh.

## 2026-09-05 | session: implementation (third entry this date)
**Did:** Retro-fitted the remaining paper-bearing probe measurements as
committed script and config pairs — item 3 of the record-keeping proposal in
the second entry. `results/manifest.json` now holds five entries where this
morning it held none. Raised Q15.

**Built.** `scripts/measure_envelope_cutoff.py` (Q03/D21),
`scripts/measure_rate_parameter_span.py` with configs for E5 and E6 (Q11, Q14),
and `scripts/verify_featurise_accuracy.py`. The span script takes its rule from
its config so E5 and E6 share one implementation, which makes the D27 span
check a reusable tool for the remaining encoders rather than a one-off — the
measurement the memory habit says to run before writing any encoder now has a
home. Both span configs import the drive from `tests/conftest.py` rather than
rebuilding it, so the measurement is on `test_G3`'s own drive and cannot drift
away from it.

**Two of the four reproduce the record exactly; two do not, and Q15 records
it.** E6's span reproduces exactly (792 flat, 1.000x). E5's span reproduces
(1.039x against the recorded 1.04x) though its absolute counts do not — 6996
falling to 6732 against the recorded 7116 to 6864 — almost certainly because
SPEC 4.6 does not say which envelope gates the zero crossings and neither probe
recorded its choice. That is the first half of Q12, and this is further
evidence for it rather than a new question.

**The Q03 envelope table half-reproduces, and the half that fails is
informative.** All eight correlation values reproduce to four decimal places,
which confirms the bank and stimulus reconstruction — it is test_F4's bank,
channels 2, 6, 10 and 18. The carrier-leakage column does not: the recorded
values are 10 to 600 times smaller, and the answer's quoted margins of 1.4x,
30x, 128x and 419x come out here as 1.2x, 5.6x, 11.3x and 20.4x. D21 itself is
untouched — this run also has D21 winning at every channel by a margin growing
with frequency — but the size of the margin is not reproducible, because the
metric definition was never written down.

I checked my own metric rather than assuming it. Leakage should be the
lowpass's gain at f_c times a constant set by the rectified waveform's harmonic
content, and it is: the ratio is *identical for both cutoff rules at each
channel*, 0.42, 0.36, 0.50, 0.50. That also disposes of a suspicion I had
formed and recorded — the f_c/4 column looked implausibly flat, and I guessed
FFT sidelobe leakage. Windowing changed nothing. The real reason is that the
f_c/4 rule holds f_c/cutoff at exactly 4 for every channel, so its attenuation
is constant by construction. The flatness was correct and my hypothesis was
wrong.

**The `featurise` figure reproduces, and identifies its own normalisation.**
9.4e-16 is the scaled measure — divide by the largest value in the array — and
E4 gives 9.39e-16. But it was not the worst of the three: E3 gives 1.31e-15,
about 40 per cent larger. Both that and the pointwise measure, about 2e-14, are
now recorded and named, since the gap between them is entirely definitional. My
first attempt at the note in the result file claimed neither measure reproduced
the figure; that was wrong and was corrected before the result was committed.

**Two defects in yesterday's provenance helper, both found by using it.**
First, the dirty-tree guard refused the *second* of four runs, because
recording a result writes into `results/` and so makes the tree dirty. `results/`
is output, not code; it is now excluded, and `assert_committed` on the script
and config remains the guarantee that matters. Second, the `np.int64` repr was
leaking into a committed script's printed output. Neither would have been found
without four real users of the helper, which is the argument for item 3 having
followed items 1 and 2 rather than waiting.

**Tests:** 61 passed, 23 failed, 1 skipped. Unchanged — no test touched.
**Results written:** `results/envelope_cutoff_comparison.json`,
`results/e5_rate_parameter_span.json`, `results/e6_rate_parameter_span.json`,
`results/featurise_accuracy.json`, all registered in `results/manifest.json`,
which now holds five entries. Every result file verified to parse under a
strict JSON reader.
**Blocked on:** unchanged. E5 on Q11/Q12 (#2, #3), E6's Layer 1 on Q14 (#5),
Q10 (#1), Q13 (#4). Q15 blocks nothing. Design session token-limited until
about 2026-09-08.
**Next:** E6 `TTFS`. It is writable now despite Q14 — T6_1 to T6_3 all
construct with `e_min=0.0` and are indifferent to the default — and would clear
eight of the twenty-three failures, leaving only `test_G3[E6]` red pending Q14.

## 2026-09-05 | session: implementation (fourth entry this date)
**Did:** Probed SPEC 4.7 before writing E6. Raised Q16 (issue #7). Nothing
written to `src/`; the encoder was not started, and that is the right outcome
rather than a stalled one — three gaps were found for the cost of a prototype
that was thrown away, and none of them would have been visible from reading
the section.

**Finding 1: equation (28) has no `E_max`.** Not a constructor argument in the
SPEC 4.7 signature, not defined in SPEC 4.7 or proposal 5.6. Utterance-maximum,
frame-maximum and a fixed constant all give different event times and a Layer 3
reimplementation has nothing to choose between them. Q14 option 2 would close
this from the other direction, so Q14 and Q16 should be answered together.

**Finding 2: equation (28) is not evaluable at `e_min = 0`,** which is what
`test_T6_1` and `test_T6_2` both pass, with `mode="log"` the SPEC 4.7 default.
`log 0 = -inf` makes the normalised term `inf/inf`. `E_min` is doing two jobs in
proposal 5.6 — the emission gate and the normalisation floor — and zero is legal
for the first and not the second.

**Finding 3: `test_T6_1` and `test_T6_2` cannot be satisfied by any
implementation at `hop < frame`.** Both pass `frame=0.025, hop=0.010`, so
windows overlap by 15 ms, and both then treat `[m*hop, m*hop+frame)` as holding
frame `m`'s events when it holds three frames' worth. Measured on a prototype,
8 channels, 1 s: 98 of 98 windows contain a duplicated channel, and no clipping
choice changes that. This is not an encoder defect and cannot be worked around.

Two causes, separated by measurement rather than argument:

| hop | offset clipped to | T6_1 duplicate windows | T6_2 worst \|rho+1\| |
|---|---|---:|---:|
| 10 ms | frame | 98/98 | 1.2301 |
| 10 ms | strictly inside | 98/98 | 1.2301 |
| 25 ms | frame | 1/40 | 0.6000 |
| 25 ms | strictly inside | 0/40 | 0.0000 |

The overlap is fatal and is the design session's. The single remaining failure
at `hop = frame` is mine: equation (28) maps `E = E_min` to an offset of exactly
`T_f`, which lands on `m H + T_f` and so falls outside its own half-open window
and into the next one. Clipping strictly inside takes both tests to exact
agreement. That is a D20-shaped implementation decision and is recorded in Q16
rather than acted on, since it is moot until findings 1 and 2 are resolved.

**`mode="lif"` is clean.** Equation (29) involves no `E_min` or `E_max`,
`test_T6_3` sets `hop = frame` so there is no overlap, and the closed form
reproduces: `I = 4.0`, latency 5.7536 ms, inside the 25 ms frame.

**Two implementation routes were put to Simon and he chose neither, correctly.**
A provisional `E_max` reading — utterance maximum, with `E_min` falling back to
the smallest positive observed energy — was prototyped and takes G1, G2, G4,
G7, G8 and T6_3 green, six tests. The alternative is `mode="lif"` alone, which
greens one and guesses nothing. Simon stopped rather than pick, on the grounds
that the open-question queue is now long enough that guessing compounds, and is
attempting to unblock the design session instead. Recording that the six-test
route exists and was declined deliberately, so a later session does not
rediscover it and assume it was overlooked.

**Tests:** 61 passed, 23 failed, 1 skipped. Unchanged — no code written.
**Results written:** none this entry.
**Blocked on:** nine open questions, seven with issues. E6 on Q16 (#7) and Q14
(#5); E5 on Q11 (#2) and Q12 (#3); E4's completion and P-01 on Q10 (#1); one
test each on Q13 (#4); Q15 (#6) corrects the record and blocks nothing; Q07 and
Q09 block nothing. Design session token-limited; Simon attempting to restore it
2026-09-06.
**Next:** nothing implementable without an answer. When answers arrive, the
order that clears most is Q11+Q12 (twelve tests, E5 and the whole T5 block),
then Q16+Q14 (eight, E6 and T6), then Q10 and Q13 (one each). If only one
answer comes back, Q10 is the one with consequences beyond a red test: P-01
predicts T1 accuracy rising and T2 falling with adaptation strength, and the
onset emphasis underneath it is non-monotone with a peak near delta_a = 1.

## 2026-09-06 | session: implementation
**Did:** Built `reports/spikeEncode_encoder_survey.docx` and its generator,
`scripts/build_encoder_report.py`, at Simon's request — a 26-page survey of
every encoder planned or implemented: methodology and defining equations,
design parameters and which are swept, output characteristics, verification
status, and recorded results. Between 1.7 and 3.1 pages per encoder, plus the
shared front end, the featurisation and corruption machinery, the manifest, the
open questions ordered by what each unblocks, and the pre-registered
predictions. Narrative is authored in the script; every number is read from
`results/` and the manifest at build time, so a rebuild after a run picks up
new values rather than restating stale ones. The build is deterministic —
python-docx stamps the current time into the archive, so an unchanged report
would otherwise diff on every rebuild and a real content change would be
indistinguishable from noise.

**The observation that matters more than the report.** Prompted by Simon
sending it to Oliver, I checked the work against the twelve-week schedule of
proposal §9 for the first time. Today is day 18, week 3 of 12 against the D11
start of 2026-08-20, and the picture is lopsided:

| | §9 asks for | Actual |
|---|---|---|
| Weeks 1-2 | Data pipeline, probe harness, budget and information accounting, experiment tracking. Deliverable: E1 end to end on TIMIT with a T1 linear probe. Concurrently resolve the TIMIT licence. | Not started. No data loader, no probe, no training code in `src/`; `data/` holds only `.gitkeep`. |
| Week 3 (now) | Preliminary P1, count-only baseline on E1 across all three tasks | Cannot start |
| Week 4 (next) | Preliminary P2 — DECISION GATE, battery confirmed or revised | Unreachable |
| Weeks 5-7 | Implement E2-E6 | E2, E3, E4 done — two to four weeks ahead |

So the encoder work has run well ahead of schedule and the infrastructure
everything downstream depends on has not been touched. The week 4 decision gate
cannot be reached next week, because P1 and P2 both need a corpus and a probe
harness and neither exists. **The TIMIT licence has not appeared in any log
since 2026-08-20**, eighteen days, and §9 names it as the top risk in rough
order of likelihood precisely because it is week one work.

**This is my miss and it is worth naming.** I have spent every session since
2026-09-02 optimising against the known-answer suite, which the validation
protocol does demand, and never once opened §9 to check what the schedule
wanted. The suite is a correctness instrument, not a progress one: it goes green
in the order the encoders are written, and says nothing at all about work that
has not been started. Nothing in the startup sequence of CLAUDE.md points at the
schedule either, which is how it stayed invisible for eighteen days.

**Consequence for the next block of work.** The whole weeks 1-2 deliverable is
*unblocked*. E5 and E6 are stuck behind Q11, Q12, Q14 and Q16, but the probe
harness, the budget and information accounting, R2 the mel baseline and the
P1/P2 scaffolding depend on none of them, and most can be built and tested on
synthetic drive while the licence is resolved. That is the work standing between
the project and its first actual result.

**Tests:** 61 passed, 23 failed, 1 skipped. Unchanged — no encoder code touched.
**Results written:** none. The report reads existing results; it adds none.
**Blocked on:** unchanged — nine open questions, seven with issues. Design
session token-limited; Simon attempting to restore it.
**Next:** Simon meets Oliver on **Tuesday 8 September 2026** and has sent him
the report. **Hold any email drafts until early Tuesday** — Simon's explicit
instruction, on the grounds that there may be more to say by then. A response
from the design session is expected to be uploaded into a fresh session before
that. When it arrives, Q11+Q12 clears the most (twelve tests), then Q16+Q14
(eight), then Q10 and Q13. If instead the schedule is the priority coming out of
Tuesday, start the probe harness rather than an encoder.

## 2026-09-06 | session: design
**Did:** Answered Q09 through Q16 in one patch (D38-D46), appended the Q03
correction, and drafted the P-01 amendment. Nothing here needed the encoders to
exist; every answer was derivable from the equations plus the implementation
session's measurements, which is why eight could be cleared at once after none
were cleared for two days.

**The queue was a throughput mismatch, not a quality problem.** Q11 taught the
implementation session to probe a specification section before writing against
it, and Q14 and Q16 are the result: three gaps in SPEC 4.7 found for the cost
of a prototype that was thrown away, rather than for the cost of an encoder
that had to be unwound. That change is working. It also produces questions
faster than one design session answers them, and the two-day stall is the
visible form of that. Worth watching rather than fixing — E5 and E6 are the
last two encoders, so the probing phase is nearly over.

**Stopping rather than picking a provisional `E_max` was right.** The six-test
route existed and was declined. Had it been taken, `test_G1`, `G2`, `G4`, `G7`,
`G8` and `T6_3` would all be green now against a definition of `E_max` that
this patch would then have contradicted, and the green ticks would have been
the reason nobody looked again.

**Three answers departed from every option offered, and in the same direction
each time.** Q10, Q11 and Q13 were all answered with a fifth option. The
pattern is not that the options were poor — they were carefully separated and
measured — but that each set was framed as a choice among ways to accommodate a
constraint, where the better move was to change the quantity being measured.
Onset emphasis against the first ISI became onset emphasis against an invariant
latency; a threshold that gates became a divisor that modulates; one draw made
more reliable became twenty draws measuring the rate. Worth noticing as a habit
to apply deliberately rather than by luck.

**Q15 corrects my own Q03 answer and the correction is right.** Checked
independently rather than deferred: under D21 the cutoff tracks the ERB, so
`f_c/b_c` runs about 4.3 at 196 Hz against 8.6 at 3057 Hz, and fourth-order
attenuation should improve by roughly seventeen times across that span. The
recorded column falls by eight hundred. D21 still wins at every channel, so the
decision stands and only the margin was wrong.

**P-01a is drafted and is not live.** PREDICTIONS.md carries it with a
sign-off marker that only Simon removes, and the original P-01 is left visible.
The case for amending rather than restricting rests entirely on provenance: the
measurement came from a step response on a synthetic drive, with no dataset, no
probe task, no labels and no run started. If that sentence were not true the
amendment would not be defensible.

**Tests:** none run — no environment here. Two expectations to check rather
than assume: `test_G3[E5]` under `cycle_divisor` is specified without having
been measured, and if the sweep comes in under 4x that is a finding to raise
rather than a threshold to relax; and `test_T4_3`'s ratio column is predicted
from Q10's own table, not recomputed here.
**Results written:** none.
**Blocked on:** Q07, open with Oliver and blocking nothing until packaging.
Nothing else.
**Next (implementation session):** E5 under D40 and D41, then E6 under D43 and
D44. E4's Layer 1 completes when the rewritten `test_T4_3` goes green.

## 2026-09-07 | session: implementation
**Did:** Implemented E5 `PhaseLocked` under SPEC 4.6 as rewritten by D40 and
D41. Ten of its twelve tests green; the two that are not are Q19 and Q20, both
raised before the encoder was written and neither fixable from `src/`.

**Prototyped against the real tests before writing anything.** The habit paid
twice. `test_G4` failed by sixteen events, and the cause was mine: the
refractory compared absolute event times, and `(i+s)*dt - (j+s)*dt` is not
bit-identical to `i*dt - j*dt`, so an interval of exactly `refractory/dt`
samples — and 1 ms is exactly 16 samples at 16 kHz — decides differently at
different offsets. `_integrate_and_fire` already uses the integer sample
difference `(i - last) * dt` for precisely this reason, so the fix was to
follow the house convention rather than invent one, and no new decision is
needed. The `e5_cycle_divisor_span` probe had the same defect and its recorded
result was re-run and superseded: 3.54x rather than the 3.48x first reported.

**Q20 was the second thing the prototype found.** `test_T5_3` cannot pass at
D40's `cycle_divisor` default of 4. The harmonic complex has exactly one upward
zero crossing per F0 period, which is *why* the pooled ISI histogram peaked at
1/F0; keeping every k-th survivor moves the peak to k/F0, so the test asserts
8.00 ms against a measured 32.12 ms. No implementation reading avoids it. This
is the test whose docstring calls F0 recovery "the one job the encoder exists
to do", so it is worth more than a red tick.

**Verified beyond the suite.** SPEC 4.6 states an identity that no test
asserts: E5 with `f_lock` below every centre frequency must equal E1 on the
same internal envelope, event for event. My first check of it was **vacuous** —
`speechlike` is quiet enough that the rectified, lowpassed envelope never
reaches the LIF's threshold of 1.0, so both sides produced zero events and
agreed trivially. Re-run at 6x and 12x amplitude the identity holds properly,
24 and 183 events, bit-identical in channel, time and polarity. A mixed bank
routes correctly too: with `f_lock = 1500` and centre frequencies 300, 800,
3000, 6000 the counts are 661, 661, 24, 24, the last two matching a standalone
LIF on those channels' envelopes. Recording the vacuous first attempt because a
check that passes on empty output is worse than no check.

**One reading recorded rather than raised.** SPEC 4.6 does not say whether
`refractory` applies in `mode="poisson"`. It is applied, on the grounds that it
is a declared parameter of the encoder and a refractory period is
physiological. Not raised as a question because that mode is excluded from the
comparison of section 6.4 and from `test_G3` and `test_G4`, and no test
exercises it; the reading is in the method docstring where a Layer 3
reimplementation will find it.

**A test that passes for the wrong reason, flagged and not yet raised.**
`test_T5_2` asserts vector strength below 0.35 above `f_lock`, and it passes —
but with **zero events**, not with unlocked ones. The internal envelope of a
unit-amplitude 5 kHz tone is about 0.313, well under the fallback LIF's
threshold of 1.0, so nothing fires, and `metrics.vector_strength` returns 0.0
for fewer than two events by SPEC section 6. The assertion is satisfied by
silence rather than by loss of locking. Simon has the flag; whether it becomes
a question is his call, since the queue already carries Q19 and Q20 against
this encoder.

**Tests:** 73 passed, 11 failed, 1 skipped, from 63/21/1. Ten newly green:
`T5_1`, `T5_2`, `T5_4` at both sigmas, and `G1`, `G2`, `G4`, `G7`, `G7b`, `G8`
for E5. Failure sets diffed, not counted; no regressions. The eleven remaining
are E6 (9), `test_G3[E5]` (Q19) and `test_T5_3` (Q20).
**Results written:** `results/e5_cycle_divisor_span.json` re-recorded under the
corrected refractory, the first entry marked superseded in the manifest.
**Blocked on:** Q19 and Q20 for E5's last two tests; Q07, Q17, Q18 open and
blocking nothing. E6 is unblocked and unwritten.
**Next:** E6 `TTFS` under D43 and D44 — nine tests, and its rate parameter is
already verified, Q14 having measured `e_frac = 0.20` at 12.4x. After that the
probe harness, which remains the schedule critical path and is still untouched.

## 2026-09-07 | session: implementation
**Did:** Implemented E6 `TTFS` under SPEC 4.7 as rewritten by D43 and D44. All
nine of its tests green. **No test in the suite now fails for a reason inside
`src/`** — the two remaining failures are Q19 and Q20 against E5, both raised
before E5 was written. That closes the encoder block: E1 to E6 are done, which
is the whole of proposal §9 weeks 5-7.

**The three properties of one sentence, each paid for by a question.** The gate
is `E > e_frac * E_max`: relative (Q14, because an absolute `e_min` sat 6.8
decades below the quietest frame and gated nothing), strict (Q14, because a
non-strict gate emits everywhere on silence when `E_max` is zero), and taken
over all channels and all frames (Q16, because the per-channel reading is the
more natural one to write and destroys the spectral profile). Each is argued in
the class docstring rather than left as a line of code, because a Layer 3
reimplementation would otherwise choose differently on all three.

**Checked that `test_T6_2` actually bites.** D44 claims the rewritten test
detects the per-channel `E_max` reading. It does: subclassing the encoder to
take the maximum per channel gives a worst Pearson residual of **1.89**,
against 3.3e-16 as shipped and a tolerance of 1e-9. Worth doing because the
claim is the entire reason the test was changed from Spearman to Pearson, and a
test believed to bite and not biting is worse than no test.

**The knife edge in the frame count was real and is why I checked it.** SPEC
4.7 gives `n_frames = floor((n*dt - frame)/hop) + 1`, and `test_T6_3` sets
`frame == hop == n*dt`, so the expression is exactly zero and one frame is
expected. Had `n*dt` come out at 0.024999999999999998 the floor would be -1,
the encoder would produce nothing, and the failure would look like a defect in
equation (29). It evaluates exactly, at every frame and hop the suite uses, and
agrees with the integer-sample form everywhere. Measured rather than assumed.

**Margins rather than passes.** G3 span 12.36x against D27's 4x; T6_1 maximum
offset 2.22 samples inside the frame boundary; T6_2 worst |r+1| 3.3e-16 against
1e-9; T6_3 latency error exactly **0.0** against a tolerance of 1.5 samples;
G4 padded and unpadded `E_max` bit-identical at 1851.1720612197246, which is
the figure Q14 quotes to six decimals.

**Branches the suite does not reach, probed with warnings promoted to errors.**
Mode validation, `e_frac <= 0` raising in log mode and *not* in lif mode, a
drive shorter than one frame, an empty drive, `hop > frame`, `e_frac` at and
above 1.0, and silence in both modes. No warnings, no nans escaping, state
matrices correctly shaped at `(n_ch, 0)` on a sub-frame drive.

**One reading recorded rather than raised, as with E5's poisson refractory.**
Equation (29) is unbounded as `I` approaches `theta`: at `I = 1.001` it gives
138 ms inside a 25 ms frame. `mode="lif"` suppresses such an event, on the
reading that the neuron did not reach threshold within its window. Verified at
the boundary — `I = 1.2` gives 35.8 ms and is suppressed, `I = 2.0` gives
13.9 ms and fires. It is in the method docstring where a Layer 3
reimplementation will look, and **not** in `DECISIONS.md`: `mode` is not a
swept axis of proposal §6.6 and no test reaches the boundary. Unlike E5's
poisson mode, though, nothing *logged* excludes lif mode from a future run, so
Simon has the flag and it is his call whether it becomes a Dnn or a Qnn.

**Q21 is the units of a figure, not the figure.** Re-measuring the two E6
numbers that reach the paper draft from the Q14 prototype — which was discarded
without a manifest entry — reproduced every one: 12.36x against 12.4x, `E_max`
0.185 to 1.85e7, identical counts at every scale. What did not reproduce is
"five decades of input scale", quoted in the Q14 answer and in proposal §5.6.
It is five scale *points*, four decades of amplitude, eight of frame energy.
The claim is understated rather than overstated, and nothing turns on it, but
it is the third figure in three sessions quoted without the definition of what
was measured, and it is in the document that goes to Oliver.

**The survey report is now materially stale and I have not rebuilt it.**
Rebuilding would make it worse. Its numbers come from `results/` at build time
but its narrative is authored in the script, and six passages are now false:
the status callout ("four of the six are implemented", "E5 and E6 are
specified but blocked"), three table rows (E5 and E6 still shown as Blocked at
0/12 and 0/9, with their superseded RATE_PARAMs `threshold` and `e_min`), and
the caption asserting that both raise `NotImplementedError`. Correcting that is
writing, not regeneration, and it is a document Simon has already sent to
Oliver with a meeting tomorrow, so it is his call and not a mechanical rebuild.

**Schedule.** Day 19, week 3 of 12 against the D11 start. Weeks 5-7 are now
complete and weeks 1-2 are still not started: no data loader, no probe harness,
no training code. The 2026-09-05 entry left a standing instruction to start the
probe harness rather than an encoder if the schedule is the priority coming out
of Tuesday's meeting with Oliver. There are no encoders left to start.

**Tests:** 82 passed, 2 failed, 1 skipped, from 73/11/1. Failure sets diffed,
not counted. Nine newly green: `T6_1`, `T6_2`, `T6_3`, and `G1`, `G2`, `G3`,
`G4`, `G7`, `G8` for E6. `G7b` skips — E6 declares no refractory. The two
remaining are `test_G3[E5]` (Q19) and `test_T5_3` (Q20). No regressions.
**Results written:** `results/e6_e_frac_span.json`, registered under id
`e6_e_frac_span`. The superseded `e6_rate_parameter_span` entry is left
untouched under its own id rather than marked superseded, because it measured a
different parameter rather than the same one differently.
**Blocked on:** Q19 and Q20 for E5's last two tests. Q07, Q17, Q18, Q21 open
and blocking nothing.
**Next:** the probe harness — weeks 1-2 of §9, the schedule critical path, and
now the only thing standing between the project and its first actual result.
Nothing in the encoder set remains. Second candidate is the survey report's
narrative, if it is wanted before Oliver sees it again.

## 2026-09-07 | session: implementation
**Did:** Built the probe harness — weeks 1-2 of §9, the schedule critical path,
untouched until today. Corpus interface, synthetic stand-in corpus,
speaker-disjoint splits, T1 frame labelling, the linear probe of §6.2, budget
calibration, and the Layer 2 controls. **The first end-to-end result the
project has produced**: E1 on T1 across six budget points, recorded under
provenance. Accuracy rises monotonically with budget, 0.4837 at Λ=160 to
0.8316 at Λ=15343, against a majority floor of 0.2079 and chance of 0.125.

**The point of a corpus with a known answer.** TIMIT is still blocked on O2 —
now twenty days — so the harness is written against an interface and the
stand-in is synthesised: a source-filter corpus with per-speaker vocal tract
scaling and f0, phone labels, boundaries and an exact f0 contour. That is not
a placeholder. On a real corpus every accuracy is plausible, so nothing
distinguishes "the encoder lost the information" from "the harness mislabelled
every frame"; on this one the ground truth is generated, so it does. When TIMIT
arrives, only the loader changes.

**Two findings, and neither was what I set out to look for.**

**E1 emits nothing on audio at the SPEC defaults.** Equation (10)'s logarithmic
branch gives `log(e + eps)`, negative wherever the envelope is below 1.0, which
through a gammatone bank is everywhere: the drive spans [-13.62, -0.96] and
100 per cent of samples are negative. E1 thresholds the membrane against an
absolute zero, so `theta >= 0` gives zero events and `theta < 0` gives 419616 —
every channel at every sample, Λ pinned at the 512000 ceiling. There is no
usable range between the two regimes. E4 thresholds the same way; E6 squares
the drive, so its gate selects the *quietest* frames, and the correlation
between its own per-frame energy and true audio RMS runs +0.394 under power
compression and **-0.280** under log. The encoder inverts. E2 and E3 are immune,
because both differentiate the drive and an additive offset cancels exactly.
Nothing here is a defect in an encoder — every known-answer test still passes,
because `test_G3` runs on `conftest`'s drive, which is positive. It is that
§5.0 and §6.6 declare compression a swept axis and half the encoder set cannot
traverse it. Q23.

**C5 found a real misalignment rather than confirming there was none.** The
control says to offset labels by ±1 frame and confirm accuracy drops. Minus one
does not drop; it gains, at **every one of the six budget points**, by 4.5 to
6.8 points. Two independent lags, separated by measurement rather than argued:
turning on `compensate_group_delay` moves the optimum from -1 to 0 at
τ_φ = 5 ms, which identifies the first as the gammatone bank and confirms D24's
machinery removes it; the second is the causal kernel of equation (32) and
moves with τ_φ, one further frame between 5 ms and 20 ms. The consequence is
larger than the control: τ_φ is a *shared swept axis* under §6.1 with each
encoder reported at its own best value, so fixing alignment at zero imposes a
penalty that grows with τ_φ — 18.5 points at 20 ms compensated — and then
selects the τ_φ that suffers least from it. That falls hardest on encoders with
a long natural timescale, which is the confound §6.1's own τ_φ caveat exists to
avoid. Q24, and the most consequential of the three raised today.

**The probe is written out rather than imported, and that was forced.** CI
installs `.[dev]` — numpy, scipy, pytest — and runs every file in `tests/`, and
the workflow is a design-session file I may not edit. A probe needing
scikit-learn would make its own tests unrunnable in the one environment that
checks them independently. So it is ~60 lines of multinomial logistic
regression on scipy's L-BFGS-B, checked against scikit-learn *out of tree* at
`C = 1/(n*alpha)`: coefficients agree to 8.2e-06 and 1.1e-06 max absolute
difference on two shapes, predictions agree exactly. D49.

**Sweeps are specified in event rate, not in parameter values.** Forced by the
same finding as Q23: a rate parameter's usable range depends on the drive
scale, so a config naming `theta` values would not be portable across the row
of encoders it has to be run over. `calibrate_rate_param` bisects, oriented by
the declared `RATE_DIRECTION`, and the six targets span two decades of Λ as
§6.4 requires. D50.

**Margins rather than passes.** C3 shuffled-label accuracy 0.1038 to 0.1409
against chance 0.1250 and a floor of 0.2079 — the split does not leak. C6
agrees at every point. Calibration lands within 5 per cent of target in 8 to 9
bisections. Bits per event falls 0.607 to 0.014 as Λ rises over two decades,
which is §6.3's caveat about that quantity appearing in the data unprompted.
The bandwidth refactor is bit-identical: 4162.701235807103 recomputes exactly.

**What is deliberately absent, and said in the module docstring rather than
left to be noticed.** The nonlinear probe, and therefore the accessibility gap
of equation (33) — it needs a tensor library this box does not have, on 8 CPU
cores with no GPU, and I would not commit to an architecture without first
measuring what a GRU costs here. T2 and T3, both of which need decisions not
taken. **C1**, the upper-bound anchor, which is a statement about TIMIT and
cannot be evaluated against a stand-in — the result file carries that as a
`caveat` field, because a number from this harness says the pipeline is
self-consistent, not that it is calibrated. C7 and the strong form of C6, both
statements about a release event format that cannot be written before Q07
settles whether ON and OFF are channels or a polarity bit.

**Schedule.** Day 19, week 3. Weeks 1-2 now have their spine, though not their
deliverable, which names TIMIT. Weeks 5-7 remain complete. P1, the count-only
baseline, is now reachable: it is this harness with the featurisation replaced
by per-channel counts, and equation (40) needs the R2 ceiling, which does not
exist yet.

**Tests:** 107 passed, 2 failed, 1 skipped, from 82/2/1. Failure sets diffed,
not counted. The 25 new ones are `tests/test_harness.py` — mine, not Layer 1;
the harness has no SPEC contract, since SPEC §8 declares the pipeline
deliberately unspecified, so what is testable is that the machinery does what
it claims and that the controls *bite*. C3, C4 and C5 are each tested twice:
once that they pass on a correct pipeline, once that they fail on one broken in
the way that control exists to catch. 39 s, numpy and scipy only. The two
remaining failures are `test_G3[E5]` (Q19) and `test_T5_3` (Q20), unchanged.
**Results written:** `results/probe_e1_t1_synthetic.json`, registered under id
`probe_e1_t1_synthetic`, config `configs/probe_e1_t1_synthetic.json`.
**Blocked on:** Q19 and Q20 for E5's last two tests. Q07 blocks the release
format and so C6/C7. Q17, Q18, Q21, Q22, Q23, Q24 open. Q23 blocks the
compression axis; Q24 blocks nothing but affects every T1 number produced.
**Next:** P1, the count-only baseline of §7.1, is the cheapest real
experiment now reachable and is week 3 work. Alternatively R2, the non-spiking
mel-filterbank bound, which P1's equation (40) needs as its ceiling and which
nothing blocks. The survey report's narrative is now stale in seven passages
rather than six — it describes no harness — and remains Simon's call, not a
mechanical rebuild.

**Addendum, same session, after the push.** CI went red on `fc24cd0` and I
checked rather than assuming it was the known pair. It is: `test_G3[E5]` and
`test_T5_3`, the same two, failing identically to the box — 2 failed, 82
passed, 1 skipped in the known-answers job. No regression from today's work.
But the run showed something I had not looked for: the workflow's second step,
"Everything else", is **skipped**, because the Layer 1 step above it exits 1
and Actions does not run what follows a failed step. So `tests/test_harness.py`
has never run in CI and will not until Q19 and Q20 clear. The independent check
CLAUDE.md justifies CI by is unavailable to precisely the newest code. I built
a clean 3.12 venv with `-e ".[dev]"` and nothing else — numpy 2.5.3 against
this box's 2.5.2 — and ran the skipped command: 25 passed in 40 s. That rules
out a dependence on local state today; it is not the standing check, and it is
me checking my own work. Q25.

## 2026-09-07 | session: implementation (second block)
**Did:** Built R2, the non-spiking upper bound of §5.9 — 40 mel bands, 25 ms
windows, 10 ms hop — and recorded it on the same corpus, splits and probe as
this morning's E1 sweep. This is the control §5.9 calls essential: "without it,
a phone accuracy figure means nothing."

**One decoder, not two that are meant to match.** `score_t1` is factored out of
`run_t1` so R2 and every spiking condition run the same split, probe and
controls, differing only in what produced the features. C4 asks for identical
decoding; two implementations could drift while each still looked right alone.
That is D30's argument for E2 and E3 sharing one lattice rule, applied a level
up. D51. The refactor is bit-identical on the spiking path — all three seeds of
the recorded sweep's first point reproduce exactly, confusion matrices
included.

**The window phase was a decision and §5.9 does not make it.** It fixes band
count, window and hop, and says nothing about where the window sits relative to
`t = k*hop`. Given what Q24 measured this morning, that is not a detail: a
centred 25 ms window sees 12.5 ms of audio the strictly causal kernel of
equation (32) cannot, so R2 would beat every spiking condition partly by seeing
the future. Causal is the default, centred is available, the choice is recorded
with the result. D52.

**The result, and the thing in it that matters.**

| condition | offset 0 | best offset | best |
|---|---|---|---|
| R2 causal | 0.8247 | -1 | **0.9133** |
| R2 centred | **0.9307** | 0 | 0.9307 |
| E1 at Λ=15343 | 0.8316 | -1 | 0.8996 |

**At offset zero the upper bound is below the encoder** — E1 0.8316 against R2
0.8247. Reported as it stands, a spiking encoder has beaten a mel filterbank,
which is the sort of result that gets a paper rejected by someone who spots the
alignment and the sort that gets it accepted by someone who does not. At each
condition's own best offset the ordering is restored and the gap is 1.4 points.
Nothing about the encoding differs between those readings; only which frame the
labels were paired with. Q24 already carried the alignment question; it now
also carries the fact that the answer decides whether the study's central
control is above or below what it controls for.

**The two R2 rows cross-check the diagnosis rather than restating it.** A
centred window is displaced ~12.5 ms, or 1.25 frames, from a causal one. Its
optimum duly sits at offset 0 where the causal window's sits at -1, and the two
best values agree to within 1.7 points. The lag is a property of where the
analysis window sits, and R2 has it as much as the spiking path does — which
rules out the reading that this is something the encoders are doing.

**The gap to the bound, which is what §5.9 exists to produce.** At each
condition's best offset, against R2 causal at 0.9133:

| Λ | E1 best | gap | % of R2 | event bandwidth |
|---|---|---|---|---|
| 160 | 0.5903 | 0.3230 | 64.6 % | 4 163 bps |
| 397 | 0.7052 | 0.2081 | 77.2 % | 10 313 bps |
| 997 | 0.7564 | 0.1569 | 82.8 % | 25 915 bps |
| 2447 | 0.7791 | 0.1342 | 85.3 % | 63 623 bps |
| 6036 | 0.8414 | 0.0719 | 92.1 % | 156 948 bps |
| 15343 | 0.8996 | 0.0137 | 98.5 % | 398 929 bps |

**And a finding that runs against the case for events, which is why it is worth
stating plainly.** R2's dense features cost **128 000 bits per second** — 40
values × 32 bits × 100 frames/s. E1 only reaches 98.5 per cent of R2's accuracy
at Λ = 15343, where its event stream costs **398 929 bps**, three times more
than the dense representation it is approximating. The two bandwidths cross at
about Λ = 4900, where E1 sits near 92 per cent of the bound. On this corpus,
at these declared widths, the event representation is *not* cheaper than mel
features in the regime where it is competitive on accuracy.

Both widths are declared parameters and the conclusion moves with them: 20 bits
of timestamp is generous, and so is 32 bits per mel coefficient. The crossover
is a statement about `b_t = 20`, `b_p = 1` and `32`, not about events in
general, and §6.3 already insists the encoder's own cost be charged rather than
hidden. But it is the first quantitative version of the study's central
engineering question this project has produced, and it does not currently
favour the answer the field assumes. Flagged rather than smoothed, per the
working practice. It is a synthetic 8-class corpus and nothing here transfers
to TIMIT; the number to watch is the shape, not the value.

**Tests:** 122 passed, 2 failed, 1 skipped, from 107/2/1. Failure sets diffed.
The 15 new ones are `tests/test_reference.py`. The one worth having asserts
that R2's probe settings, split and frame counts are identical to a spiking
condition's — true by construction under D51, and the test is there to notice
if that stops. The causal window is asserted to contain no sample later than
`t = k*hop`, which is the property that keeps the gap attributable to the
encoding. Two remaining failures unchanged: `test_G3[E5]` (Q19), `test_T5_3`
(Q20).
**Results written:** `results/reference_r2_t1_synthetic.json`, id
`reference_r2_t1_synthetic`, config `configs/reference_r2_t1_synthetic.json`.
**Blocked on:** unchanged. Q24 is now the question with the most riding on it.
**Next:** P1, the count-only baseline of §7.1, is now computable — equation
(40)'s ceiling is R2 and it exists. After that T3 and T2, which the week 4 P2
gate needs.

## 2026-09-07 | session: implementation (third block)
**Did:** Built and ran P1, the count-only baseline of §7.1, at segment level on
E1 across the same six budget points as the morning's sweep. The machinery
works and is tested. **Its answer on the stand-in corpus does not mean
anything, and the more useful output of the day is why.**

**Segment level, because §7.1's notation settles it.** `n_c` is indexed by
channel and by nothing else, so the count representation has no time axis at
all — which cannot be done on a frame grid, since the grid is itself timing.
§4.1 already offers segment-level T1 as a first-class form of the task. The
temporal and ceiling conditions produce a segment verdict by majority vote over
the *unchanged* frame probe's predictions, because §7.1 says to run the same
probes and inventing a segment-level pooling of equation (32) would put a free
choice inside equation (40)'s numerator. D53.

**The finding that matters: the index changes sign depending on a parameter
§7.1 never mentions.** My first run fixed τ_φ = 5 ms. §6.1 requires τ_φ to be
swept over {2, 5, 20} ms with each condition reported at its best, so I reran
it. Three of six points flipped sign:

| Λ | TII, τ_φ fixed at 5 ms | TII, τ_φ swept |
|---|---|---|
| 160 | −0.200 | **+0.200** |
| 397 | −0.211 | **+0.158** |
| 997 | −1.333 | −0.111 |
| 15343 | +0.200 | +0.800 |

The cause is structural. The count condition integrates a whole 60–140 ms
segment; a 5 ms exponential kernel does not. So equation (40) was reading a
mismatch of *integration windows* as an absence of temporal information. The
swept run picks τ_φ = 20 ms — the longest value offered — at the two lowest
budgets on every seed, which is exactly what that reading predicts. Q27, and I
think the honest version of P1 equalises the windows rather than merely
sweeping τ_φ, which needs Q22 settled first.

**The second finding: this corpus cannot answer P1, and P1 correctly says so.**

| Λ | count | temporal | ceiling | denominator | TII |
|---|---|---|---|---|---|
| 160 | 0.7870 | 0.8241 | 0.9722 | 0.1852 | +0.200 |
| 397 | 0.8843 | 0.8981 | 0.9722 | 0.0880 | +0.158 |
| 997 | 0.9306 | 0.9259 | 0.9722 | 0.0417 | −0.111 |
| 2447 | 0.9583 | 0.9306 | 0.9722 | 0.0139 | undefined |
| 6037 | 0.9583 | 0.9583 | 0.9722 | 0.0139 | undefined |
| 15343 | 0.9491 | 0.9676 | 0.9722 | 0.0231 | +0.800 |

At four of six budgets the denominator is under 0.042, which on 72 test
segments is three segments. The index is undefined twice and swings from −0.111
to +0.800 between adjacent points. It is noise, and I am not reporting it as
anything else.

The cause is in my synthesiser: each phone is a *stationary* resonance, so a
segment's per-channel count vector is nearly a complete description of it, and
counts reach 0.9583 where the mel ceiling reaches 0.9722. Real phones have
formant transitions, and transitions are what a count discards. §7.1 calls this
condition "a spectral profile task wearing a spiking costume" — which the
stand-in is, by construction, and the diagnostic detected it. **The instrument
works; what it is diagnosing is the corpus.** Q28 asks whether the stand-in
should gain formant transitions or whether P1 waits for TIMIT. I lean to
waiting, and I have deliberately not added transitions, because making the
corpus more speech-like in order to obtain a more interesting index is close to
the line CLAUDE.md draws around the battery being the design session's remit.

**P-06 is neither confirmed nor contradicted.** It predicts a moderate index
for T1. What was measured is +0.16 to +0.20 at the two lowest budgets and noise
above them, on a corpus whose denominator collapses. That is not evidence
either way and I am not recording it as a test of the prediction. §7 of the
validation protocol wants a written investigation for a *contradicted*
prediction; this is an uninformative one, which is a different thing and worth
distinguishing.

**Margins rather than passes.** C3 on the count condition: shuffled-label
accuracy 0.056 to 0.125 against chance 0.125 and a floor of 0.194 — the segment
split does not leak either, which is worth checking separately since it is a
different partition from the frame split. C5's segment analogue, sliding the
counting window 20 ms off the segment, costs 2.3 to 9.7 points at every budget,
so the count features do depend on where their window sits. Counts against
duration-normalised rates differ by at most 0.023, or 1.7 segments (Q26) —
expected here, since the stand-in draws durations independently of phone, and
therefore silent about TIMIT. The `ceiling_accuracies` hoist out of the
per-point loop is bit-identical to the inline computation, and the cached path
identical to the uncached one.

**One seed saturates.** Split seed 1 gives a ceiling of 1.0000 at every offset —
that speaker partition is trivially separable at 72 test segments. It is left in
rather than dropped, and it is part of why the denominator is thin.

**Two of my own tests failed when first written and both were the test's
fault.** The second is worth recording: it asserted equation (40)'s guard
rejects a denominator of `0.52 - 0.5`, which in floating point is
0.020000000000000018 and clears a `<= 0.02` threshold. Checking that knife edge
showed the guard is a floor and not a sufficiency test — just above it the
index still exceeds 10 — so the denominator is now reported beside every index.

**Tests:** 137 passed, 2 failed, 1 skipped, from 122/2/1. The 15 new ones are
`tests/test_segments.py`. The one that earns its place asserts that
`shift_labels` and `frame_segment_index` agree about what an offset means:
`run_p1` shifts the probe's labels by `o` and separately attributes each vote to
a segment using `o`, and if those drifted apart the result would be a plausible
number produced by scoring against the wrong segment. Two remaining failures
unchanged: `test_G3[E5]` (Q19), `test_T5_3` (Q20).
**Results written:** `results/p1_count_only_e1_synthetic.json`, id
`p1_count_only_e1_synthetic`. The τ_φ-fixed first run is superseded rather than
deleted, so the sign change in Q27 stays visible in the manifest.
**Blocked on:** unchanged for implementation. Q24 remains the question with most
riding on it; Q27 and Q28 now decide whether P1 and the week 4 P2 gate can be
run on the stand-in at all.
**Next:** T3 and T2 adapters, which P2 needs. But Q28 says plainly that a P2 run
on this corpus could not settle the gate it exists for, so the honest ordering
may be to build both and hold the gate for TIMIT.

## 2026-09-07 | session: implementation (fourth block)
**Did:** Built T3, boundary detection (§4.3) — peak picking, one-to-one
matching, precision/recall/F, the R-value, and frame AUC — and ran it on E1
across three budgets and three context widths with R2 alongside. **T2 is not
built.** I said at the start of this block that both in one session would be an
unreviewable drop; it would have been, and T3 alone produced three questions.

**The R-value was looked up, not recalled.** Räsänen, Laine and Altosaar,
Interspeech 2009. `R = 1 − (|r₁| + |r₂|)/2`, `r₁ = √((1−HR)² + OS²)`,
`r₂ = (−OS + HR − 1)/√2`, `OS = N_detected/N_ref − 1`. The proposal names the
metric and gives neither formula nor citation, and writing one from memory is
the thing the working practice forbids. Checked against the two points the
definition pins: perfect segmentation gives exactly 1, and buying recall by
doubling detections keeps F above 0.6 while dropping R by more than 0.3, which
is the behaviour §4.3 wants it for.

**A correction to my own reading, made in the same session that produced it.**
A 12-utterance smoke test gave frame AUC 0.444 at context 0 — below chance —
and I read that as the per-frame probe being *structurally incapable* of
boundary detection. On the full 30-utterance corpus the same condition gives
0.644, 0.521 and 0.684 at the three budgets, against shuffled controls at 0.50
to 0.54. **The probe does learn at context zero.** The below-chance figure was a
small-sample artefact of a 12-utterance corpus with 32 test segments, and the
strong version of the claim was wrong. What survives is weaker and still
matters, and it is what Q30 says.

**What actually holds.** At context 0 no E1 condition beats evenly spaced
boundaries at the reference rate:

| condition | context | Λ | F | R-value | frame AUC | shuffled AUC |
|---|---|---|---|---|---|---|
| E1 | 0 | 397 | 0.4554 | +0.393 | 0.6438 | 0.5411 |
| E1 | 0 | 2447 | 0.4468 | −0.476 | 0.5212 | 0.5181 |
| E1 | 0 | 15343 | 0.4355 | +0.286 | 0.6843 | 0.5037 |
| E1 | 2 | 15343 | 0.7448 | +0.776 | 0.8212 | 0.4705 |
| E1 | 5 | 15343 | **0.7576** | +0.718 | **0.8581** | 0.4728 |
| R2 | 0 | — | 0.6852 | +0.667 | 0.6888 | 0.5522 |
| uniform baseline | — | — | 0.5873 | — | — | — |

Context is what makes T3 viable: two frames of it take the same encoder at the
same budget from 0.436 to 0.745. Q30.

**E1 beats R2 on T3.** 0.7576 against 0.6852 on F, 0.8581 against 0.6888 on
AUC, each at its own best context. §5.9 calls R2 "the non-spiking upper bound"
and it does not bound this task. I believe the mechanism rather than a defect —
25 ms windows hopped by 10 ms smear a transition that an event stream resolves
at event precision, and §4.3 names transient timing as exactly what T3 rewards
— but the honest position is that I do not know whether E1 beats R2 or beats
*this* R2, whose window length was chosen for phone classification. Q31, and it
should be settled before any T3 figure is quoted.

**Why frame AUC is now reported beside every F-score.** They disagree. R2 at
context 0 has AUC 0.6888 and F 0.6852; E1 at context 0, Λ=2447 has AUC 0.5212
and F 0.4468 — but with an R-value of −0.476, meaning it reached that F by
over-segmenting. F-score is the product of probe, threshold, peak picker and
the corpus's boundary statistics; AUC is the probe alone. Without both, a
detector firing at roughly the right rate is indistinguishable from one that
works, which is the failure the R-value was invented for and which the first
smoke test walked straight into. D56.

**Margins rather than passes.** C3 shuffled-label controls sit at AUC 0.47 to
0.55 across all twelve conditions — chance — so the split does not leak on T3
either. The uniform baseline is a real floor and not a formality: it scores
0.5873, above eight of the twelve learned conditions. `frame_auc` returns
exactly 0.5 on a constant posterior via the tie correction, checked, because
without it a probe that learned nothing would score by luck of tie ordering.

**Tests:** 157 passed, 2 failed, 1 skipped, from 137/2/1. The 20 new ones are
`tests/test_boundaries.py`. Two remaining failures unchanged: `test_G3[E5]`
(Q19), `test_T5_3` (Q20).
**Results written:** `results/t3_boundary_e1_synthetic.json`, id
`t3_boundary_e1_synthetic`.
**Blocked on:** unchanged for implementation. Q28's caveat applies to every
number above — quasi-regular phone durations make the uniform baseline far
stronger here than on real speech.
**Next:** T2. It needs a decision this session did not reach: §4.2 wants the
reference contour from a standard pitch tracker with a second tracker run
against it to quantify disagreement, and neither exists on this box. On the
stand-in the commanded f0 is exact, so T2 can be built and validated without a
tracker — but the tracker question has to be answered before T2 runs on TIMIT,
and it is worth raising before the code is written rather than after.

## 2026-09-08 | session: implementation (fifth block)
**Did:** Built T2, the f0 contour task (§4.2) — ridge probe in semitone space,
a separate voicing probe, both correlations — and ran it on E1 across four
budgets and two context widths with R2 alongside. **The probe battery now has
all three tasks.** Simon settled the two open choices before I wrote code:
per-utterance correlation as the headline, semitone target space. D57.

**The headline result.**

| condition | ctx | Λ | r/utt | pooled | RMSE (st) | floor | voicing |
|---|---|---|---|---|---|---|---|
| E1 | 5 | 15343 | **0.5755** | 0.9142 | **1.430** | 4.415 | 0.9921 |
| R2 | 5 | — | 0.4991 | 0.8738 | 1.676 | 4.413 | 0.9939 |
| E1 | 0 | 15343 | 0.3264 | 0.7145 | 3.039 | 4.427 | 0.9787 |
| R2 | 0 | — | 0.3353 | 0.5524 | 3.161 | 4.427 | 0.9488 |

Shuffled-label controls run −0.13 to +0.05 — chance — at every condition, and
voicing accuracy 0.94 to 0.99 against a 0.50 floor.

**The pooled/per-utterance gap is large and consistent: 0.09 to 0.39.** At the
best conditions, roughly a third of the pooled figure is voice height rather
than contour. `tests/test_f0.py` asserts the mechanism directly — a predictor
emitting one constant per utterance, with no contour information whatever,
scores pooled r > 0.99 and cannot be scored per utterance at all. Q32. Worth
noting the gap is itself a cheap measure of how much speaker identity an
encoding retains, which §4.5 wants known before release and has no instrument
for.

**R2 fails to bound T2 as well as T3.** E1 at five frames of context reaches
0.5755 against R2's 0.4991. Q31 now covers two of the three tasks; only T1 is
bounded (0.9133 against 0.8996). Whatever replaces "upper bound" has to be
per-task.

**A prediction of mine that was wrong, and a diagnosis that was wrong.** The
first T2 run recorded **RMSE 5617 semitones** — 468 octaves — against a floor
of 4.4. I diagnosed it as the zero-variance columns: `featurise` leaves the OFF
half at zero for a unipolar encoder, so 32 of E1's 64 features are constant and
`cond(X'X)` is infinite at *every* operating point. That was real and is fixed
(D58). It was not the cause. Ridge is exactly invariant to all-zero columns —
they take `w = 0` either way — and the re-run reproduced 5617 byte for byte.

The cause was the informative columns: at Λ=160 their standard deviations span
37×, standardisation turns rare events into spikes of ±39, the context-stacked
copies are near-collinear, and a penalty of 1.0 against a Gram diagonal of order
n is no regularisation at all. **The correlation survived it at an
ordinary-looking 0.179, because correlation is scale-free.** Only the RMSE
showed it. That is the argument for reporting both, and it is the same shape as
the T3 lesson that an F-score without an AUC cannot be interpreted.

Fixed by sweeping the penalty and selecting it on speakers held out inside the
training split — never on test, the same rule as T3's threshold. D59. **And the
first grid was truncated**: the failing condition picked the maximum 1e5 on all
three seeds while validation RMSE was still falling steeply, 346 at 1e4 and 68
at 1e5. Extending to 1e9 brought it to 4.433 against a floor of 4.434. Nine of
ten conditions now sit clearly below their floor and that one sits exactly at
it, which is the honest outcome for the sparsest condition. Q34.

**I also predicted the zero-column fix would be bit-identical for
classification, and it was not.** Five of six budget points in the recorded T1
sweep reproduce exactly; Λ=160 moves by 0.0005 — a fifth of one test frame out
of 339, against a seed spread of 0.0167 at that point. L-BFGS builds its Hessian
approximation from the full parameter vector, so removing coordinates whose
gradient is identically zero still changes the trajectory and the
finite-tolerance stopping point. Measured rather than assumed, which is the only
reason I know it.

**Consequence, and it is a loose end.** `probe_e1_t1_synthetic`,
`reference_r2_t1_synthetic`, `p1_count_only_e1_synthetic` and
`t3_boundary_e1_synthetic` were all produced before D58. They are correct
records of the code at the commits they name, and they differ from what the
current tree produces by at most 0.0005 at one budget point of one of them. But
D35's point is that a commit hash records provenance only if the tree that
produced the number is the tree the hash names, so they should be re-run and
superseded. That is four mechanical config-driven runs, about 75 minutes, and I
have not done it — it is the first thing to do next session, before anything is
built on top of them.

**Tests:** 173 passed, 2 failed, 1 skipped, from 157/2/1. The 16 new ones are
`tests/test_f0.py`. Also fixed: `RidgeProbe` standardised before checking for an
empty fit, so the guard raised the right error having already emitted five
RuntimeWarnings; verified under `-W error::RuntimeWarning`. Two remaining
failures unchanged: `test_G3[E5]` (Q19), `test_T5_3` (Q20).
**Results written:** `results/t2_f0_contour_e1_synthetic.json`, superseding two
earlier entries of the same id — the 5617 one and the truncated-grid one, both
left visible in the manifest.
**Blocked on:** unchanged. Q28's caveat applies: the stand-in's contour is a
linear declination moving one to three semitones, where real speech carries
accents and question intonation and moves far more, so the within-utterance
correlation here is measured against a contour with little to track.
**Next:** re-run the four pre-D58 results and supersede them. Then P2 — the week
4 gate — for which all three tasks and the four corruption operators of
`corrupt.py` now exist, though Q28 says plainly that a P2 run on this corpus
cannot settle the gate it exists for.

## 2026-09-08 | session: implementation (sixth block)
**Did:** Re-ran the four results that predated D58 and superseded them, closing
the provenance gap flagged at the end of the previous block. Mechanical:
committed configs, no code changed, run in dependency order because P1 and T3
take their rate-parameter values from the T1 sweep's recorded result.

**Nothing moved that changes anything.** Diffed field by field against the
superseded entries rather than eyeballed:

| result | change |
|---|---|
| `probe_e1_t1_synthetic` | Λ=160 accuracy 0.4837 → 0.4841. Five of six points bit-identical. **Rate parameters bit-identical at all six**, so P1's and T3's comparability against this sweep is preserved. |
| `reference_r2_t1_synthetic` | bit-identical. R2's mel features have no zero-variance columns, so D58 drops nothing. |
| `p1_count_only_e1_synthetic` | bit-identical, every count accuracy and every TII. |
| `t3_boundary_e1_synthetic` | no F-score or R-value changed anywhere. Three conditions moved in the fourth decimal of frame AUC, and one *shuffled control* moved 0.4122 → 0.4088. |

The largest movement in any headline figure across all four results is 0.0005,
at one budget point of one of them, against a seed spread of 0.0169 there. No
conclusion in any earlier entry is affected, and the manifest now carries nine
superseded entries with the old values still visible.

**Worth noting for its own sake:** the T1 sweep's calibrated `theta` values came
back bit-identical, which they had to — `calibrate_rate_param` touches encoders
and the front end and never a probe — but it is the property that makes P1 and
T3 comparable against the sweep at all, and checking it cost one assertion.

**Tests:** 173 passed, 2 failed, 1 skipped. Unchanged; no code touched this
block.
**Results written:** four ids re-recorded under supersede —
`probe_e1_t1_synthetic`, `reference_r2_t1_synthetic`,
`p1_count_only_e1_synthetic`, `t3_boundary_e1_synthetic`.
**Blocked on:** the design-session round trip Simon is now taking. The
priority order given to him: the free-parameter principle (Q22, Q24, Q27, Q30,
Q34, and half of Q31 — six questions that are one question, since §6.1 already
states the rule for τ_φ and the question is whether it generalises); then Q23
(compression, blocks a declared sweep axis before the week-8 screen); then Q28
(whether the stand-in gains formant transitions or P1/P2 wait for TIMIT); then
Q31 (R2 bounds T1 but not T2 or T3); then Q19+Q20, which are cheap and are why
CI is red, and Q25 shows that means none of the 173 tests has ever run in the
clean environment CI exists to provide.
**Next:** P2 as an explicit rehearsal — all three tasks exist and `corrupt.py`
has the four operators §7.2 needs — held as a rehearsal and not the week-4 gate,
per Q28. Nothing else should be built on the current answers until the
free-parameter question comes back, since it could change the shape of every run.

## 2026-09-08 | session: implementation (seventh block)
**Did:** Built and ran P2, corruption and dissociation (§7.2), on E1 at
Λ = 15343, sixteen conditions × three seeds across all three tasks. **Recorded
as a rehearsal, not the week 4 gate** — D60, and said so in the script, the
config and the result caveat, because Q28's argument applies here as much as to
P1.

**The finding that does not depend on the corpus.** Before running anything I
found that §7.2 and SPEC §7 define the fourth operator differently: the
proposal randomises times *within each segment*, SPEC over `[0, duration]`. I
ran both. They are not variants of one operator:

| operator | T1 | T2 | T3 |
|---|---|---|---|
| `randomise_times` (SPEC) | **0.1533** (lost 1.08) | 0.1806 (0.69) | 0.3881 (2.85) |
| within each segment (§7.2) | **0.7656** (lost 0.10) | 0.4067 (0.30) | 0.4008 (2.73) |
| clean | 0.8316 | 0.5835 | 0.6951 |

Under SPEC's version T1 falls **below its own majority floor of 0.2020** — the
task is annihilated. Under the proposal's it loses a tenth of its headroom. The
mechanism is exactly what §7.2's own phrase says: randomising across the whole
utterance moves events between segments, so the per-segment rate profile goes
with the fine timing, and "leaving rate intact" is false of it. **Unlike every
other number here, this transfers to TIMIT unchanged** — it is a statement about
what the operator does, not about what the stand-in contains. Q35, and it is
blocking for P2's interpretation because the two operators support opposite
conclusions about how much of T1 is timing.

`corrupt.randomise_times` is untouched — SPEC-defined, known-answer covered, not
mine. The proposal's operator sits beside it (D61).

**`channel_shift` is not a translation.** Downward shifts cost T2 up to 0.48 of
its headroom and T3 up to 1.67; upward shifts cost nothing at all (−0.04 to
+0.00). A translation should not be that asymmetric. SPEC §7 drops events
falling outside the bank rather than wrapping, so shifting down by four discards
the lowest four of thirty-two ERB channels — where F₀ and its low harmonics
live, which is what T2 estimates. The measured T2 collapse is a band-removal
experiment wearing a vocal-tract-length label, and the two are confounded in one
parameter. Q37.

That also explains the one cell where §7.2's predicted signature looks wrong.
It predicts T3 robust to channel shift "since a boundary is a boundary wherever
in the spectrum it appears". T3 *is* robust upward and not downward, which is
consistent with the prediction about translation and with losing the channels
carrying most of the energy — not with a failure of the spanning argument.

**The normalisation is doing real work and has a failure mode.** Degradation is
reported as fraction of each task's headroom above its own floor, because the
three tasks sit on different scales: T1 headroom 0.6297, T2 0.5835, T3 **0.1078**.
A raw drop of 0.10 costs T1 a sixth of its range and T3 almost all of it. But
T3's headroom is so thin here that its normalised column is a ratio of small
numbers — "+2.85" means it fell to 0.388 — and should not be read against T1's
and T2's at face value. Q36, and it is partly Q28 again.

**P-07 is untested, not supported.** The profiles do differ — T1 completely
robust to channel shift where T2 and T3 are not, T3 hypersensitive to jitter
(2.33) where T1 loses 0.40, T1 destroyed by whole-utterance randomisation and
not by per-segment. The direction is consistent with the prediction. It is not
evidence for it, because the corpus cannot carry the test, and I am not
recording it as a test of P-07, which stays open.

**A latent bug P2 found in code written earlier today.** `run_t2`, `run_t3` and
`run_p1` each reported an "at offset zero" figure by indexing `by_offset["0"]`
unconditionally. That holds for every sweep written so far and fails the moment
a caller fixes the alignment instead of scanning it — which is what P2 does
(D62: alignment held at each task's clean best, so a degradation measures
information destroyed rather than alignment moving). The first P2 run died on a
`KeyError`. Fixed in all three, with a regression test that fixes a single
non-zero offset on all three tasks.

**Margins rather than passes.** Jitter at 0.1 ms and 0.5 ms costs every task
nothing — negative losses, i.e. within seed noise — which is the sanity check
that the operator is not doing something gross at small σ. Alignment resolved to
T1 −1, T2 −2, T3 −1 on clean data and was held there throughout.

**Tests:** 184 passed, 2 failed, 1 skipped, from 173/2/1. The 11 new ones are
`tests/test_p2.py`, including the assertion that per-segment counts survive one
randomisation operator and not the other — which turns the Q35 discrepancy into
a measurement rather than a reading of two documents. Two remaining failures
unchanged: `test_G3[E5]` (Q19), `test_T5_3` (Q20).
**Results written:** `results/p2_corruption_e1_synthetic.json`.
**Blocked on:** the design-session round trip, which hit a token limit and
returns in about three hours. Q35 now joins the priority list and is arguably
above Q28 on it, being the one P2 finding that does not depend on the corpus.
**Next:** nothing further should be built until the free-parameter question and
Q35 come back. The remaining unblocked work is the survey report's narrative,
now stale in nine passages — it describes no harness, no R2, no P1, no T2, no
T3 and no P2 — and that is writing rather than regeneration, so it stays
Simon's call.

## 2026-09-08 | session: implementation (eighth block)
**Did:** Rebuilt the encoder survey report as **version 2**, at Simon's request,
for sending to Oliver before this afternoon's meeting. Version is now a constant
carried in the filename (`spikeEncode_encoder_survey_v2.docx`) and in the docx
properties; v1 is left in place as the record of what Oliver already has.

**Eleven passages were false, not the six I logged yesterday.** The two I had
not counted were E6's design-parameter table — still listing `e_min` as the
RATE_PARAM and `E_max` as "defined nowhere", both settled by D43 and D44 — and a
sentence in E7's section calling a controllable rate parameter "the property E5
and E6 are currently blocked on". Corrected in full: the status callout, three
summary-table rows, the table caption asserting both encoders raise
`NotImplementedError`, the paragraph counting "the four implemented encoders",
E5's and E6's status callouts, R2's section, the claim that "none of them is a
task result. No probe has been run", the known-answer block table, and the
questions section.

**E4 is 11/11, which I had not noticed.** The report said 10/11 with test_T4_3
failing on Q10. D39 replaced that test on 2026-09-06 and the block has been
complete since. Counted from the collected test ids rather than from memory,
which is how it surfaced — and a reminder that a status table is a claim like
any other.

**Two new sections.** §12 the probe harness: the corpus problem and why the
stand-in is a stand-in rather than a placeholder, the probes and why they are
written out rather than imported, and the Layer 2 controls as a table with three
of eight marked not evaluable and each one's blocker named. §13 first task
results: the T1 budget sweep with the bandwidth crossover, what C5 found
including R2 falling below E1 at offset zero, and T2, T3, P1 and P2 in one
table with the P1 and P2 caveats stated rather than footnoted.

**Two things I changed about how the report is built, both because of what went
stale.** The open-question count is now derived from `QUESTIONS.md` instead of
being a literal — it went from 9 to 20 in two days and is exactly the kind of
number nobody re-checks. The suite totals and per-encoder test counts are named
constants in one block at the top with a comment saying they must match the last
recorded run, rather than being scattered through the narrative; running the
suite inside the build would make the report slow and able to fail for reasons
unrelated to the report.

**Margins rather than passes.** The build is still byte-deterministic — two
consecutive runs give the same sha256. The rebuilt document was scanned
programmatically for eleven stale phrases and for every occurrence of "not
implemented", "does not exist", "not started", "not been run" and "blocked on";
the remaining matches are all legitimate (E7, R1, the nonlinear probe, the three
unevaluable controls). One claim I checked and *kept*: E4's adaptation-ratio
table still says "not yet registered in the manifest", and that is still true.

**Tests:** unchanged, 184 passed, 2 failed, 1 skipped. No source touched.
**Results written:** none. The report reads `results/` and the manifest; it adds
nothing.
**Blocked on:** the design-session round trip, expected in about two hours.
**Next:** nothing further should be built until the free-parameter cluster
(Q22, Q24, Q27, Q30, Q34 and half of Q31) comes back, since it could change the
shape of every run recorded so far. §15 of the report puts that cluster first
and says why, which is also the order Simon has for the round trip.

## 2026-09-08 | session: implementation (ninth block)
**Did:** Recorded three corrections owed to report v3, and stopped a rebuild
from silently replacing a version that has been sent.

**Simon found a genuine defect in v2 by reading the table.** The Drive column in
§2 carries two meanings. `DRIVE_KIND` is declared only as `"envelope"` or
`"subband"` (SPEC §4.1) and §1.2 says exactly that — "one of two things" — but
the table shows a third value, `"audio"`, on E7, R1 and R2. None of those three
is an `Encoder` subclass and none declares a `DRIVE_KIND` at all; for those rows
the column silently changes meaning to "bypasses the shared front end". A reader
who trusts §1.2 will read the third value as a typo.

The elaboration owed for v3 is the signal chain itself: audio → gammatone
filterbank → `x_c(t)` the subband waveform → envelope → `u_c(t)` the compressed
envelope. Measured on one utterance to make it concrete: subband channel 4
(centre 203 Hz) has 211 upward zero crossings per second and is negative half
the time; channel 24 (centre 3603 Hz) has 3606. **The crossing rate of a subband
is its centre frequency** — that is the carrier, and it is exactly what E5 exists
to encode and what the envelope discards. The envelope of the same channel has
zero crossings and never goes negative.

**A near-miss worth recording, because the mechanism was invisible.** v2 had
already gone to Oliver. Adding the pending list to the builder and running it
rewrote `reports/spikeEncode_encoder_survey_v2.docx` — same size, 79923 bytes,
but a different file, because **the front matter embeds the commit hash** and
the commit had moved. Nothing about the narrative changed. I caught it only
because `git status` listed the binary as modified, and had I not looked, the
committed v2 would no longer have been the v2 in Oliver's inbox. The sent file
is restored byte-for-byte from git.

Both builders now refuse to overwrite an existing output without `--force`, with
the reason in the error text. This is the same shape as every other mechanical
guard added this week — the drop protocol that appends rather than copies, the
controls that run unconditionally, the split that cannot be constructed leaking.
Relying on remembering not to rebuild a sent document is exactly the kind of
care that fails once and fails silently.

**`PENDING_NEXT_VERSION` is printed at the end of every build**, so the three
outstanding items are in front of whoever rebuilds at the moment they are
actionable, rather than sitting in a notebook entry nobody re-reads. The other
two: §13 needs re-running wholesale once the free-parameter cluster is answered,
and E4's adaptation-ratio table is still marked "not yet registered in the
manifest" and should be produced under a committed config like every other
reported number, or dropped.

**Tests:** unchanged, 184 passed, 2 failed, 1 skipped. No source under `src/`
touched.
**Results written:** none.
**Blocked on:** the design-session round trip.
**Next:** unchanged — nothing further built until the free-parameter cluster
comes back.

## 2026-09-08 | session: design
**Did:** Answered Q19, Q20, Q23, Q24 and Q34 (D67-D72). This is the first of
two patches; Q17, Q18, Q21, Q22, Q25-Q33 follow, and Q28 and Q31 wait on
Oliver.

**Q19 came back as a finding and D27 was not relaxed.** The APPLY sheet for the
Q09-Q16 patch said a span under 4x would be a finding rather than a threshold
to lower, and it was one. It is Q14's shape, not Q11's: the parameter is exactly
`survivors / k` above k = 8, and the sweep had been centred where refractory
still dominates. Two numbers were being asked of one — the encoder's natural
default and the gates' mid-range point — and separating them resolved Q20 as
well, without touching a test. The default of 4 had been chosen so that
`test_G3`'s grid landed on integers, which is a default picked for the
convenience of a generic gate and which then broke the encoder's defining
measurement. Worth remembering as a shape: a value chosen to satisfy machinery
rather than to describe the thing.

**Q23 is the most serious specification error found so far and no test could
have caught it.** `log(e + eps)` is negative everywhere on real audio, so E1
and E4 have no operating range and E6 gates in the quietest frames while
reporting them as the loudest — a sign flip, not a degradation. Every generic
gate passed throughout, because `conftest`'s drive is positive and nothing in
the suite exercises the compression axis. That is a coverage gap of the same
shape as the error itself and it goes in the second patch: the gates need at
least one drive that has been through the real front end under each compression
method.

**Q24 changes how existing results are read.** Every T1 number in `results/`
is at offset zero and is a lower bound by 4.5 to 6.8 points. They are not wrong
— the offset was not a declared axis when they were taken — so D72 records the
interpretation rather than regenerating them. The R2 causal-versus-centred rows
are what made the diagnosis convincing rather than merely plausible: an
independent prediction, checked, and it landed.

**The condition I attached to Q24 is the one to watch in review.** Reporting
each condition at its best offset makes the offset a free parameter selected
against the reported number, and it must therefore be chosen on held-out
training data like the ridge penalty and the detection threshold. This is easy
to get wrong by accident precisely because a sweep over offsets looks like the
tau_phi sweep, which is selected the same way — so the resemblance that makes
option 2 defensible is also what makes the error invisible.

**Four instances of one principle were being decided separately.** D56, D59,
D69 and proposal 6.1 all reached "select per condition on held-out training
data, record the grid, never touch test" independently. That is now section 9
of the validation protocol rather than a fifth question waiting to be asked.
Noting the general lesson: when the same answer arrives three times from
different directions, the thing to write down is the rule, not the third
answer.

**This drop applies by script rather than by shipping whole files.** Q18 is not
answered yet but its point is acted on here: `apply_patch.py` edits by targeted
string replacement and appends fragments to NOTEBOOK.md and DECISIONS.md, so
anything written between the drop being built and applied survives. Each
replacement asserts a single match and exits without writing if it fails.

**Tests:** none run — no environment here. Expected: `test_T5_3` passes at the
new default without modification, and `test_G3[E5]` reaches 10.5x at the new
registry point, which is your measurement rather than my prediction this time.
**Results written:** none.
**Blocked on:** nothing in this patch. Q28 and Q31 need Oliver; Simon is
raising the TIMIT dependency for the week 4 gate with him.
**Next (design session):** the second patch — Q17, Q18, Q21, Q22, Q25, Q26,
Q27, Q29, Q30, and the compression-axis coverage gap Q23 exposed.

## 2026-09-08 | session: implementation (tenth block)
**Did:** Applied the design session's Q19/Q20/Q23/Q24/Q34 drop. **The suite is
fully green for the first time since E5 landed: 186 passed, 0 failed, 1
skipped.** Q19, Q20, Q23, Q24 and Q34 are answered and closed; fifteen questions
remain open.

**The drop arrived in a new and better shape.** Not a tarball of files to unpack
over the tree but a script that edits by targeted string replacement, asserting
exactly one match per edit, with `DECISIONS_APPEND.md` and `NOTEBOOK_APPEND.md`
concatenated onto the append-only files. That is Q18's fix, acted on before Q18
is formally answered, and it worked: my "ninth block" entry and D59 both
survived, and the notebook went from 30 entries to 31. One residual hazard worth
noting for next time — `main()` writes each edit as it goes, so a failure on
edit *n* leaves edits 1…*n*−1 applied. It did not fire, and git would have
recovered it, but a drop that wrote nothing until every edit had matched would
be strictly better.

**A decision-number collision, which is exactly what check 3 exists to catch.**
The drop was built at 07:06 against a GitHub read that predated D60, D61 and
D62 — which I pushed at 10:23. Its D60/D61/D62 were *different decisions* with
the same numbers: log compression, `cycle_divisor`, the alignment axis, against
my P2 rehearsal, per-segment randomisation and P2 alignment. `DECISIONS.md` is
append-only and authoritative, so duplicate numbers make every citation
ambiguous.

Simon's decision was to renumber the incoming set to **D67–D73**, mine being
already published and cited in commit messages and notebook entries that must
never be edited. 36 references across the drop's four files were renumbered.
Verified afterwards: 69 decisions defined, highest D73, no duplicate numbers,
and no citation anywhere in the tree resolving to nothing. **The design session
must be told its numbers moved** — it will otherwise cite D60 for the log
branch, which is now my P2 rehearsal entry.

**Two section-number slips, fixed while renumbering.** D71's text and a
self-reference inside the new section both called it "section 9" of the
validation protocol. Section 9 is *Review practices*; the rule is installed as
section 13. Consistent with the drop having been drafted as section 9 and
renumbered late.

**The sheet made a falsifiable prediction, it failed, and chasing it found the
missing piece.** "`test_T5_3` passes at the new default without modification" —
it did not, failing on the identical 32.12 ms. The reason is that the drop
changes the *contract* and the implementation is mine: SPEC 4.6 now declares
`cycle_divisor=1` and SPEC 3 declares the log branch as `log(1 + e/epsilon)`,
while `src/` still had 4 and `log(e + epsilon)`. The design session cannot edit
`src/`. Had the sheet not made a checkable prediction I would have applied the
drop, seen one test still red, and had no way to tell a stale drop from an
incomplete application.

**D67 was verified to do what it claims rather than assumed.** Implemented as
`np.log1p(e / epsilon)` — exact for small arguments, and exactly 0.0 in
silence, which makes SPEC 4.1's all-zero-drive requirement hold by construction
rather than by every encoder's threshold happening to sit above the floor.
Measured: the log drive now spans **[4.801, 17.461]** with no negative samples,
against [−13.62, −0.96] and 100 per cent negative. E1 gains a full operating
range under log compression — Λ from 19662 down to 34 across θ = 1 to 16, a
575× span against D27's required 4×. And E6 stops inverting: the correlation
between its own frame energy and true audio RMS goes from **−0.280 to +0.261**.

**No recorded result changes.** Every task run so far used power compression,
precisely because log was unusable — which is what Q23 was raised about. D72
covers the other direction: T1 figures taken before D69 are lower bounds rather
than errors, and carry that note where cited rather than being regenerated.

**Tests:** 186 passed, 0 failed, 1 skipped, from 184/2/1. Both former failures
were Q19 and Q20. Nothing else moved, as the sheet predicted.
**Results written:** none.
**Blocked on:** Q28 and Q31 need Oliver. Fifteen questions open, of which the
design session says Q17, Q18, Q21, Q22, Q25, Q26, Q27, Q29, Q30 plus a
compression coverage gap are in patch 2.
**Next:** CI should now go green for the first time, which clears Q25's
blindness as a side effect — no implementation-session test has ever run in the
clean environment because the Layer 1 step failed ahead of it. Verify that on
the next push. Then the compression axis is genuinely available for the first
time, so the T1 sweep could be re-run under log as well as power.

## 2026-09-08 | session: implementation (session close)
**Did:** Closing a long session. Everything is committed and pushed;
`origin/main` and `HEAD` are both at the same commit and the tree is clean.
**186 passed, 0 failed, 1 skipped, and CI green — including the "Everything
else" step, which ran for the first time and reported 102 passed.**

**Where the project stands.** All six encoders implemented; the probe harness
and all three tasks running end to end with R2 alongside; P1 and P2 rehearsed;
the encoder survey at v2 and a one-page decisions brief both sent to Oliver.
Day 20, week 3 of 12. Weeks 1–2 and 5–7 of §9 are done in substance, on a
synthetic stand-in.

**Oliver will prioritise the TIMIT licence tomorrow** (Simon, after today's
meeting). That changes the shape of the next session: O2 has been the largest
blocker since 2026-08-20 and may clear.

**Start the next session here, and in this order.**

1. **The harness violates D71 and this is the first thing to fix.** §13 of the
   validation protocol, added today, requires every free parameter to be
   selected per condition on data held out *within the training split, never on
   test*. `run_t2` (harness.py:918), `run_t3` (:697) and `run_p1` (:556) all
   pick the best offset — and `run_p1` the best tau_phi — by maximising over
   **test-set** scores. Only `_select_ridge_alpha` does it correctly, because
   D59 named that one parameter specifically. So every "at best offset" figure
   in T2, T3 and P1 is selected against the number it reports. Unlike T1's
   offset-zero figures, which D72 covers as *lower* bounds, this bias points
   upward. Generalise `_select_ridge_alpha` into one shared mechanism; record
   the grid and chosen value per condition; and record the **analytically
   predicted offset** beside the selected one — declared front-end lag plus the
   kernel's first moment — which is what the APPLY sheet asked for and what
   turns the sweep into a check on the two lags rather than a fit.
2. Restate C5 per D70: sweep at least ±2 frames and confirm an **interior
   maximum**, rather than confirming a drop at ±1.
3. Re-run and supersede T2, T3, P1 and P2 under the corrected selection. The
   difference between the two is the measurement of how large the bias was.
   T1 stands as recorded, per D72.
4. **The TIMIT loader, which has tomorrow's deadline.** `TimitCorpus`
   implementing the three attributes of the corpus interface. Two things to
   settle early: the box has no `soundfile` and no `sph2pipe`, and NIST SPHERE
   comes both as plain PCM behind a 1024-byte ASCII header — readable in numpy
   — and shorten-compressed, which is not. If LDC93S1 arrives compressed we
   need `sph2pipe` built or `sox` installed, and that is better found out
   before the data lands than after.

**Not yet: the compression axis.** D67 makes the logarithmic branch usable
across all six encoders for the first time, and §6.6 declares compression a
swept parameter, so a T1 sweep under log as well as power is now a real
experiment. But the design session flagged the matching coverage gap in the
same breath — no generic gate exercises the compression axis, because
`conftest`'s drive is positive — and put it in patch 2. Sweeping an axis
nothing tests would be the wrong order.

**Open:** fifteen questions. Q28 and Q31 need Oliver. Patch 2 is expected to
carry Q17, Q18, Q21, Q22, Q25, Q26, Q27, Q29, Q30 and the compression gate gap.
**One thing to relay:** the design session's decision numbers moved. D60→D67,
D61→D68, D62→D69, D63→D70, D64→D71, D65→D72, D66→D73. It will otherwise cite
D60 for the log branch, which is now the P2 rehearsal entry.
**Results written:** none this block.
**Tests:** 186 passed, 0 failed, 1 skipped.

## 2026-09-09 | session: implementation
**Did:** The D71 selection fix, its re-runs, and the TIMIT reader.

**The fault, confirmed in the code rather than taken from the handover.**
`run_t2:918`, `run_t3:696` and `run_p1:552` built their offset profile from
*test* scores and took the argmax; `run_p1` did the same over `tau_phi`.
`run_reference.py` and P1's ceiling had it one level up — R2's own alignment,
and equation (40)'s denominator, were both taken at their test argmax. Only
`_select_ridge_alpha` was right, because D59 named that one parameter.

**One mechanism, not four.** `spikeenc/selection.py`: speaker-disjoint folds
inside the training split, one recorded grid per condition, chosen value
applied to a refit on the whole training split. `_select_ridge_alpha` is gone,
rewritten as a call into it. D74-D79 record the six decisions this needed.

**The fold count was chosen on evidence and it overrode an approved answer.**
Simon picked 3-fold this morning; at K=3 the inner fit set is four speakers of
seven and T2's inner RMSE sat at **3.5 semitones against 1.35 at test**, which
is the floor — the selection was being made by models that could not do the
task. At K=5 and K=7 the inner RMSE matches test. Leave-one-speaker-out
everywhere, declared per run in the configs, at roughly double the cost.

**How large was the bias.** This is the measurement the fix makes possible and
it is not uniform across tasks.

| condition | selection bias, three seeds |
|---|---|
| T1, all six budgets | **0.0000 at every point and every seed** |
| R2 on T1, both alignments | **0.0000** |
| T3 at context 2 and 5 | 0.000 to 0.032, mean 0.008 |
| T3 at context 0 | 0.002 to **0.128** |
| T2 | 0.000 to **0.150** |
| P1 temporal | 0.000 to 0.069 |

**And for P1 it reversed the conclusion.** Equation (40) at the honestly
selected operating point against the same index computed the way the pre-D71
code computed it:

| Λ | count | ceiling | denominator | TII selected | TII at test argmax |
|---:|---:|---:|---:|---:|---:|
| 160 | 0.7870 | 0.9676 | +0.1806 | **+0.128** | +0.208 |
| 397 | 0.8843 | 0.9676 | +0.0833 | **−0.056** | +0.352 |
| 997 | 0.9306 | 0.9676 | +0.0370 | **−0.250** | +0.143 |
| 2447 | 0.9583 | 0.9676 | +0.0093 | undefined | −0.500 |
| 6037 | 0.9583 | 0.9676 | +0.0093 | undefined | +0.000 |
| 15343 | 0.9491 | 0.9676 | +0.0185 | undefined | +0.667 |

The index changes **sign** at two of the three budgets where it is defined at
all. Selected on test, P1 said timing buys a third of the available headroom
at Λ = 397; selected inside the training split it says timing buys nothing
there and is slightly worse than counting. The reason the swing is so violent
is in the denominator column: it collapses from 0.18 to 0.009 as the budget
rises, because the count condition reaches 0.958 against a ceiling of 0.968.
A thin denominator turns a small numerator bias into a large index. That is
Q28's argument arriving as a number rather than as an argument, and it is why
`tii_denominator` is reported beside the index.

**This contradicts P-06** ("P1: temporal information index high for T2 and T3,
moderate for T1") on its T1 clause, at five of six budget points. The
investigation CLAUDE.md requires is the paragraph above: the contradiction is
attributable to the corpus rather than to E1, because the stand-in's phones are
stationary resonances so a per-channel count over a segment nearly identifies
it, which is exactly what Q28 says and what D60 records P1 as being a rehearsal
of. P-06 is **not** marked resolved and must not be, on this corpus.

**The predicted offset is the selected offset, and R2 is the clean test of it.**
R2's lag is a different quantity from the gammatone group delay — half a 25 ms
analysis window against a filterbank's phase response — and it is predicted
without fitting anything. Causal R2 selects −1 on all three seeds and is
predicted −1; centred selects 0 and is predicted 0. E1 on T1 selects −1 at
five of six budgets, predicted −1. The exception is Λ = 160, which selects −2
unanimously: at that event rate the features integrate over longer, which is a
real effect rather than noise precisely because it is unanimous.

**Two places the prediction and the selection part company, both informative.**
T3 at context 2 and 5 selects offset 0 at every budget and every seed, against
a prediction of −1, with C5 passing — so it is a stable disagreement and not
noise. T2's selected offset wanders over −2, 0, +1, +2 with no pattern, and C5
fails at six of thirty (condition, seed) pairs. Q38 is raised about the second:
T2's headline correlation does not resolve the alignment axis on this corpus,
because the stand-in's f0 is a linear declination and shifting a straight line
changes its intercept and not its slope. Validation RMSE does resolve it, and
agrees with the low-channel prediction of −2, which is where f0 lives. Both
readings are recorded in every T2 result.

**T3 at context 0 is where the controls bite hardest.** Offsets −3, +1, −3
across three seeds, C5 failing on all three, bias up to 0.128 — and at context
2 the same condition is offset 0 on every seed with C5 passing and bias 0.006.
A per-frame probe with no context has no representation of a boundary at all,
so its posterior is noise and the alignment axis is genuinely undefined. Q30
says this; the C5 column is now the evidence for it.

**The bias was not uniform across conditions, so it distorted comparisons and
not only levels.** Every figure in the v2 survey sent to Oliver is superseded,
and the two sides of a comparison did not move together:

| figure, v2 as sent | v2 | now | moved |
|---|---:|---:|---:|
| T2, E1 r/utt | +0.5755 | +0.5525 | −0.023 |
| T2, R2 r/utt | +0.4991 | +0.4604 | −0.039 |
| T3, E1 F | 0.7576 | 0.7557 | −0.002 |
| T3, R2 F | 0.6852 | **0.5930** | **−0.092** |
| T3, R2 frame AUC | 0.6888 | 0.7519 | +0.063 |
| P1 index | +0.20 to +0.80 | +0.128, −0.056, −0.250 | sign |

R2 on T3 lost 0.092 where E1 lost 0.002, because E1's offset was already
pinned at 0 on every seed while R2's wandered over −1, 0, +1 — so R2 had noise
to harvest and E1 did not. The E1-over-R2 gap on T3 therefore *widens* from
+0.072 to +0.163 under the honest procedure. A bias that differs by condition
can move a ranking, and here it moved one in the direction that makes Q31
harder to explain away rather than easier.

**E1 beats R2 on both T2 and T3 at the highest budget**: F 0.7557 against
0.5930 at context 5, and r/utt +0.5525 against +0.4604. Q31 is about the first
and now has a second instance, under a selection procedure that cannot be
flattering E1 because neither condition saw test.

**T1's pre-D69 figures were lower bounds by four to five points**, as D72 said:
0.8996 at Λ = 15343 against 0.8179 at offset zero.

**P2 re-ran and its conclusions survive, with the numbers moved.** Alignment
fixed at the clean best under the new selection — T1 −1, T2 0, T3 0 — and held
across every corruption per D62. Worst headroom lost, against the v2 figures
as sent:

| operator | T1 | T2 | T3 |
|---|---:|---:|---:|
| whole-utterance randomisation, v2 | 1.08 | 0.69 | 2.85 |
| whole-utterance randomisation, now | 1.06 | 0.77 | 2.20 |
| per-segment randomisation, v2 | 0.10 | 0.30 | 2.73 |
| per-segment randomisation, now | 0.21 | 0.20 | 1.99 |

Q35's contrast is unchanged in substance: the two operators still support
opposite conclusions about T1, 1.06 against 0.21, a factor of five. The second
run reproduced the first exactly, which is worth stating because the first run
died before recording and the two are therefore an unintended determinism
check on the whole P2 path.

One thing in the grid is asymmetric in a way worth a look later:
`channel_shift = −2` costs T2 0.56 of its headroom while `channel_shift = +2`
costs it −0.01, i.e. nothing. Q37 already asks whether `channel_shift` is
translation plus truncation and whether the truncation dominates; a clean
sign asymmetry on the task that lives in the low channels is what that would
look like. Not investigated here.

**P-07** ("the three tasks degrade under different corruption operators") is
consistent with the grid — T3 loses 1.2 to 1.5 of its headroom to channel
shifts that cost T1 0.01, and T1 loses everything to whole-utterance
randomisation — but P2 is a rehearsal under D60 and P-07 is not marked
resolved on this corpus.

**P2 cost half an hour to a name collision.** The alignment scan's `clean` dict
shadowed the corruption loop's `clean` entry, so the run completed its whole
grid and died on its last line. Renamed and re-run. Nothing was recorded from
the failed attempt, which is the provenance guard working as intended.

**TIMIT, second half of the session.** `spikeenc/sphere.py` reads NIST SPHERE
on numpy and scipy alone, because this box has no `soundfile`, no `sph2pipe`,
no `sox` and no `ffmpeg`, and CI has less. Uncompressed PCM is ten lines behind
an ASCII header. `shorten`-compressed SPHERE is a different format and is not
read here; that case raises `UnsupportedEncoding` naming the coding string and
naming the two tools that would decode it, because a compressed file read as
PCM does not fail — it produces noise that runs all the way through the
filterbank. **If LDC93S1 arrives compressed, one of those two needs
installing, and that is the thing to check first when it lands.**

`timit_corpus` implements the same three attributes as the stand-in: case
insensitive paths, phone times from each file's own sample rate, SA sentences
excluded by default, `f0` left as None so T2 raises by name rather than
scoring an invented contour. `fold_to_39` is the collapse proposal 4.1 requires
be stated wherever a figure is quoted; it merges adjacent segments that fold
together, which deletes hand-placed boundaries by construction, so T3 takes
the unfolded corpus.

**Tests:** 220 passed, 1 skipped, from 186. Two new files: 15 in
`tests/test_selection.py`, 19 in `tests/test_timit.py`. The selection tests
assert a property rather than a value — the selected parameter must not change
when the test set is destroyed — because that is the whole content of D71 and
a test asserting a particular offset would have gone on passing throughout the
period the offsets were being chosen against the number they reported.
`tests/test_known_answers.py` and `conftest.py` untouched.
**Results written:** all six superseded — `probe_e1_t1_synthetic`,
`reference_r2_t1_synthetic`, `t2_f0_contour_e1_synthetic`,
`t3_boundary_e1_synthetic`, `p1_count_only_e1_synthetic`,
`p2_corruption_e1_synthetic`, each with a new manifest entry.
**Blocked on:** Q28 and Q31 need Oliver. Q38, Q39 and Q40 are new and go to
the design session. Patch 2 is still expected to carry Q17, Q18, Q21, Q22,
Q25, Q26, Q27, Q29, Q30 and the compression gate gap.
**Next:**
1. **Report v3 is now owed three ways.** Every T1, T2, T3, P1 and P2 figure in
   v2 is superseded, the P1 index has changed sign, and `build_encoder_report`
   still reads `misaligned_accuracy` for its "at best offset" column, which now
   means a neighbourhood of the selected offset rather than a full sweep.
2. **The compression axis**, still gated on patch 2's coverage gap: no generic
   gate exercises it because `conftest`'s drive is positive. D67 made the log
   branch usable and §6.6 declares compression swept, so a T1 sweep under log
   as well as power is a real experiment as soon as something tests the axis.
3. **TIMIT the day it lands**: check `sample_coding` first, then T1 and T3 run
   immediately. T2 waits on Q40's two pitch trackers.

## 2026-09-09 | session: design
**Did:** Read the primary Spiketrum source in full — Tang et al., "Neuromorphic
Auditory Perception by Neural Spiketrum", TETCI 9(1) 2025 — and corrected
sections 2, 5.2, 5.7, 9 and 10 of the proposal accordingly. D80. No code
changes, no results affected, no schedule change. D09 stands; O3 is restated
and needs Oliver.

**The reconstruction from abstracts was right about the algorithm and wrong
about everything around it.** Matching pursuit, controllable rate and
reconstruction all held up — the authors' own name for it is Event-based
Temporal Matching Pursuit. What did not hold up: the work is led from Zhejiang
by Tang, not developed at Manchester by Alsakkal and Wijekoon, who are two of
eight co-authors; E7 does share the gammatone front end, since its dictionary
is ERB-spaced gammatone atoms; and reconstruction is not a privacy axis.

Worth noting which parts survived. The algorithmic reconstruction was accurate
because matching pursuit has few degrees of freedom once identified, so
inferring the equations from an abstract was safe. The attribution was wrong
because citation records show institutions, not who led the work, and nothing
in that process would have flagged the error. The lesson is not that inference
from abstracts is unreliable in general but that it is unreliable in a
predictable place: it is safe for the technical content of a well-known method
and unsafe for anything social — who did it, where, and in what relation to us.

**The correction strengthens the case for E7 rather than weakening it.** The
shared front end removes the confound that made E7 look like an outsider. What
remains is that E1 to E6 all decide locally, from state at one channel at one
moment, while matching pursuit selects the globally best-explaining event at
each step. E7 is not a seventh point on our continuum; it is the only member of
a second class, and the axis separating it is the study's own independent
variable. Leaving it out means the conclusions are about local event rules, and
the paper has to say so.

**One new obstacle, invisible before.** Intensity-to-place coding gives M x K
channels — 1920 at the paper's settings against the few dozen we sweep. That is
resolvable by choosing K, but it has to be settled before E7 enters, since a
feature vector an order of magnitude longer than the other arms' is not matched
treatment under C4.

**D09 is not touched by any of this and was not treated as if it were.** Its
reasoning is collegial rather than technical, and having the algorithm in front
of me changes the feasibility and not the attribution. The middle course put to
Oliver as O3 — implement the published algorithm, report it as our
implementation of that algorithm and not as the authors' system — is offered as
a decision for him rather than taken here.

**Also corrected: the misattribution may already have circulated.** The encoder
survey went to Oliver at v2. If that document carries the same wording, the
error is already outside the repository and describes people he may be about to
contact.

**Tests:** none run, none affected — this touches the proposal only.
**Results written:** none.
**Blocked on:** O3 with Oliver, alongside Q07, Q28 and Q31. E7 remains outside
the critical path.
**Next (design session):** patch 2 — Q17, Q18, Q21, Q22, Q25, Q26, Q27, Q29,
Q30, the compression-axis coverage gap, and the apply-time decision numbering
now prototyped in this drop.

## 2026-09-09 | session: implementation (E7 block)
**Did:** Read the primary Spiketrum source, raised Q41, applied the design
session's E7 drop as D80, raised Q42 against one figure in it, and corrected
the two report builders.

**Both sessions read the same paper independently and agreed.** Simon supplied
`tang_2025_neural_spiketrum.pdf` and I wrote Q41 from it before knowing a drop
existed; the drop landed while Q41 was being written. On the substance we
converge: the attribution, the two-stage algorithm, the ERB-spaced gammatone
dictionary, exact rate control. The design session found one thing I missed and
it is the sharpest point in the drop — describing reconstruction fidelity as a
*privacy axis* was wrong, because a representation the audio can be recovered
from carries the same restricted content as the recording rather than a milder
version of it. That is a category error, not a degree error, and it was in the
proposal. I had read the same paragraph and let it stand.

**I found one thing the drop got wrong, and it is a number.** §5.7 now says
"at the paper's own settings, with K = 30, a 64-atom dictionary yields 1920
channels". Neither `1920` nor a dictionary size of 64 occurs in the paper; the
only configuration it states is the hardware's 40 kernels × 3 intensities =
**120 channels**, and K = 30 is described there as the small end rather than as
their setting. Q42. The conclusion inverts with the number: at 120 channels the
expansion sits *inside* the range this study sweeps rather than an order of
magnitude above it, so the C4 concern is much weaker than §5.7 states, and the
third question O3 puts to Oliver — what K to use — may already be answered by
the authors' own hardware.

Worth recording where that leaves the pair of us. §2 of the validation protocol
says the assistant will occasionally produce a plausible false claim and will
not signal it, and it names the Spiketrum description as its example. The drop
corrects that instance and introduces another, of a different kind: the drop's
own entry concludes that inference from abstracts is "safe for the technical
content of a well-known method and unsafe for anything social". This error is
neither — it is a specific numeric parameter. The generalisation was drawn one
case too narrowly. What actually caught it was not a better rule but having the
PDF on the same machine as the checker.

**Not corrected by me.** Editing a design-session document on my own judgement
is what the precedence rule forbids, so §5.7 keeps the figure until the design
session rules on Q42. Report v3 must not quote it and the builder does not.

**The misattribution had already circulated, as the drop suspected.** Report v2
§10.1 said "developed at Manchester by Alsakkal and Wijekoon" and the one-page
brief framed O3 as "the approach to Wijekoon". Both are with Oliver. Generated
documents cannot be recalled, so the fix is at the source, with a dated note in
the report saying what v2 said and why it was wrong, per D45.

**`docs/references.md` is new.** §2 requires factual claims to be traceable to
a primary source and there was nowhere in the repository for a source to live;
the proposal cites inline by surname only. It records read-in-full separately
from cited-from-abstracts, because that distinction is exactly what failed
here. `papers/` is gitignored — the PDF is licensed and the repo is public.

**The apply-time decision numbering worked and should stay.** The drop shipped
`{{D_E7}}` and allocated D80 against the highest number in `DECISIONS.md` at
apply time, which was D79 because this session's own six had been committed
first. That is the fix for the collision the Q09-Q16 drop hit. It also shipped
`NOTEBOOK_APPEND.md` rather than `NOTEBOOK.md`: 59 lines added, none removed.

**Tests:** not re-run; this block touched the proposal, questions, references
and two report builders, and no library code. 220 passed, 1 skipped as of the
previous block.
**Results written:** none.
**Blocked on:** Q42 with the design session, and it should be settled before
O3 goes to Oliver. Q41 likewise. O3, Q28 and Q31 need Oliver; Q38, Q39, Q40
need the design session.
**Next:** report v3, which now owes the D71 supersessions, the P1 sign change,
the D45 correction note and the E7 rewrite. Then the compression axis, still
gated on patch 2.

## 2026-09-09 | session: implementation (report v3)
**Did:** Built encoder survey v3. Every task figure in v2 is superseded, the
three items `PENDING_NEXT_VERSION` had been carrying are discharged, and three
new ones are recorded for v4.

**§13 is rewritten around the D71 re-runs**, with a new §13.4 giving the
measured size of the selection bias. That section is the reason the correction
was worth making rather than merely being owed: T1 and R2 come out at exactly
0.0000 at every budget and every seed, T3 with context at 0.0135 mean, T3 at
context 0 at 0.0398 rising to 0.1280 on one seed, T2 at 0.0205 rising to
0.1497, and P1's equation (40) changes sign at two of the three budgets where
it is defined. v2's most uncomfortable finding — the upper bound sitting below
the encoder it bounds — is resolved by the same change: R2 causal now scores
0.9133 against E1's 0.8996.

**§13.3 and §13.4 now read their numbers out of `results/` rather than
carrying them inline.** That is not tidiness. Two cells of the bias table were
wrong when I wrote them by hand, because I averaged only the E1 rows of a
conditions list that also holds R2's. The table said 0.008/0.032 for T3 with
context where the data says 0.0135/0.0645. Nobody would have caught it: it is
a plausible number in a table of plausible numbers, in a document whose whole
subject this week has been numbers that were not checked against their source.
Deriving it removes the class.

**E4's adaptation table is registered under D35, and it does not reproduce.**
v1 and v2 reported a peak ratio of 2.45 near delta_a = 1; the registered
measurement gives 2.00 at delta_a = 0.25 with a monotone decline above. The
parameters behind the old table were never written down, so the discrepancy
cannot be resolved by inspection and those numbers are withdrawn rather than
reconciled. The qualitative claim survives — non-monotone with an interior
peak — but the location is the part that bears on P-01, and v2 told Oliver to
centre a delta_a sweep in the wrong place. This is the cleanest illustration of
D35 the project has produced, and it came from the one table the report had
left unregistered.

Two implementation notes on that measurement. A fixed 200 ms steady-state
window returns NaN at delta_a = 4 and 8, because the interval is longer than
the window, so the measurement failed at exactly the adaptation strengths it
exists to characterise; averaging the final five *intervals* is
rate-independent, which is what a sweep over rate needs. And "from 8 ms to
139 ms" in the v2 prose half-matches: my delta_a = 2 gives 138.94 ms, and
nothing in my sweep gives 8 ms. Unresolvable without the old config, which is
the point.

**A defect older than this version: `*italic*` never rendered.** It was written
into the narrative from v1 onward and reached Oliver with the asterisks intact,
in v1 and v2 both. `_markup` handled `**bold**` only. Now handled, captions
included; zero stray asterisks in the rendered text.

**`build_oliver_brief.py` is now ahead of its output.** Its O3 row was
corrected when the Spiketrum attribution was fixed, but the brief has not been
rebuilt: the committed .docx and .pdf are the versions Simon sent on 8
September, and rebuilding would replace a sent document. Left deliberately
inconsistent and recorded here rather than resolved, because which of those two
is right is Simon's call and not the builder's.

**Tests:** 220 passed, 1 skipped — 84 passed, 0 failed, 1 skipped in the
known-answer suite, 136 implementation-session tests. The suite constants in
the builder were stale at 82/2/1 and are corrected, as were the per-encoder
counts for E5 (now 12 of 12) and the implementation-test count (102 → 136).
**Results written:** `e4_adaptation_ratio`, recorded twice — the first run
superseded by the interval-counting fix.
**Blocked on:** Q42 before §5.7's channel figures can be quoted anywhere; Q38
to Q41 and Q43 with the design session or Oliver.
**Next:** v4 owes the E5 span re-centred on D68's operating point, the Q42
reconciliation, and D81's phone-inventory caveat with a citation. None is
urgent. The next substantive work is TIMIT the day it lands: check
`sample_coding` first, then T1 and T3 run immediately.
