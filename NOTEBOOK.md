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
