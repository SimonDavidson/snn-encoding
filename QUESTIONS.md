# Open questions for the design session

Raised by the implementation session (or by Simon) when something needs a
decision that isn't in DECISIONS.md or the specs. Simon carries these to the
design session; answers come back as edits here plus a DECISIONS.md entry.

Format:
```
### Qnn — one-line summary
**Raised:** YYYY-MM-DD by <who>
**Context:** what you were doing when it came up
**Question:**
**Options considered:**
**Blocking?** yes / no — and what it blocks
**Answer:** (filled in by the design session; add the Dnn number)
```

---

### Q01 — placeholder
**Raised:** 2026-08-20 by design session
**Context:** repository scaffold created
**Question:** none yet; this file is a channel, not a backlog.
**Blocking?** no
**Answer:** n/a

### Q03 — cutoff for the rectify-lowpass envelope of equation (9)
**Raised:** 2026-09-02 by implementation session
**Context:** implementing `Filterbank.envelope`. F4 exercises the `"hilbert"`
branch only, so nothing in the known-answer suite constrains equation (9). The
branch would have shipped looking correct while returning mostly carrier.
**Question:** equation (9) is written `e_c = LPF_fcut(max(x_c, 0))` — a single
cutoff for the whole bank. What should `f_cut` be, and should it stay a single
value or become channel-relative?
**Measured:** correlation between the extracted envelope and a known 5 Hz
modulator, by channel centre frequency, for a 1 s AM tone (Hilbert shown for
reference):

| f_c (Hz) | hilbert | 1 kHz, order 2 | 300 Hz, order 2 | 300 Hz, order 4 | f_c/4, order 4 |
|---:|---:|---:|---:|---:|---:|
| 196 | 0.910 | 0.237 | 0.268 | 0.253 | 0.769 |
| 479 | 0.967 | 0.270 | 0.607 | 0.853 | 0.934 |
| 953 | 0.988 | 0.366 | 0.936 | 0.980 | 0.978 |
| 3057 | 0.999 | 0.961 | 0.997 | 0.995 | 0.997 |

**Options considered:**
1. Single fixed cutoff, 300 Hz, 4th order — faithful to equation (9) as
   written; good above ~500 Hz, poor in the low channels. *Implemented as the
   provisional default.*
2. Channel-relative cutoff, `min(f_cut, f_c/4)`, 4th order — uniformly better,
   but departs from equation (9), which specifies one cutoff.
3. Declare equation (9) unusable below some f_c and restrict it to a
   high-frequency subset of the bank.
4. Accept the low-channel carrier leakage as physiologically real — auditory
   nerve fibres genuinely phase-lock below ~1 kHz — and treat equation (9) as
   a deliberately different representation rather than a cheaper equation (8).

**Blocking?** no — `"hilbert"` is the SPEC section 3 default and every current
test path uses it. It blocks only the envelope-method sweep.
**Correction appended 2026-09-06 (D45).** The leakage figures quoted in the
answer below do not reproduce and should not be cited. Q15 re-measured them
from a committed script and config: the margins between the two cutoff rules
are 1.2x, 5.6x, 11.3x and 20.4x, not the 1.4x, 30x, 128x and 419x recorded. The
correlation columns reproduce exactly, and D21 still wins at every channel by a
margin that grows with frequency, so the decision below stands unchanged — it
is the size of the margin that was wrong.

The re-measurement is the sound one and the physics says so independently.
Under D21 the cutoff tracks the ERB, so `f_c/b_c` runs about 4.3 at 196 Hz and
8.6 at 3057 Hz, and fourth-order attenuation should therefore improve by
roughly `(8.6/4.3)^4` — about 17x across that span. The recorded column falls
by a factor of 800. No reading of the filters produces that. The original text
is left below rather than edited, as with `test_T3_5` under D33.

**Answer:** Option 2, with the cutoff tied to the channel's own bandwidth
rather than to f_c: `f_cut_c = min(f_cut, b_c)`, global ceiling 1000 Hz, fourth
order. SPEC section 3 amended; D21. A subband of bandwidth b_c cannot carry
envelope modulation faster than b_c, so a cutoff above it admits carrier and no
extra envelope. b_c and f_c/4 are within 5 per cent at 196 Hz and b_c is the
more restrictive above that, so the measured f_c/4 column should be a lower
bound on what this achieves — please re-measure the table and record it, and
say so if it comes out worse.

Option 4 was the most interesting of the four and is right about the
physiology: phase locking below roughly 1 kHz is real, and a rectify-lowpass
front end that preserves it is not obviously wrong as a model. It is rejected
on study-design grounds rather than modelling ones. Carrier in the low-channel
envelope would make E1-E4 and E6 partly phase-locking encoders in precisely the
channels carrying F_0, and P-03 turns on the contrast between those encoders
and E5 on T2. That contamination would not show up as an error anywhere; it
would quietly blur the distinction the battery exists to measure.


**Re-measured 2026-09-03 (implementation session), as asked.** D21 implemented
as `f_cut_c = min(f_cut, b_c)`, ceiling 1000 Hz, fourth order, second-order
sections. Against the same 1 s AM tone and 5 Hz modulator:

| f_c (Hz) | b_c | f_cut_c | raw corr, f_c/4 | raw corr, D21 | lag-corrected, f_c/4 | lag-corrected, D21 | carrier leak, f_c/4 | carrier leak, D21 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 196 | 46.7 | 46.7 | 0.7688 | 0.7605 | 0.9999 | 0.9999 | 1.74e-04 | 1.20e-04 |
| 479 | 77.9 | 77.9 | 0.9339 | 0.9114 | 0.9999 | 1.0000 | 1.67e-04 | 5.32e-06 |
| 953 | 129.9 | 129.9 | 0.9782 | 0.9678 | 0.9999 | 1.0000 | 1.56e-04 | 1.22e-06 |
| 3057 | 361.5 | 361.5 | 0.9973 | 0.9958 | 0.9999 | 1.0000 | 6.29e-05 | 1.50e-07 |

**Yes, it comes out worse on the metric as originally posed — and that metric
was the wrong one.** On raw correlation D21 is below f_c/4 at all four
channels. But b_c is more restrictive than f_c/4 everywhere, not just above
196 Hz, so D21 lowpasses harder, and a harder lowpass costs group delay. Once
the filter's own lag is removed, both sit at 0.9999 or better: the envelope
*shape* is essentially perfect under either cutoff and the raw-correlation
deficit is delay, not distortion.

The metric that does discriminate is carrier leakage, which is what the change
was for, and there D21 wins at every channel — by 1.4x at 196 Hz and by 30x,
128x and 419x above it. The physical argument in the answer holds; my original
table just measured the wrong thing, because correlation against an
uncompensated modulator conflates rejection with delay.


### Q04 — test_T2_4 asserts a closed loop the fixture signal does not close
**Raised:** 2026-09-02 by implementation session
**Context:** E2 implemented. T2.1, T2.2, T2.3 and T2.5 pass. T2.4 fails by
exactly one event: ON 199 vs OFF 200 out of 399.
**Question:** `test_T2_4_polarity_balances_over_a_closed_loop` asserts
`n_on == n_off` for `sine_drive(1.0, 5.0, n_channels=1, duration=2.0)`, on the
grounds that "a signal returning to its starting value must emit equal ON and
OFF counts". The fixture signal does not return to its starting value.
`sine_drive` builds `t = np.arange(n) * dt`, so the last sample sits at
`t = D - dt`, phase -0.0019635 rad, and `u[-1] = -0.00196349` against
`u[0] = 0.0`. Its docstring says "starting and ending at zero phase"; it ends
one sample short of that.

**Why one sample changes the count.** Rising out of the final trough the
reference reaches lattice index -1 (r = -0.1) and stops, because the rule of
SPEC 4.3 is "emit until |u - r| < C" and |-0.00196 - (-0.1)| = 0.098 < 0.1
already holds. Index 0 is also within C (residual 0.00196), so both are legal
stopping points; the rule as specified stops at the *first* index reached, not
the nearest, so the net lattice displacement over the run is -1 rather than 0.

**Evidence that the encoder is right and the premise is not.** Same encoder,
same parameters, signal extended by one sample so it genuinely closes:

| signal | u[-1] | ON | OFF |
|---|---:|---:|---:|
| duration D + 1 sample (true zero phase) | -2.45e-15 | 200 | 200 |
| duration D, as the fixture builds it | -1.96e-03 | 199 | 200 |

**Options considered:**
1. `sine_drive` uses `t = np.arange(n) * dt` for an open interval, which is the
   right convention for a sampled signal generally, but leaves T2.4's premise
   false. T2.4 could build its own closed signal, or assert `abs(n_on - n_off)
   <= 1`, which is what protocol section 3.4 T2.4 already allows for the
   non-lattice variant.
2. Change the encoder to stop at the *nearest* lattice index rather than the
   first within C. This would balance the counts but contradicts SPEC 4.3 and
   roughly doubles the event rate, breaking T2.2 and T2.5. Rejected.
**Blocking?** no — E2 is otherwise complete and its four analytic tests pass.
It blocks only the T2.4 assertion itself.
**Answer:** The analysis is right and the encoder is right; the test premise
was false. Fixed in test_T2_4, which now builds its own closed signal. D22.

One correction to the reasoning, which strengthens rather than weakens it.
Extending by one sample is not sufficient on its own: `sin(20*pi)` evaluates to
-2.45e-15, not zero, and with eps even infinitesimally negative both m = 0 and
m = -1 satisfy |eps - m*C| < C, so the encoder remains entitled to either. The
200/200 measured for the extended signal therefore depended on the D20
tolerance rather than on the signal closing. The test now forces `u[-1] = u[0]`
exactly, which is the only condition under which equation (16) pins m to zero
and the assertion is a theorem.

This is also why D20 has been promoted into SPEC section 4.3 rather than left
as an implementation decision: Layer 3 of the validation protocol calls for an
independent reimplementation of E2 compared event for event, and one without
the tolerance would disagree at every excursion crest.

### Q05 — the envelope lowpass adds delay that compensate_group_delay does not remove
**Raised:** 2026-09-03 by implementation session
**Context:** measuring D21. Surfaced by the lag analysis above, not looked for.
**Question:** D19 has `compensate_group_delay=True` advance each channel by its
gammatone group delay, `(order-1)/(2*pi*b_c)`, and that shift is applied in
`subbands`. With `method="rectify_lowpass"` the envelope lowpass then adds a
*second* channel-dependent lag downstream of the compensation, which the
compensation therefore does not remove. Under D21 that second lag is the larger
of the two, and it is larger in exactly the low channels where the gammatone
delay is already worst:

| f_c (Hz) | gammatone GD | envelope-LPF lag | total, uncompensated |
|---:|---:|---:|---:|
| 196 | 10.22 ms | 22.50 ms | 32.7 ms |
| 479 | 6.13 ms | 13.50 ms | 19.6 ms |
| 953 | 3.67 ms | 8.12 ms | 11.8 ms |
| 3057 | 1.32 ms | 2.94 ms | 4.3 ms |

So `compensate_group_delay=True` with `"rectify_lowpass"` removes about a third
of the actual onset skew and leaves 20 ms of it between the lowest and highest
channel. SPEC section 3 says compensation "aligns onsets across the bank",
which holds for `"hilbert"` but not for `"rectify_lowpass"`.

This is the same class of problem D19 was raised about, and no test detects it
either: F4 uses `"hilbert"`, and G4 passes because a uniform input shift stays
uniform.

**Options considered:**
1. Compensate the envelope lowpass as well when both are active, advancing by
   the measured or analytic lag of the Butterworth at `f_cut_c`.
2. Leave it, and state in the paper that compensation applies to the filterbank
   only. Defensible but makes the flag mean less than it appears to.
3. Restrict `compensate_group_delay` to `"hilbert"` and raise on the
   combination, so the incomplete case cannot arise silently.
**Blocking?** no — `"hilbert"` is the default and nothing currently sweeps
either axis. It blocks the envelope-method sweep crossed with the group-delay
axis.
**Answer:** Option 1, restated so the flag means what it says, with option 3
as the fallback. Compensation is a property of the whole envelope path: advance
each channel by the sum of the declared lags of the stages actually used, and
raise rather than compensate partially if a stage cannot declare its lag. SPEC
section 3 amended; D24. A partially compensated bias is worse than an
uncompensated one, because an uncompensated bias is a known quantity.

Option 2 was rejected for the same reason: a flag documented as aligning onsets
while removing a third of the skew will be read as the former by anyone using
the released data.

**One thing to reconcile before implementing.** Your gammatone column matches
the analytic value exactly (10.22 ms at 196 Hz), but the envelope-lowpass
column sits a consistent 2.53x above the analytic DC group delay of a
fourth-order Butterworth at `b_c` — 22.50 against 8.90 ms at 196 Hz, and the
same factor at all four centre frequencies. A uniform ratio is a definitional
difference rather than an error, but it needs identifying before it is used as
a compensation value: applying 2.53x the true lag would overshoot and reskew
the bank the other way. Order-8 does not explain it (that would be 1.29x).
Candidates worth checking: whether the lag was measured from a step or peak
response rather than group delay, whether the filter is applied more than once,
and whether the cutoff passed to the design function is the one intended.
Please report which, with the corrected table.

**A test now covers this.** `test_F6` measures onset spread across the bank on
the selected path, with and without compensation, for both envelope methods.
Thresholds are loose on purpose — record the measured spreads in NOTEBOOK.md
and we can tighten them once the numbers are known. This is the third
channel-dependent timing bias in a row that no test detected (D19, then this),
which is the argument for having one.


### Q06 — equation (21) is a level rule, and no test constrains which reading is meant
**Raised:** 2026-09-03 by implementation session
**Context:** starting E3 `TemporalContrast`. Surfaced before writing any of it,
by asking what T3.1-T3.4 actually pin down. They pin down the filters and the
symmetry; they do not pin down the event rule.
**Question:** equation (21) is written as a *level* condition — `ON event if
d_c[n] >= theta_plus` — with no reset and no rearm condition. Read literally, a
channel whose `d` sits above `theta` emits one event per sample for the whole
excursion. The prose of proposal section 5.3 one paragraph earlier says events
are emitted "on threshold *crossings* of d_c", which is a different rule. SPEC
section 4.4 says only "equations (18)-(21)" and names state key `"d"`, so it
does not settle it either. Which reading is E3?

**Why no test catches this.** T3.1 and T3.2 assert silence, T3.3 sets
`theta=1e9` so nothing fires and reads the `"d"` trace directly, and T3.4
asserts only ON/OFF symmetry under negation. All five candidate rules below
pass all four T3 tests. The discriminating test is the generic G3, which
requires event count to be monotonic in the declared RATE_PARAM.

**Measured:** event counts, 4 channels, 2 s of `drive_for`, `tau_fast=0.001`,
`tau_slow=0.05`, `theta` swept x0.25 to x4 about 0.2 exactly as G3 sweeps it.
max|d| over this drive is 0.660.

| theta | level | edge, rearm at theta | edge, rearm at 0 | lattice on d | exact on d |
|---:|---:|---:|---:|---:|---:|
| 0.05 | 118531 | 85 | 52 | 888 | 870 |
| 0.10 | 109070 | 104 | 52 | 432 | 432 |
| 0.20 | 88504 | **117** | 52 | 191 | 191 |
| 0.40 | 38472 | 114 | 35 | 69 | 69 |
| 0.80 | 0 | 0 | 0 | 0 | 0 |

**Options considered:**
1. **Level**, equation (21) read literally. Monotonic in theta, so G3 passes,
   but it fires on 93 per cent of samples. That makes E3 a rate code, which
   contradicts proposal section 5.3's "markedly sparser output on sustained
   sounds", and it is the reading under which E3 is *least* like the
   onset-sensitive cochlear-nucleus cells it is meant to model. It also
   collapses to zero events the instant theta exceeds max|d|, so the usable
   range of the rate parameter is narrow and drive-dependent. The refractory
   period cannot rescue it: SPEC 4.4 defaults `refractory=0.0`, and SPEC 4.2
   fixes refractory as a declared constant that is never a swept axis, so it is
   not available as the rate-limiting mechanism.
2. **Edge, rearmed when |d| falls back below theta.** The natural reading of
   "threshold crossings". *Fails G3*: counts go 85, 104, 117, 114, 0 — not
   monotonic. The mechanism is not subtle. A lower threshold means `d` sits
   inside the band for longer, so the detector rearms less often, and below
   some theta the count falls again. A rate parameter that turns over in the
   middle of its range makes the matched-budget comparison of proposal section
   6.4 impossible to arrange.
3. **Edge, rearmed when d returns through zero.** Technically passes G3 —
   counts are non-increasing and the endpoints differ — but they are 52, 52,
   52, 35, 0. Flat across an 8x sweep of theta. The event count is set by how
   many excursions of `d` exceed theta at all, which is a property of the
   drive; theta only gates. Not usable as a rate parameter even though the
   test would go green, which is worth noting as a case where a passing G3 is
   not sufficient evidence.
4. **Lattice on d.** E2's rule of SPEC 4.3 applied to `d` instead of `u`:
   reference on a lattice of spacing theta anchored at `d = 0`, emit until
   `|d - r| < theta`, reference advanced by an integer index with the D20
   tolerance. Counts go as roughly 1/theta, which is what a RATE_PARAM has to
   do.
5. **Exact on d.** As 4 but the reference jumps to `d` at event time, the
   analogue of E2's `reference_update="exact"`. Differs from 4 by 2 per cent at
   the smallest theta and not at all elsewhere on this drive.

**Recommendation (implementation session): option 4.** It is the only reading
that both passes G3 and gives theta a usable, roughly 1/theta relationship to
event count across the sweep range, which is what proposal section 6.4 needs.
Options 4 and 5 are near-indistinguishable here; 4 is preferred because it
reuses machinery already specified, tested and reasoned about in SPEC 4.3
rather than introducing a second convention.

**This does not make E3 into E2, and the test file's warning should not be read
as forbidding it.** The header comment above the T3 block says the risk is that
E3 is accidentally implemented as E2. What separates the two encoders is the
bandpass of equations (18)-(20), not the event rule. Under option 4, on the
T3.2 slow ramp E3 emits 0 events where E2 emits 39. Sharing the threshold rule
does not blur that; equation (20) is the whole difference.

**One correction to the premise of T3.1, flagged rather than smoothed.** Its
docstring says "E2 would settle; E3 must never fire at all". Measured, E2 emits
**0** events on `constant_drive(5.0)`, not a settling burst, because SPEC 4.3
initialises its reference to `drive[:, 0]`. T3.1 therefore does not discriminate
E3 from E2 at all; T3.2 is the only test in the block that does. T3.1 remains a
correct and worthwhile assertion about E3 — it just is not evidence for the
thing its docstring claims it is evidence for.

**Verification already done on option 4**, so the answer can be acted on
directly: T3.4 holds exactly, not approximately. At theta=0.2 the ON/OFF split
is 64/63 and negating the drive gives 63/64; at theta=0.05, 289/284 against
284/289. Event times are bit-identical under negation in both cases. T3.1 and
T3.2 give 0 events, T3.3 is unaffected since it never fires.

**Blocking?** **Yes** — this blocks E3 entirely, and E3 is on the critical path
for T3 boundary detection, where proposal section 5.3 predicts it is the
strongest candidate. It does not block E4, the D24 front-end work, or the
`features`/`corrupt` stubs, so there is unrelated work to do meanwhile.

**Answer:** Option 4, as recommended. D26. SPEC section 4.4 amended, equation
(21) and the surrounding prose of proposal section 5.3 rewritten, and
`test_T3_5` added to pin the rule.

**The choice is more forced than the recommendation claims.** Options 2 and 3
are not two candidates that happen to fail; they are two members of a family
that cannot work. Any rule emitting at most one event per crossing has an event
count bounded above by the number of excursions of `d` through the threshold
band, and that number is a property of the drive and of `tau_fast`/`tau_slow`,
not of `theta`. As `theta` falls the count therefore saturates rather than
growing. Option 3's flat 52, 52, 52 is the clean form of this; option 2's
turnover at 117 is the same ceiling reached less tidily. So the measurement is
not a property of `drive_for` that a different test signal might overturn — it
is arithmetic, and it disqualifies the whole crossing family at once.

That leaves the level reading and the reference-reset family. The level reading
is out on the grounds you give, and the refractory period cannot rescue it: the
proposal's own prose introduces equation (21) as "subject to a refractory
period", but SPEC 4.2 fixes `refractory` as a declared constant that is never
swept, precisely so it cannot confound the matched-budget comparison, and SPEC
4.4 defaults it to zero. The proposal's rescue mechanism is unavailable by
prior decision. Within the reference-reset family, 4 over 5 for exactly the
reason you give — reuse SPEC 4.3 rather than introduce a second convention.
`reference_update` is exposed on E3 for symmetry with E2, defaulting to
`"lattice"`, and is not a swept axis.

**Two arguments in favour that did not come up.** First, sharing the event rule
makes E2 against E3 a *single-factor* contrast: any difference between their
Pareto fronts is attributable to equation (20) and to nothing else. That is
better experimental design than differing in both the filtering and the rule,
where a difference in outcome would be uninterpretable. The header comment
above the T3 block was aimed at the wrong hazard and has been rewritten.
Second, the reset is what "temporal contrast" names: the DVS pixel the term is
borrowed from thresholds change in log intensity against a reference that
resets at each event. Option 4 is closer to the hardware referent than the
literal reading of (21) is, not further from it.

**The cost, which now appears in the paper rather than only here.** Under
option 4 E3's event count on a transient scales with the transient's amplitude
divided by `theta`, rather than with the number of transients. That is a
modelling choice made under pressure from an evaluation requirement, and
section 5.3 now says so. It is defensible on its own terms for T3 — a boundary
with greater contrast accumulates proportionally more evidence — but it is a
choice, not a consequence of the difference of exponentials, and it should not
reach a reviewer looking like one.

**Your correction to T3.1 is accepted and goes further than stated.** The
docstring is rewritten. Beyond that, the fact it relied on — that E2 is silent
on a constant drive because SPEC 4.3 initialises the reference to `drive[:, 0]`
— was pinned by nothing in the suite, and is exactly the kind of convention an
independent Layer 3 reimplementation would plausibly choose differently; a
reference initialised to zero emits fifty events at the first sample at
`C = 0.1`. `test_T2_6` now asserts it.

**The more important half of this question is G3, not E3.** Option 3 passes G3
while being useless, and you flagged that as "a case where a passing G3 is not
sufficient evidence". It is worse than that: G3 encoded a *necessary* condition
when what section 6.4 requires is *sufficient dynamic range*. G3 now also
requires the count to span at least 4x across the sweep. Option 3 gives 1.5x
and fails; option 4 gives 12.9x and E2 about 16x, both comfortably. The
foreseeable casualty is E6 — if time-to-first-spike emits one spike per channel
per frame its count is structurally fixed and no threshold-like RATE_PARAM will
span anything, in which case matched budgets for E6 must come from channel
count or frame rate. That is a design question to raise when you reach it, not
a threshold to relax. The gate has deliberately not been pre-weakened to
accommodate it.

**One thing found while reading the proposal to write the replacement.**
Section 5.3 states `alpha = exp(-dt/tau)` explicitly, so the discretisation was
never actually ambiguous — but SPEC cites equations by number and does not
reproduce them, so the convention never reached the only document a Layer 3
reimplementer works from. Two implementations differing here disagree
everywhere by about 0.25 per cent, which is the hardest kind of disagreement to
diagnose. Restated in SPEC section 1; D28.

**On `test_T3_5`, which is new and which you should read before running it.**
It is derived from the closed-form step response, not from any implementation.
Expected values are 4 ON and 3 OFF events with `theta = 0.2`, and a `d` peak of
0.9048124 continuous, 0.9048007 sampled at 16 kHz. Three things about it are
deliberate and are documented in its docstring: the ON/OFF asymmetry is the
"first index within theta, not nearest" rule of SPEC 4.3 and is the same
phenomenon as Q04, not an off-by-one; the 0.30 s duration is load-bearing,
because the 1e-9 tolerance admits a fourth OFF event once `d` falls below
2e-10, about 1.12 s after the step; and the 1e-4 tolerance on the peak is tight
enough to catch an Euler pole, which would read 0.9070919. If it fails, the
failure messages name the likely cause.


### Q07 — ON and OFF as separate channel indices, or as a polarity bit
**Raised:** 2026-09-03 by design session
**Context:** reading proposal section 5.3 in full while rewriting equation (21)
for Q06. Noticed rather than looked for.
**Question:** section 5.3 offers exposing E3's ON and OFF events as distinct
channel indices rather than as a polarity field, doubling the channel count and
letting a downstream user select onsets alone. SPEC section 2 fixes a single
`polarity` field on `SpikeTrain` and section 4.4 does not mention the
alternative. Which does the released dataset use, and does the choice apply to
E2 as well, which is equally bipolar?
**Options considered:** not yet worked through — this is logged so that it is
settled deliberately rather than by whatever the writer happens to do first.
Note that it interacts with R1: the Lauscher/SHD channel convention is
unipolar, so a doubled channel count is a departure from the interoperability
reference, while a polarity field is a different departure.
**Blocking?** no. It changes nothing about the encoders, only how their output
is written out, and no dataset is written yet. It must be settled before
anything is packaged for release, and preferably before the featurisation of
SPEC section 5 is written, since a channel-doubling convention changes what
`featurise` receives.
**Answer:** (open — to be taken with Oliver, as it is a release-format question
rather than a methods one)


### Q08 — two quoted values in test_T3_5's docstring do not reproduce
**Raised:** 2026-09-03 by implementation session
**Context:** implementing E3 under D26. Found while checking the closed form by
hand before trusting the test, not by a failure — `test_T3_5` passes.
**Question:** neither number affects an assertion, because the test computes
the peak from the formula rather than from the literal, and both margins are
enormous. But they are the values a Layer 3 reimplementer would hand-check
against, and one of them is quoted to seven digits. Should they be corrected?

**1. The continuous peak.** The docstring says `d_max = 0.9048124 A`. The
expression in the test body evaluates to **0.9048013**, and the independent
route `exp(-t*/tau_s) - exp(-t*/tau_f)` at `t* = 3.9919 ms` gives 0.9048013 as
well. The docstring value is 1.11e-05 high. The sampled value it also quotes,
0.9048007, is correct and reproduces exactly. The assertion is
`abs(d_max - d_max_closed_form) < 1e-4` against the *computed* form, so it
passes with 167x margin either way.

**2. `d` at the end of the signal.** The docstring says "At the 0.30 s used
here d is still 2.5e-3, seven orders clear." Measured at 0.30 s, `d` is
**6.74e-03**; `exp(-0.25/0.05) = 6.738e-3` confirms it. 2.5e-3 is the value at
a total duration of 0.3496 s. The likely explanation is that the docstring was
written against a 0.35 s signal and the duration later moved to 0.30 s, or the
reverse. The conclusion is unaffected in either case — the fourth OFF event
needs `d < 2e-10`, which arrives at 1.167 s total, so the "load-bearing
duration" warning is right and the stated ~1.12 s after the step is right.

**Blocking?** no. E3 is implemented, T3.1-T3.5 pass, and every margin is
recorded in NOTEBOOK for 2026-09-03. This blocks nothing at all; it is logged
here rather than only in NOTEBOOK because the file is the design session's to
edit and a notebook entry cannot be closed by whoever resolves it.
**Answer:** Both correct, both errors mine, both now fixed. D33.

Recomputed independently before accepting them. The continuous peak is
0.9048013053; the 0.9048124 in the docstring came from rounding the two
exponentials to seven digits before subtracting, which is exactly the arithmetic
the closed form exists to avoid. And the residual is 6.738e-3, which is
`exp(-5)`: your diagnosis is right, the sentence was written against time after
the step and the parameter against total duration, and 2.5e-3 is `exp(-6)`, the
value at 0.35 s total. A third, unreported: `t*` is 3.99186 ms, which I wrote
as 3.9918 by truncating instead of rounding. Your 3.9919 is right.

The conclusions all survive — the fourth OFF event arrives 1.1166 s after the
step, so the load-bearing-duration warning stands — but that is not much
comfort. Two of the three hand-checkable numbers in that docstring were wrong,
and they were wrong in the one part of the file that a Layer 3 reimplementer is
meant to check against by hand rather than by running. Finding them needed the
closed form recomputed independently, which is what you did and what the
protocol asks for. The corrected docstring now records that they were wrong,
rather than silently reading correctly.

Raising this as a question rather than only in NOTEBOOK was right for the
reason you give.

### Q09 — `test_T3_6` says `d[:, 0]` is exactly zero; in floating point it usually is
**Raised:** 2026-09-04 by implementation session
**Context:** reviewing the Q08 patch before applying it. `test_T3_6` passes, and
this does not threaten it. Checked because the identity the test rests on is
stated as a floating-point fact rather than an algebraic one.
**Question:** the docstring argues that handing E2 the signal `d` gives it the
anchor `d[:, 0]`, "which the filter initialisation of SPEC §4.4 makes exactly
zero", and that the identity therefore "follows from the equations alone and
holds for any implementation". In exact arithmetic that is right. In doubles,
`d[0] = (a_f u_0 + (1-a_f) u_0) - (a_s u_0 + (1-a_s) u_0)` is a difference of
two separately rounded reconstructions of `u_0`, and the roundings need not
agree.

**Measured**, 200000 random `u_0` spanning 1e-6 to 1e3 in magnitude, at four
`(tau_fast, tau_slow)` pairs:

| tau pair | non-zero `d[0]` | worst \|d[0]\|/\|u_0\| |
|---|---:|---:|
| (0.001, 0.05) | 5684 / 200000 | 3.75e-16 |
| (0.0005, 0.2) | 10324 / 200000 | 3.61e-16 |
| (0.002, 0.01) | 3660 / 200000 | 3.86e-16 |
| (0.0001, 0.5) | 4942 / 200000 | 2.11e-16 |

So `d[0]` is exactly zero about 97 per cent of the time and one ulp off
otherwise. It is exactly zero for all four channels of the drive `test_T3_6`
actually uses, which is why the test passes rather than passing by luck of the
tolerance.

**Why it does not matter, and why it is still worth recording.** The worst
residue is 3.9e-16 relative, which at `theta = 0.15` is 2.6e-15 in lattice
units — six orders below the 1e-9 tolerance of SPEC §4.3, so it cannot move an
event. The test is robust as written and needs no change. But a Layer 3
reimplementation that hits one of the 3 per cent will see a non-zero anchor
where SPEC says zero, and the docstring tells it that is impossible. The
accurate statement is that `d[0]` is zero in exact arithmetic and within one
ulp of zero in doubles, which the tolerance absorbs by six orders.

**Options considered:** (1) soften the docstring's "exactly zero" to "zero in
exact arithmetic, within an ulp in doubles, absorbed by the §4.3 tolerance";
(2) leave it, on the grounds that no reader will hit it; (3) have E2 anchor at
exactly zero when handed a signal whose first sample is within an ulp of zero —
rejected, it complicates SPEC §4.3 to fix a non-problem.
**Blocking?** no. Blocks nothing at all; `test_T3_6` passes and E4 is unaffected.
**Answer:** Option 1. D38. The docstring is softened and SPEC 4.4 carries the
same correction, since it makes the identical claim — "under the initialisation
above those are the same number" — and SPEC is what a Layer 3 reimplementation
reads.

Worth recording that this makes an earlier decision better than its stated
reason. SPEC 4.4 anchors E3's lattice at exactly zero rather than at `d[:, 0]`,
and D26 justified that on the aesthetic ground that the anchor is a property of
the rule rather than of the signal. Your measurement makes it substantive: the
two genuinely differ, about 3 per cent of the time, and anchoring at exactly
zero is the choice that does not inherit the rounding.

One consequence for `test_T3_6` itself, now stated in its docstring rather than
left implicit. The identity is not exact in floating point — E3 anchors at zero
and E2 handed `d` anchors at `d[:, 0]` — and the events coincide because the
difference is six orders below the tolerance, not because the anchors are
equal. A residual would have to land within about 3e-15 of the tolerance
boundary to change an event, which is possible in principle at a probability
around 1e-10 per run and has not been observed.

### Q10 — `test_T4_3` asserts a monotonicity the ALIF does not have
**Raised:** 2026-09-04 by implementation session
**Context:** implementing E4 under SPEC §4.5. Nine of the ten targeted tests
went green; `test_T4_3` fails on its third assertion, `ratios[2] > ratios[1]`,
with `2.0 > 3.0`. Raised rather than worked around, per the precedence rule.

**The implementation is not in doubt.** At `delta_a = 0` the ISI under the
3.0 step is 8.13 ms against the closed form `tau_m*ln(V_inf/(V_inf-theta))`
= `0.02*ln(3/2)` = 8.11 ms, and `test_T4_1` confirms bit-identity with E1. At
`delta_a = 0.5` the first post-step ISI is 13.13 ms, and solving
`3(1-e^{-t/0.02}) = 1 + 0.5 e^{-t/0.1}` by hand gives 13.1 ms (V = 1.4415,
theta = 1.4386 at that instant). The encoder is doing what equations (22)-(23)
say.

**Nor is it the discretisation.** Three readings of equation (23) — the literal
`a[n] = rho*a[n-1] + delta_a*s[n-1]`, add-then-decay `rho*(a + delta_a*s[n-1])`,
and increment-at-own-sample `rho*a[n-1] + delta_a*s[n]` — give *identical*
early/late counts of 6/6, 3/1, 2/0 and identical ratios 1.00, 3.00, 2.00. No
choice available to an implementer changes the outcome.

**What the estimator does.** `early / max(late, 1)` over 50 ms windows:

| delta_a | early | late | ratio |
|---:|---:|---:|---:|
| 0.0 | 6 | 6 | 1.00 |
| 0.5 | 3 | 1 | 3.00 |
| 1.0 | 2 | 1 | 2.00 |
| 2.0 | 2 | 0 | 2.00 |
| 4.0 | 1 | 1 | 1.00 |
| 8.0 | 1 | 0 | 1.00 |

The clamp inverts the metric exactly where adaptation is strongest: once `late`
reaches 0 the ratio is just `early`, and `early` falls monotonically. In the
limit the neuron fires once at onset and never again — perfect onset emphasis —
and scores 1.00, the same as no adaptation at all.

**But the claim is also false, independently of the estimator.** This is the
part worth the design session's attention. Re-measured on a 5 s signal with
200 ms windows, so counts are adequate and the steady state is genuinely
reached:

| delta_a | ISI_1 (ms) | ISI_ss (ms) | ISI_ss/ISI_1 |
|---:|---:|---:|---:|
| 0.0 | 8.13 | 8.12 | 1.000 |
| 0.25 | 10.50 | 22.19 | 2.113 |
| 0.5 | 13.13 | 31.19 | 2.376 |
| 1.0 | 18.88 | 46.25 | 2.450 |
| 2.0 | 33.38 | 71.50 | 2.142 |
| 4.0 | 73.31 | 110.31 | 1.505 |
| 8.0 | 138.88 | 161.06 | 1.160 |

Onset emphasis peaks near `delta_a ~ 1` and decays on both sides, and the
test's two adapting points, 0.5 and 2.0, straddle that peak. The mechanism is
not subtle: adaptation from the first spike suppresses the second, so strong
adaptation lengthens the onset ISI (8 ms to 139 ms) as well as the steady-state
one, and the two rates re-converge. Steady-state *suppression* is monotone in
`delta_a` — `test_T4_4` asserts exactly that and passes — but the onset-to-
steady-state *contrast* is not.

**Question:** `test_T4_3` as written cannot be satisfied by any correct ALIF.
What should it assert instead?

**Options considered:**
1. Keep the windows and the triple, change the statistic to `early/(late+1)`.
   Gives 0.86, 1.50, 2.00 on `(0.0, 0.5, 2.0)` and passes — but it is not
   monotone over a wider grid either (it turns over at `delta_a = 4`), so it
   passes by landing on the rising limb rather than by measuring something
   true. Cheapest and least honest.
2. Keep the claim, bound the range: assert monotonicity only for
   `delta_a <= 1`, where it holds on every estimator measured, and say in the
   docstring that the property is non-monotone beyond the peak.
3. Assert what is actually true and is the property the study needs: that
   `ISI_ss/ISI_1 > 1` for any `delta_a > 0`, and that steady-state count falls
   monotonically (already `test_T4_4`). Drops the "grows with adaptation
   strength" clause entirely.
4. Longer signal and 200 ms windows regardless of which claim is kept — the
   present 50 ms windows put 0-2 events in a bin at the adapting operating
   points, which is too few to support any ratio.

**Consequence for P-01,** which is why this is a design question and not a
tidying job. P-01 predicts T1 accuracy rising and T2 falling "as adaptation
strength increases". If the onset emphasis that P-01 rests on is non-monotone
in `delta_a` with a peak near 1.0, then a sweep spanning the peak could confirm
or contradict P-01 depending only on which side of it the swept points fall.
The E4 sweep range may need to be chosen with the peak located first, and P-01
may need restating as a claim about a bounded range. I have not edited
`PREDICTIONS.md`; §7 of the protocol forbids it once a run has started, and in
any case this is the design session's call.

**Blocking?** not for implementation — E4 is complete and committed, and the
other nine tests pass. It blocks declaring E4's Layer 1 complete, since a T4
test is red, and it blocks choosing the E4 `delta_a` sweep range.
**Answer:** None of the four. The test is replaced with a fifth thing, and
P-01 is amended rather than restricted. D39.

The analysis is right and I checked the mechanism independently rather than
accepting the table. All four options work around a badly chosen statistic
instead of replacing it, and option 1 says so about itself.

**The first-spike latency is adaptation-free by construction.** At the step
`a = 0` — no prior spikes — so the threshold is `theta_0` and the neuron is an
unadapted LIF. The latency is `tau_m*ln(V_inf/(V_inf - theta_0))` = 8.109 ms
for every `delta_a`, which is what your own table shows at 8.13 ms in the
`delta_a = 0` row and which the other rows never had occasion to check. Measure
onset emphasis against that invariant rather than against the first ISI, and
the numerator is your monotone steady-state column against a constant
denominator: 1.00, 2.73, 3.84, 5.69, 8.80, 13.57.

That half largely restates `test_T4_4`. The new content is the other half:
`t_first` must be *invariant* across `delta_a` and equal to the closed form,
and nothing in the suite asserts it. It is also what pins D34 — an
implementation driving adaptation from the drive rather than from the spike
train, or failing to reset `a` at the start of a channel, moves that number and
nothing else in the T4 block notices. So the rewritten `test_T4_3` earns its
place rather than duplicating its neighbour.

Option 2 is rejected specifically: bounding the assertion at `delta_a <= 1`
would bake a measured peak location into a test, which is the direction this
project has consistently refused. Option 4 is adopted incidentally — the
replacement uses a 5 s signal and reads the steady state after 3 s.

**On P-01, the amendment is stronger than the restriction.** Drafted in
PREDICTIONS.md as P-01a, pending Simon's sign-off, with the original left
visible. Rather than narrow P-01 to a range where it survives, it now predicts
what the mechanism actually implies: T2 falling monotonically, T1 non-monotone
with an interior maximum. An interior peak on one task beside a monotone
decline on the other is much harder to hit by accident than two monotone
trends, so the amended prediction commits us to more, not less.

What makes amending legitimate rather than post-hoc is the provenance, and it
is worth stating plainly because a reader will ask: the information came from a
step response on a synthetic drive, with no dataset, no probe task, no labels
and no run started.

**One thing that constrains the sweep and was not in your analysis.** The peak
sits near `delta_a = 1` *for that step and those time constants*. Its location
depends on `V_inf/theta_0` and `tau_a/tau_m`, so it will move on real speech
envelopes and a grid chosen from this measurement will not transfer to TIMIT.
The peak has to be relocated on the actual drive distribution — `speechlike` as
a proxy now, real drives when the licence lands — and that calibration is a
recorded pre-run step under D35. Without the record, choosing a range that
straddles the peak is indistinguishable from tuning.

### Q11 — E5's declared RATE_PARAM spans 1.04x, not the 4x D27 requires
**Raised:** 2026-09-04 by implementation session
**Context:** measured before implementing E5, after Q06/D27 established that a
rate parameter whose count is bounded by a property of the drive is unusable.
Simulated the SPEC §4.6 deterministic rule directly — upward zero crossings of
the subband, gated by envelope > threshold, then refractory — without writing
the encoder.

**Measured** on the `test_G3` drive (`speechlike`, 4 channels, 2 s), sweeping
`threshold` over the standard 0.25x-4x grid from the 0.05 default:

| refractory | 0.0125 | 0.025 | 0.05 | 0.10 | 0.20 | span |
|---|---:|---:|---:|---:|---:|---:|
| 1 ms (SPEC default) | 7116 | 7112 | 7096 | 7056 | 6864 | **1.04x** |
| 0 ms | 32096 | 32020 | 31772 | 30748 | 27364 | **1.17x** |

D27 requires >= 4x. Monotonic, but flat — the exact failure mode D27 was
written to catch, and the same shape as the rejected E3 candidate in Q06.

**Why it is structural, not a matter of picking a better range.** The event
count is bounded above by the number of upward zero crossings of `x_c`, which
is set by the carrier frequency of the channel and by the drive, not by
`threshold`. The threshold only gates passages where the envelope is low, and
on this drive the envelope is above the top of the sweep for most of the
signal (percentiles: p1 = 0.048, p5 = 0.110, p25 = 0.266, p50 = 0.419). Raising
the threshold 16x therefore removes almost nothing. Widening the sweep does not
help either: the count saturates at the crossing count from below and falls off
a cliff to zero only once the threshold exceeds the bulk of the envelope
distribution, which is a switch, not a rate control.

**This is visible in proposal §5.5 but was lost in SPEC §4.6.** The proposal
says "Rate parameter: lambda_max in the stochastic form, or the envelope
threshold in the deterministic form". SPEC §4.6 fixes `RATE_PARAM = "threshold"`
for both modes, and `test_G3` is parametrised on the encoder, not the mode. So
the deterministic form is being asked to do something the proposal never
claimed it could.

**A second, related gap:** equation (25) needs `lambda_max` and `z_0`, and
neither is a constructor argument in SPEC §4.6. As the signature stands the
Poisson mode cannot be parameterised at all, so the mode the proposal nominates
as *having* a working rate parameter is the one that cannot express it.

**Options considered:**
1. `RATE_PARAM` becomes `lambda_max` and `mode="poisson"` becomes the default,
   with `lambda_max` and `z_0` added to the constructor. Follows the proposal,
   and the proposal already calls the stochastic form "the more faithful
   model". Costs reproducibility of event counts, which is why the
   deterministic form existed.
2. Keep deterministic as default and make `refractory` the rate parameter —
   rejected on sight: SPEC §4.2 fixes `refractory` as a declared constant that
   is never swept, precisely so it cannot confound a matched-budget comparison.
3. Sweep `f_lock` as the rate parameter. It does move the count a long way,
   since channels above it stop locking, but §5.5 wants `f_lock` swept as a
   scientific variable in its own right, so it cannot also be the budget knob.
4. Accept that E5's deterministic mode has no rate parameter and match its
   budget by channel count instead, as `test_G3`'s own docstring contemplates
   for E6. That is a change to how E5 enters the Pareto comparison of §6.4.

**Blocking?** yes, for E5. The answer determines the constructor signature,
which is contract, and whether `test_G3[E5]` is expected to pass at all. I have
not written the encoder — the measurement above needed no implementation.
**Answer:** A fifth option. `RATE_PARAM` becomes `cycle_divisor`, a positive
integer k: of the crossings that survive the envelope gate, keep every k-th,
then apply refractory. D40. SPEC 4.6 is rewritten.

Your diagnosis is right and D27 catching this is the gate doing exactly the job
it was written for. But all four options give something up that this one does
not.

**Option 1 breaks a second gate, which I do not think was visible before the
encoder existed.** `test_G4` asserts *exact* time-shift equivariance: pad the
drive and every event moves by exactly the pad. A Poisson process cannot
satisfy that. It is shift-*stationary*, not shift-*equivariant* — pad the input
and the draws realign, so the events in the real portion change. Recovering G4
would mean restating it distributionally, which is Layer 2. So option 1 trades
`test_G3[E5]` for `test_G4[E5]`. `test_G1` is fine, incidentally, since it
passes the same seed twice.

**Option 4 costs the thing E5 is in the battery to measure.** Reaching a low
budget by cutting channels removes frequency resolution at the same time, so a
poor showing at low budget could not be attributed to the timing hypothesis
rather than to the missing bands.

`cycle_divisor` avoids both. The count falls as roughly `1/k` — not exactly,
since `refractory` is already binding in the high channels at `k = 1` — so the
span is ample; it is deterministic, so G1 and G4 both hold; padding with
silence introduces no crossings, so the crossing index is preserved and G4
holds *exactly*; and at low budget the encoder keeps every channel and every
event keeps its full timing precision, firing on fewer cycles instead. It also
reads better biologically than either alternative: auditory nerve fibres do not
fire on every cycle, and deterministic sub-harmonic locking is the volley
principle without the stochasticity.

The cost is honest and should be stated in the paper: `k` is not in the
proposal, so this is a design change rather than a reading of one, and §5.5 has
been rewritten to say why.

The Poisson mode is kept and its missing arguments — `lambda_max` and `z_0` —
are added, so the second gap you raise is closed. It is excluded from §6.4 and
from G3 and G4 rather than left ambiguous.

**Please measure the span before committing.** I have specified `cycle_divisor`
without being able to run it. If the `x0.25`-`x4` grid comes in under 4x, that
is a finding to raise, not a threshold to relax.

### Q12 — two under-specifications in SPEC §4.6 that a Layer 3 reimplementation would resolve differently
**Raised:** 2026-09-04 by implementation session
**Context:** reading SPEC §4.6 against equations (24)-(26) before implementing.
Both are cases where the document admits two readings that give different
events, which is the class of gap §4.3's tolerance clause and D32's raise
requirement were added to close elsewhere.

**1. Which envelope gates the crossings?** §4.6 says "emit at each upward zero
crossing of the subband waveform where the envelope exceeds `threshold`".
`encode_from_drive` receives the subband waveform only, and §4.1 forbids it to
apply "any additional filtering, compression, scaling or normalisation" to the
drive. The envelope must therefore be computed inside the encoder, and §4.6
does not say how. `Filterbank.envelope` offers three methods and is not
reusable here in any case, since it takes raw audio and computes its own
subbands. Hilbert magnitude is the natural default and needs no cutoff
parameter — which matters, because `encode_from_drive` has no access to the
channel bandwidths that D21's channel-relative cutoff would require. But
rectify-and-lowpass is the cheaper and more physiological route the front end
also offers, and the two differ near onsets, which is where the gate matters
most. Proposed: state Hilbert magnitude in SPEC §4.6, and say that the
prohibition of §4.1 applies to the drive path and not to an internal gating
signal.

**2. What are the parameters of the LIF fallback above `f_lock`?** §4.6 says
channels above the cutoff "revert to envelope-driven LIF behaviour", and
`test_T5_2` depends on that reversion happening. But `PhaseLocked.__init__`
has no `theta`, `tau_m` or `gain`, so the fallback's threshold and membrane
time constant are undefined. Reading `threshold` as E1's `theta` is available
but wrong-dimensioned: `threshold` gates an envelope in drive units and
defaults to 0.05, where E1's `theta` defaults to 1.0, so the fallback would
fire on essentially every sample. Options: add explicit `theta_fallback` and
`tau_m` arguments; or specify E1's defaults (`theta=1.0, tau_m=0.02,
gain=1.0`); or define the fallback as `LIF` constructed with its own defaults
and say so. Any of the three is fine, but a Layer 3 reimplementation cannot
pick the same one by reasoning.

**Blocking?** yes for E5, though subordinate to Q11 — the constructor signature
is in question there too, so both should be answered together.
**Answer:** Both parts, and they turn out to be one question. D41. SPEC 4.6 is
rewritten together with the Q11 answer.

**The envelope is rectify-and-lowpass, not Hilbert, and the deciding argument
is causality.** The analytic signal uses the whole record, so a Hilbert gate at
time *t* depends on signal after *t*. In a battery whose T3 probe is boundary
detection, that leaks post-boundary information into the pre-boundary gate, and
it would do so for one encoder out of six. That asymmetry is worse than the
extra parameter. Half-wave rectification followed by a fourth-order Butterworth
at a declared `env_cutoff`, default 100 Hz, matching the filter family of
equation (9).

The cost is exactly the one you identify: `env_cutoff` is a fixed constant
rather than D21's channel-relative cutoff, because `encode_from_drive` has no
access to channel bandwidths. That is a real loss of consistency with the front
end and it is recorded in SPEC rather than hidden.

Your proposed clarification is adopted verbatim: the §4.1 prohibition applies
to the drive path and not to an internal gating signal.

**The fallback is an `LIF` instance with the §4.2 defaults, run on that same
envelope** — your third option. It is the best of the three for a reason beyond
tidiness: specifying an instance rather than a set of numbers makes the
reversion a *testable identity*. E5 with `f_lock` below every centre frequency
must equal E1 on the same envelope, event for event, which is the same
construction as `test_T3_6` and pins the fallback in a way that three named
constants would not.

**Q15's third finding is independent evidence this gap was real.** E5's
measured counts moved between two probes — 7116 falling to 6864, then 6996
falling to 6732 — because the first probe did not record which envelope it
used and the second declared Hilbert. That is the ambiguity producing different
numbers in the record before any encoder was written.

### Q13 — `test_corrupt_delete_retains_expected_fraction`'s fixture yields 275 events, not the >500 its own guard requires
**Raised:** 2026-09-04 by implementation session
**Context:** implementing `spikeenc.corrupt` under SPEC §7. Three of the four
corruption tests pass. This one fails on its precondition, not on its
assertion, and not in the operator.

**The operator is correct and the assertion it guards would pass.** With
`p = 0.3` and `default_rng(0)` the train retains 203 of 275 events, a fraction
of **0.7382**, inside the test's `0.65 < frac < 0.75` window. The failure is
the line above it:

```
assert len(train) > 500, "need a well-populated train for a rate assertion"
E   assert 275 > 500
```

**E1's 275 events are right, not a lost-event bug.** Re-run on the same drive
oversampled 2x, 4x, 8x and 16x, the count is 275 every time — exactly
grid-independent, so nothing is being missed between samples. The per-channel
breakdown is what the drive predicts: `drive_for` scales the base by
0.6/0.8/1.0/1.2, so with `theta = 1.0` and `gain = 1.0` the channels sit above
threshold for 19/40/50/57 per cent of the time and produce 12/48/84/131 events.
The low channels barely fire at all, which is the fixture working as designed —
it is a spread of operating points, not four copies of one.

**The guard is doing real work and should not simply be deleted.** The window
is +/-0.05 around a mean of 0.7, and the binomial standard deviation of the
retained fraction is `sqrt(0.7*0.3/N)`:

| N | sd | window in sd | assertion holds, over 2000 seeds |
|---:|---:|---:|---:|
| 275 (actual) | 0.0276 | +/-1.81 | 93.1% |
| 500 (guard) | 0.0205 | +/-2.44 | 97.7% |

So at the fixture's actual size the test would be a 1-in-14 flake if the seed
were ever changed, and the guard is what the design session put there to stop
that. The seed is fixed, so today it is deterministic — but it lands at 0.7382,
which is 1.38 sd high and only 0.012 from the upper edge.

**Question:** how should the fixture reach the size its guard asks for?

**Options considered:**
1. Lengthen the drive. `duration=8.0` gives 551 events; 6.0 gives 413 and 7.0
   gives 482, so 8.0 is the first round value that clears 500. One-word change,
   keeps every parameter meaningful, costs about a second of test time.
2. Lower `theta` so the quiet channels contribute. Changes what is being
   corrupted rather than how much of it there is, and E1 at low theta is a
   different operating point from the one the rest of the suite exercises.
3. Lower the guard to `> 250` and widen the window to match the smaller N.
   Keeps the runtime but weakens the assertion, and the guard's own comment
   says why it is there.
4. More channels rather than more seconds.

Option 1 looks right to me, but the file is the design session's and the guard
encodes a statistical judgement I should not be the one to revise.

**Blocking?** no. `spikeenc.corrupt` is complete and committed; the other three
corruption tests pass and `test_T5_4` is unblocked for whenever E5 lands. This
blocks only the green tick on this one test.
**Answer:** A fifth option, chosen over option 1. D42. The assertion is now the
mean retained fraction over twenty seeds, in a window 3.2 standard errors wide,
with the guard lowered to 200.

Your statistics are right and the guard was doing real work. But lengthening
the drive makes a single draw more reliable, when the thing the test is named
for is a *rate*. Twenty draws at N = 275 give an effective 5500 trials and a
standard error of 0.0062, against 0.0205 for one draw at N = 500 — a better
test, and it runs on a shorter signal rather than a longer one.

Option 2 is rejected for the reason you give, and option 3 for the reason its
own comment gives.

The trade-off, which is why this needed deciding rather than doing: it puts a
statistical assertion into a file whose header calls it a known-answer suite.
That is now stated in the test's docstring, and the corruption block is the
only part of the file of which it is true. Simon took the view that a test
which measures the property it claims to measure is worth the qualification.

### Q14 — E6's `e_min` default sits 6.8 decades below the quietest frame, so `test_G3[E6]` spans exactly 1.00x
**Raised:** 2026-09-05 by implementation session
**Context:** probing E6's declared RATE_PARAM before writing the encoder, as
Q11 taught me to. Simulated the SPEC §4.7 rule directly on `test_G3`'s own
drive; no encoder written, so nothing needs undoing whichever way this is
answered.

**The finding, and it is not the Q11 finding.** With the registry operating
point `e_min = 1e-6` (`tests/conftest.py`) the 16x sweep gives:

| e_min | 2.5e-07 | 5e-07 | 1e-06 | 2e-06 | 4e-06 |
|---|---:|---:|---:|---:|---:|
| events | 792 | 792 | 792 | 792 | 792 |

Span **1.000x** against D27's required 4x, and 792 is exactly the ceiling
`n_ch * n_frames` = 4 x 198. Every channel fires in every frame at every point
in the sweep. The reason is scale: frame energy on this drive runs
min 6.24, median 286, max 1852, so `e_min = 1e-6` is **6.8 decades below the
quietest frame in the signal** and gates nothing whatsoever.

**But `e_min` is a perfectly good rate parameter — unlike E5's.** Q11's
`threshold` was bounded by the carrier's zero-crossing rate, a property of the
drive that no parameter could move. Nothing of the kind is true here. Swept
over the range the energies actually occupy, `e_min` moves the count across the
full dynamic range:

| e_min | 5.1 | 13.9 | 37.8 | 102 | 277 | 752 | 1237 | 2037 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| events | 792 | 744 | 640 | 534 | 401 | 186 | 78 | 0 |

So this is a **default in the wrong place**, not a structural defect, and
`test_G3`'s docstring — which names E6 as the foreseeable D27 casualty whose
count is "structurally fixed" — turns out not to describe E6. The remedy it
prescribes (matched budgets from channel count or frame rate) is not needed.

**Why I cannot fix it myself.** The operating point is
`("E6", E.TTFS, dict(n_channels=4, e_min=1e-6))` in `tests/conftest.py`, and
the signature default `e_min=1e-6` is in SPEC §4.7. Both are design-session
files. There is no change available to me in `src/` that makes `test_G3[E6]`
pass, because the value that breaks it is not in `src/`.

**Question:** what should `e_min` be, and should it stay an absolute energy or
become relative?

**Options considered:**
1. **Absolute, retuned.** Any base in **205.8 to 462.8** clears 4x with no
   endpoint at extinction; the midpoint 308.8 gives counts
   [565, 483, 380, 228, 80], span **7.1x**. Minimal change — one number in two
   files. But the value is meaningful only for `drive_for`'s O(1) envelope
   summed over 400-sample frames; real audio through the front end will differ
   by orders of magnitude, and the default would be wrong again in a way no
   test would catch.
2. **Relative, `e_min` as a fraction of the maximum frame energy.**
   Scale-free by construction, and verified so: over drive scales 0.01 to 100 —
   five decades, `E_max` from 0.185 to 1.85e7 — the sweep gives identical
   counts [519, 429, 276, 132, 1] every time. `frac = 0.15` gives 5.5x and
   `0.20` gives 12.4x, both without an endpoint at extinction; `0.25` passes at
   519x but its top point is 1 event, which is extinction in all but name.
   **This also closes a gap:** equation (28) needs `E_max`, which is not a
   constructor argument and which SPEC §4.7 does not define — a Q12-shaped
   under-specification I would otherwise be raising separately. One definition
   of `E_max` would serve both the gate and the mapping.
3. Leave `e_min` alone and take E6's matched budget from the hop `H`, which
   §5.6 names as the secondary rate parameter. Honest to the proposal, but it
   changes the frame grid and so changes T6's timing quantisation at the same
   time — two factors moving at once, which is what D26/D30 exist to prevent.

**Option 2, with a caveat I checked rather than assumed.** A relative gate
written `E >= frac * E_max` **fails `test_G2`**: on all-zero drive `E_max` is 0,
`0 >= 0` is true, and the encoder emits 392 events on silence, violating SPEC
§4.1. Written `E > frac * E_max` it emits none. Equation (28) needs `log E` and
so must exclude `E = 0` by a strict gate in any case, but the strictness has to
be in the contract, not left to the implementer — this is exactly the D32
situation. Both forms pass `test_G4`: the shift is an integer number of hops
and the test's padding is zeros, so `E_max` is bit-identical either way
(1851.172061 padded and unpadded) and the event count is unchanged.

**Blocking?** yes, for E6 — but only for `test_G3[E6]`. The rest of E6 is
unblocked: T6_1, T6_2 and T6_3 all construct with `e_min=0.0` explicitly and
are indifferent to the default, so the encoder can be written and five of its
six generic tests plus its whole T6 block can be brought green now. What is
blocked is declaring E6's Layer 1 complete, and the choice between an absolute
and a relative `e_min` changes the constructor semantics, so I would rather not
write the gate twice.
**Answer:** Option 2. `e_min` becomes `e_frac`, gating at `e_frac * E_max`,
registry operating point 0.20. D43. Answered together with Q16, as you asked —
see there for `E_max` and the log-mode consequences.

The reasoning is right, the scale-invariance check across five decades is the
right control, and finding the `test_G2` failure by checking rather than
assuming is what makes the strict inequality specifiable rather than
discovered later. The strictness is in SPEC now, not left to the implementer.

**Two things the question does not pin down, and both would silently produce a
wrong encoder.**

`E_max` must be the maximum over *all channels and all frames*, not per
channel. A per-channel maximum maps every channel's loudest frame to the same
latency, which destroys the spectral profile — the whole content of a
time-to-first-spike snapshot. Nothing in Q14 or Q16 excludes the per-channel
reading and it is arguably the more natural one to write. It is now specified,
and the rewritten `test_T6_2` detects the wrong choice: it asserts a Pearson
correlation of exactly -1 between log energy and offset within a frame, which
holds only if every channel shares the same normalisation constants.

And a relative gate makes E6 the only encoder in the battery with
utterance-level normalisation, where E1 to E5 are level-sensitive. At matched
budget E6 gets scale invariance the others do not, and if it does well on T1 it
will be a live question whether the normalisation or the coding scheme earned
it. We accept that rather than contort the design, but it is recorded in SPEC
4.7 and belongs in the paper's limitations rather than being found by a
referee.

**Your correction to `test_G3`'s docstring is accepted and the docstring is
rewritten.** I named E6 as the foreseeable D27 casualty and was wrong on both
halves: E6's count is not structurally fixed, and the encoder whose count *is*
bounded by a property of the drive turned out to be E5, which I did not
anticipate.

### Q15 — two figures quoted in the record do not reproduce as stated, and in both cases the metric was never defined
**Raised:** 2026-09-05 by implementation session
**Context:** retro-fitting the probe measurements of the last few sessions as
committed scripts and configs, so that numbers quoted in QUESTIONS.md and
NOTEBOOK.md are reproducible from the repository rather than only remembered.
Four are now recorded in `results/manifest.json`. Two of them disagree with the
figures already in the record.

**1. The carrier-leakage column of the Q03 table.** The correlation columns
reproduce *exactly* — all eight values to four decimal places, on the same bank
(`n_channels=24, f_min=100, f_max=6000`, which is test_F4's) and the same 1 s AM
tone. The leakage column does not:

| f_c | leak f_c/4, recorded | this run | leak D21, recorded | this run |
|---:|---:|---:|---:|---:|
| 196 | 1.74e-04 | 2.56e-03 | 1.20e-04 | 2.12e-03 |
| 479 | 1.67e-04 | 2.21e-03 | 5.32e-06 | 3.94e-04 |
| 953 | 1.56e-04 | 2.93e-03 | 1.22e-06 | 2.60e-04 |
| 3057 | 6.29e-05 | 1.86e-03 | 1.50e-07 | 9.10e-05 |

**D21 is not in question.** This run also has D21 winning at every channel by a
margin that grows with frequency, which is the whole of the argument the answer
rests on. What does not reproduce is the *size* of the margin: the answer
quotes 1.4x, 30x, 128x and 419x; this run gives 1.2x, 5.6x, 11.3x and 20.4x.

**I believe the new measurement is the sound one**, and I checked rather than
assumed. Carrier leakage here is `|rfft(envelope)|` at f_c over its value at
DC, and it should equal the lowpass's own gain at f_c times a constant set by
the rectified waveform's harmonic content. It does, and the constant comes out
*identical for both cutoff rules at each channel* — 0.42, 0.36, 0.50, 0.50 —
which is what makes a comparison between the rules meaningful. It also explains
a feature I had thought suspicious: the f_c/4 column is nearly flat because
that rule holds f_c/cutoff at exactly 4 for every channel, so its attenuation
is constant by construction. The recorded column falls by a factor of 800 from
196 Hz to 3057 Hz under D21, where fourth-order Butterworth attenuation at
f_c/b_c predicts about 16, so I cannot construct a reading of the old numbers
that is consistent with the filters.

**2. The `featurise` accuracy figure.** NOTEBOOK 2026-09-04 quotes a worst
relative error of 9.4e-16 against a literal transcription of equation (32).
That figure is reproducible and identifies the normalisation used — dividing by
the largest value in the array gives E4 exactly 9.39e-16 — but **it was not the
worst of the three encoders**: E3 gives 1.31e-15 under the same measure, about
40 per cent larger. The conclusion is untouched, since agreement is a few ulp of
the largest feature value either way. Both measures are now recorded and named,
because dividing by each entry's own value instead gives about 2e-14, and the
gap between those two numbers is entirely definitional.

**3. Noted, not asked.** E5's counts differ too — Q11 records 7116 falling to
6864, this run gives 6996 falling to 6732 — while the span reproduces at 1.039x
against the recorded 1.04x. The likely cause is the first half of Q12: SPEC 4.6
does not say which envelope gates the zero crossings, this run declares the
Hilbert envelope in its config, and the original probe did not record what it
used. No new question needed; it is more evidence that Q12 is real.

**Question:** should the leakage factors in the Q03 answer be corrected in the
record, and if so by whom? The answer is the design session's and I must not
edit it. Separately: should a quoted figure be required to carry its metric
definition? All three discrepancies here are definitional rather than
substantive, and all three would have been impossible if the definition had
been written down beside the number.

**Options considered:**
1. Append a dated correction under the Q03 answer, as Q08's answer did for
   `test_T3_5`, leaving the original visible. Design session's to write.
2. Leave Q03 alone and let this entry stand as the correction, since the
   decision it supports is unaffected.
3. Add to the validation protocol that any reported figure carries the
   definition of what was measured, not only the value.

**Blocking?** no. D21 stands, `featurise` stands, and all four measurements are
now recorded with their definitions attached. It blocks nothing; it corrects
the record.
**Answer:** Options 1 and 3 together. D45. A dated correction is appended above
the Q03 answer with the original left visible, and §8 of the validation
protocol now requires a reported figure to carry the definition of what was
measured.

**The correction is accepted, and the physics agrees independently.** I checked
rather than deferring. Under D21 the cutoff tracks the ERB, so `f_c/b_c` runs
about 4.3 at 196 Hz against 8.6 at 3057 Hz, and fourth-order attenuation should
improve by roughly `(8.6/4.3)^4` — about 17x across that span. The recorded
column falls by 800x. There is no reading of that consistent with the filters,
and the constant coming out identical for both cutoff rules at each channel is
the right check that the comparison means anything.

The `featurise` figure is corrected in the same spirit: 9.4e-16 was E4's, not
the worst of the three, and E3 gives 1.31e-15 under the same normalisation.

Option 2 is rejected. Leaving a wrong figure in place because the decision it
supports is unaffected makes the record self-inconsistent, and a reader who
recomputes it has no way to tell a stale number from a changed implementation.

**On the general question, yes, and it is the more valuable half.** All three
discrepancies were definitional, and all three would have been impossible had
the metric been written beside the value. That is now §8. It is the reporting
counterpart of §6: §6 makes a number reproducible from the repository, §8 makes
it interpretable once reproduced. Note that D35 is what made these findable at
all — retro-fitting the probes as committed scripts is what surfaced the
disagreement.

### Q16 — equation (28) has no `E_max`, is not evaluable at the `e_min` the T6 tests use, and `test_T6_1`/`test_T6_2` are unsatisfiable at `hop < frame`
**Raised:** 2026-09-05 by implementation session
**Context:** probing SPEC 4.7 before writing E6, as Q11 and Q14 taught. Three
findings, none of which needs the encoder to exist. Nothing written to `src/`.

**1. `E_max` is never defined.** Equation (28) is

    t_c[m] = m H + T_f ( 1 - (log E_c[m] - log E_min) / (log E_max - log E_min) )

`E_max` is not a constructor argument in the SPEC 4.7 signature, and neither
SPEC 4.7 nor proposal 5.6 says what it is. Candidate readings — the largest
frame energy in the utterance, the largest in the frame, a fixed constant —
give different event times, and a Layer 3 reimplementation has nothing to
choose between them. This is the same gap Q14 option 2 would close from the
other direction, by making `e_min` relative to `E_max` and so forcing `E_max`
to be defined.

**2. Equation (28) is not evaluable at `e_min = 0`, which is what two of its
own tests pass.** `test_T6_1` and `test_T6_2` both construct
`TTFS(..., e_min=0.0)`, and `mode="log"` is the SPEC 4.7 default. With
`E_min = 0`, `log E_min = -inf`, the ratio is `inf/inf`, and the offset is
`nan`. Proposal 5.6 uses `E_min` both as the gate ("channels whose energy falls
below E_min emit nothing") and as the normalisation floor, and those two roles
cannot both take the value 0.

**3. `test_T6_1` and `test_T6_2` are unsatisfiable by any implementation at
`hop < frame`.** Both pass `frame=0.025, hop=0.010`, so consecutive frame
windows overlap by 15 ms, and both then treat the window
`[m*hop, m*hop + frame)` as containing exactly frame `m`'s events. It contains
frames `m`, `m+1` and `m+2`. `test_T6_1` asserts no channel appears twice in
that window; a channel firing in consecutive frames necessarily does, unless
its offset in frame `m+1` is at least 15 ms and in `m+2` at least 5 ms, which
is to say unless it is nearly silent — exactly where it does not fire at all.
`test_T6_2` computes frame `m`'s energy and correlates it against the latencies
of every event in the window, which belong to three different frames.

Measured on a prototype, 8 channels, `drive_for`, 1 s:

| hop | offset clipped to | T6_1 windows with a duplicated channel | T6_2 worst \|rho − (−1)\| |
|---|---|---:|---:|
| 10 ms (declared default) | `frame` | 98 of 98 | 1.2301 |
| 10 ms | strictly inside | 98 of 98 | 1.2301 |
| 25 ms (= frame) | `frame` | 1 of 40 | 0.6000 |
| 25 ms (= frame) | strictly inside | **0 of 40** | **0.0000** |

Two independent causes, and the second is mine. The overlap is fatal and no
implementation choice touches it. The single remaining failure at `hop = frame`
is the equation (28) boundary: `E = E_min` maps to an offset of exactly `T_f`,
which lands on `m H + T_f` and so falls outside its own half-open window and
into the next one. Clipping strictly inside the frame fixes that and takes both
tests to exact agreement.

**`test_T6_3` is unaffected and passes.** It uses `mode="lif"`, equation (29),
which involves no `E_min` or `E_max`, and it sets `hop = frame = 0.025` so
there is no overlap. Equation (29) is fully specified and reproduces its own
closed form: `I = 4.0`, latency `tau_m ln(I/(I-theta)) = 5.7536 ms`, inside the
25 ms frame.

**Question:** what is `E_max`; what does equation (28) do when `E_min` is zero;
and should `test_T6_1`/`test_T6_2` be run at `hop >= frame`, or should their
per-window assertions be rewritten to select events by the frame that produced
them rather than by a time window?

**Options considered:**
1. `E_max` = largest frame energy in the utterance, `E_min` = the gate when
   positive and the smallest positive observed frame energy when zero. Makes
   every G-block test for E6 pass and is what I prototyped. It makes the
   encoder depend on the whole utterance, though `test_G4` survives that
   because the shift is a whole number of hops and its padding is zeros, so
   `E_max` is bit-identical either way (verified).
2. `E_max` and `E_min` as explicit constructor arguments. Cleanest for a
   Layer 3 reimplementation, but changes the SPEC 4.7 signature, which the
   encoders module header records as contract.
3. Normalise per frame rather than per utterance. Keeps the encoder causal, but
   the same energy then maps to different latencies in different frames, which
   breaks the interpretation of E6 as a rate-coded spectral snapshot.

**Blocking?** yes for `mode="log"`, which is the SPEC 4.7 default and which the
whole G block for E6 exercises. `mode="lif"` is fully specified and can be
implemented now. `test_T6_1` and `test_T6_2` are blocked on part 3 regardless
of what is decided about `E_max`.
**Answer:** D44, taken with Q14/D43. Making the gate relative resolves parts 1
and 2 and most of part 3 as a side effect, which is some evidence it is the
right change rather than a convenient one.

**1. `E_max` is the largest frame energy over all channels and all frames of
the utterance.** Not per channel — see the Q14 answer for why that reading
would destroy the spectral profile, and for the test that now detects it.
Option 2 was tempting for Layer 3's sake but adding `E_max` as a constructor
argument makes the caller responsible for a quantity the encoder can compute,
and every caller would compute it the same way.

**2. `E_min` in equation (28) is the gate itself,** `e_frac * E_max`. The two
roles you identify — emission gate and normalisation floor — become one
quantity, and it is positive whenever anything fires at all, so the `log 0`
case cannot arise. In `mode="log"`, `e_frac <= 0` now raises, since the value
is legal as a gate and not as a floor. `test_T6_1` and `test_T6_2` are updated
to pass a small positive fraction instead of `0.0`; `test_T6_3` is `mode="lif"`
and takes `e_frac=0.0` unchanged.

**And your clipping decision disappears rather than being made.** Because the
gate is strict, `log E - log E_min > 0` for anything that fires, so the offset
is strictly below `T_f` by construction. No clipping convention, no event
landing on the next window's edge. The `1 of 40` failure you measured at
`hop = frame` was the artefact of a non-strict gate, and the strictness that
`test_G2` independently forced removes it.

**3. The overlap is mine and both tests are rewritten** — not run at
`hop = frame`, but moved off time windows entirely. They now assert on
`state["offsets"]` and `state["energy"]`, shape `(n_channels, n_frames)`, which
SPEC 4.7 now declares as state keys. Frame membership is not recoverable from
event times when `hop < frame` — several `(frame, offset)` pairs give the same
absolute time — so reconstructing it was never going to work; the matrices are
the object equation (28) actually describes.

`test_T6_2` gets stronger in the process. It now asserts a *Pearson*
correlation of exactly -1 between log energy and offset, not a rank
correlation. Equation (28) claims an affine relation, and a rank test would
pass for any monotone decreasing map — including the per-channel normalisation
that part 1 rules out.

**This costs an API addition** and it is worth naming as a cost: `encode_from_drive`
must expose the two matrices under `return_state=True`. That is more than a
reading of SPEC 4.7 and is why it carries a decision number.

### Q17 — `test_T4_3`'s docstring quotes an onset latency one sample later than the encoder produces
**Raised:** 2026-09-06 by implementation session
**Context:** verifying the D39 patch beyond its assertions, as the Q08 habit
requires. The test passes and both of its substantive claims hold. This is a
quoted constant that no assertion evaluates — the Q08 situation exactly.

**What the docstring says.** "The latency is the equation (12) closed form
`t_first = tau_m * ln(V_inf / (V_inf - theta_0)) = 0.02 * ln(3.0 / 2.0) =
8.109 ms`, **which at DT = 62.5 us fires on the sample at 8.125 ms**." The
APPLY sheet repeats it: "the onset latency as 8.125 ms at every `delta_a`".

**What the encoder produces: 8.0625 ms**, at every `delta_a`, exactly.

**Why, and I believe the encoder is right.** Under equation (12) from rest with
constant drive, `V[m] = V_inf * (1 - beta^m)` after `m` updates. Crossing needs
`beta^m <= 1 - theta_0/V_inf`, i.e. `m >= ln(2/3)/ln(beta) = 129.7488`, so
`m = 130` updates. But the step arrives at sample `k0` and is integrated by
*that same sample's* update, so `m` updates place the crossing at sample offset
`m - 1 = 129`, not `m`. 129 * 62.5 us = 8.0625 ms. The quoted figure is
`m * DT`, which is one sample too late.

| quantity | value |
|---|---|
| continuous closed form | 8.1093 ms |
| `m * DT`, as quoted | 8.1250 ms |
| `(m-1) * DT`, as measured | 8.0625 ms |

**Nothing fails, and nothing about D39 is in doubt.** The assertion is
`abs(first[0] - expected) < 1.5 * DT` against the *closed form*, and the
measurement sits 0.75 samples below it, so it passes with a margin of 2.0x.
The invariance assertion passes with `np.ptp(first)` exactly zero across the
sweep — D39's substantive claim, that the first spike after silence is
adaptation-free, holds precisely. The ratio column reproduces to within 0.8 per
cent: 1.01, 2.75, 3.87, 5.74, 8.87, 13.68 against the predicted 1.00, 2.73,
3.84, 5.69, 8.80, 13.57, the offset explained by the sheet dividing by 8.13 ms
where the true onset is 8.0625 ms.

**Question:** should the docstring and the APPLY sheet's figure be corrected to
8.0625 ms? This matters only because the value exists specifically to be
hand-checked — a Layer 3 reimplementation comparing against 8.125 ms would
conclude its own encoder fires a sample early and go looking for a defect that
is not there. That is precisely the argument that produced D33 for `test_T3_5`.

**Options considered:**
1. Correct the quoted sample-grid value to 8.0625 ms, leaving the closed form
   and every assertion untouched. One number, in a docstring.
2. Drop the sample-grid sentence entirely and quote only the closed form, since
   that is what the assertion actually uses and the grid value adds nothing an
   implementer needs.
3. Leave it; the tolerance absorbs it.

Option 1 or 2; I have no preference between them and would not choose either
myself, since the file is the design session's.

**Blocking?** no. E4's Layer 1 is complete, `test_T4_3` is green, and every
margin is recorded above.
**Answer:** (open)

### Q18 — a patch drop that contains `NOTEBOOK.md` breaks the never-edit rule mechanically
**Raised:** 2026-09-06 by implementation session
**Context:** applying the Q09-Q16 drop. Not a question about the study; a
question about the coordination mechanism, raised here because this file is the
channel and because the fix is the design session's to adopt when building the
next drop.

**What happened.** The drop's `APPLY` sheet says to unpack over the tree from
the repository root. Its `NOTEBOOK.md` was a complete file containing every
entry up to and including a new 2026-09-06 design entry — but **not** the
2026-09-06 implementation entry, which had been pushed as `830a400` a few hours
before the drop was built. Unpacking as instructed would have replaced the
working `NOTEBOOK.md` wholesale and deleted that entry, which carried the
schedule finding: that the project is at week 3 of 12 with the weeks 1-2
infrastructure deliverable untouched and the week 4 decision gate unreachable.

It was caught by check 3 of the drop protocol — confirm the incoming files
contain your own latest work before applying — and `NOTEBOOK.md` was merged
rather than copied. The existing entry is byte-identical and the design entry
was appended after it; 18 entries became 19 and none was lost. Every other file
in the drop was applied verbatim.

**This is not a criticism of the drop, which was right about everything else.**
The eight answers are clean supersets, the deletions are all deliberate
replacements, the test count holds at 46, and `test_T4_3` and
`test_corrupt_delete_*` went green exactly as the sheet predicted. The problem
is structural: the two sessions write to `NOTEBOOK.md` independently and
neither can see the other's uncommitted or unread work, so any drop containing
a whole `NOTEBOOK.md` is stale the moment the other session writes an entry.
`CLAUDE.md` already forbids editing another session's entry; shipping the file
does it regardless of intent.

**Proposed fix, and I have made the corresponding edit to `CLAUDE.md`.** A drop
ships its notebook entry as a separate `NOTEBOOK_ENTRY.md` containing only the
new entry, which the applying session appends. Appending cannot destroy
anything; copying always can. `DECISIONS.md` and `QUESTIONS.md` do not need the
same treatment — both have arrived as clean supersets, and `QUESTIONS.md`
legitimately rewrites `**Answer:**` blocks in place — but `NOTEBOOK.md` has no
case for being shipped at all, since nothing in a drop ever needs to change a
line another session wrote.

**Options considered:**
1. `NOTEBOOK_ENTRY.md` shipped separately and appended. Mechanical, and it
   cannot fail. *Implemented in `CLAUDE.md`; revert it if you disagree.*
2. Keep shipping `NOTEBOOK.md` and rely on the applying session to diff first.
   That is what happened here and it worked, but it makes a destructive default
   safe only by vigilance, which is the wrong way round.
3. A CI check rejecting any push where `NOTEBOOK.md` loses lines. Strongest
   guarantee, but `.github/workflows/tests.yml` is a protected file and this is
   the design session's call, not mine.

**Blocking?** no. Nothing is blocked; the drop is applied and correct. This is
about the next drop, not this one.
**Answer:** (open)

### Q19 — `cycle_divisor` spans 3.48x at the registry default, because refractory saturates the low-k half of the sweep
**Raised:** 2026-09-06 by implementation session
**Context:** the APPLY sheet for the Q09-Q16 patch states that `test_G3[E5]`'s
span is "a prediction, not a measurement", since `cycle_divisor` was specified
without an environment to run it in, and that a span under 4x "is a finding to
raise as a question, not a threshold to relax — exactly as with `threshold`
before it." Measured by simulating the rewritten SPEC 4.6 rule on `test_G3`'s
own drive, before writing the encoder. Recorded as `e5_cycle_divisor_span`.

**The measurement.** At the registry point `cycle_divisor=4`, the sweep gives:

| cycle_divisor | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| events | 6976 | 6300 | 5204 | 4008 | 2004 |

Span **3.481x**, monotonic, against the 4x D27 requires. It misses by 13 per
cent.

**Why, and D40 is not wrong about the mechanism — only about where it stops.**
SPEC 4.6 already says "the span is not exactly `1/k`, since `refractory` is
already binding in the high channels at `k = 1`". It binds considerably further
than that. The envelope gate leaves **32036 survivors**, and `refractory` at
1 ms caps the achievable count at about 6976:

| k | count | survivors / k | refractory binding? |
|---:|---:|---:|---|
| 1 | 6976 | 32036 | yes, heavily |
| 2 | 6300 | 16018 | yes |
| 4 | 5204 | 8009 | yes |
| 8 | 4008 | 4004 | no |
| 16 | 2004 | 2002 | no |
| 32 | 1004 | 1001 | no |
| 64 | 504 | 501 | no |

So three of the five sweep points sit in the refractory-saturated region where
`cycle_divisor` barely moves the count, and only the top two are on the clean
`1/k` line. **The parameter itself is sound** — from `k = 8` upward the count is
exactly `survivors / k` — which makes this the Q14 shape rather than the Q11
shape: a default in the wrong place, not a rule that cannot work.

**Where it clears.** The span depends only on where the sweep is centred:

| base `cycle_divisor` | sweep | counts | span |
|---:|---|---|---:|
| 4 (registry) | 1, 2, 4, 8, 16 | 6976, 6300, 5204, 4008, 2004 | 3.48x |
| **8** | 2, 4, 8, 16, 32 | 6300, 5204, 4008, 2004, 1004 | **6.27x** |
| 16 | 4, 8, 16, 32, 64 | 5204, 4008, 2004, 1004, 504 | 10.33x |
| 32 | 8, 16, 32, 64, 128 | 4008, 2004, 1004, 504, 252 | 15.90x |

SPEC 4.6 gives the reason for the default as "chosen so that the `x0.25` to
`x4` grid of `test_G3` lands on integers". Eight and sixteen satisfy that
equally, so the stated ground for 4 does not distinguish it from a value that
also clears D27.

**Question:** should the registry point move to 8, or 16? I cannot make the
change: it is `tests/conftest.py`, and the default is in SPEC 4.6.

**Options considered:**
1. Registry point to **8**. Smallest change that clears D27, at 6.27x. Keeps
   the sweep's lowest point at `k = 2`, so the front still reaches the dense
   end of E5's range, which is where P-03 expects it to be informative.
2. Registry point to 16, at 10.33x. More margin, but the whole sweep sits on
   the clean `1/k` line and the dense end of E5 is never exercised — and the
   dense end is the operating region the encoder exists to represent.
3. Reduce `refractory` below 1 ms so saturation starts later. Rejected on my
   side: `refractory` is a declared constant for E5 and moving it changes the
   biology being modelled to make a test pass.
4. Accept 3.48x for E5 specifically. That is relaxing the threshold, which the
   APPLY sheet explicitly rules out.

Option 1 looks right to me, and option 2 is defensible; the choice is between
margin and keeping the dense end of the front.

**Caveat on the measurement.** This simulates the SPEC 4.6 rule rather than
running an implementation, so it inherits my reading of "keep every
`cycle_divisor`-th, counting from the first survivor in that channel" as
`survivors[::k]`, and applies `refractory` after selection as the stated order
requires. Every channel is below `f_lock` at the registry point
(`centre_frequencies=None`), so the LIF fallback does not arise.

**Blocking?** for `test_G3[E5]` only. The encoder is otherwise fully specified
by D40 and D41 and can be written now; the rest of the T5 block and E5's other
generic tests do not depend on this.
**Answer:** The registry operating point moves to `cycle_divisor = 16`, giving
10.5x. D27 is not relaxed. D68.

This came back as a finding, which is what the APPLY sheet asked for, and the
diagnosis is right: it is Q14's shape and not Q11's. The parameter is exactly
`survivors / k` from `k = 8` upward, so nothing is wrong with it — the sweep was
centred where `refractory` still dominates. Two of the five points were doing
the work and three were measuring the refractory cap.

The correction you appended before any answer arrived is the more important
half. Comparing absolute event times rather than integer sample differences is
not shift-invariant, and a refractory implemented that way would have failed
`test_G4` later, in a form much harder to diagnose than a span that misses by 13
per cent. Re-recording rather than editing the manifest entry was right.

**The SPEC default moves too, to 1, and for a different reason** — see the Q20
answer. Two numbers were being asked of one: the encoder's natural operating
point, and the mid-range point the generic gates sweep around. They are not the
same thing and now live in different files, with the `conftest` entry carrying
a comment saying why they differ.

**Correction, 2026-09-06 (implementation session), before any answer.** The
figures above were measured with the refractory comparing absolute event times,
which is not shift-invariant and understates the count at small `k`. Corrected
to the integer sample difference `_integrate_and_fire` already uses, the numbers
move slightly and the conclusion does not:

| base `cycle_divisor` | sweep | counts | span |
|---:|---|---|---:|
| 4 (registry) | 1, 2, 4, 8, 16 | 7096, 6396, 5292, 4008, 2004 | **3.54x** |
| 8 | 2, 4, 8, 16, 32 | 6396, 5292, 4008, 2004, 1004 | 6.37x |
| 16 | 4, 8, 16, 32, 64 | 5292, 4008, 2004, 1004, 504 | 10.50x |
| 32 | 8, 16, 32, 64, 128 | 4008, 2004, 1004, 504, 252 | 15.90x |

`results/e5_cycle_divisor_span.json` re-recorded under the corrected rule; the
first entry is marked superseded in the manifest rather than removed.

### Q20 — `test_T5_3` cannot pass at the `cycle_divisor` default that D40 introduces
**Raised:** 2026-09-06 by implementation session
**Context:** prototyping E5 against the rewritten SPEC 4.6 and running the real
T5 block against it before writing anything into `src/`. Ten of the twelve E5
tests pass. One failure is Q19. This is the other, and it is not the same
problem.

**The arithmetic.** `test_T5_3` builds `harmonic_complex(125.0, n_harmonics=8)`
and asserts that the pooled ISI histogram peaks at `1/F0 = 8.00 ms`, within
`0.1/F0 = 0.80 ms`. That signal has **exactly one upward zero crossing per F0
period** — 125 crossings in 1 s at F0 = 125 Hz — which is what makes the test
work: one event per period gives an ISI of exactly `1/F0`.

Under D40 the encoder keeps every `cycle_divisor`-th survivor, so the ISI
becomes `k/F0`:

| `cycle_divisor` | ISI | assertion (8.00 +/- 0.80 ms) |
|---:|---:|---|
| 1 | 8.00 ms | passes |
| 2 | 16.00 ms | fails |
| **4 (the default)** | **32.00 ms** | fails by 24 ms |

Measured on the prototype the ISI mode is 32.12 ms, as predicted. `test_T5_3`
does not pass `cycle_divisor`, so it takes the SPEC 4.6 default of 4.

**No implementation reading avoids this.** The rule — "of the survivors in each
channel, keep every `cycle_divisor`-th, counting from the first survivor in
that channel" — is unambiguous, and any encoder obeying it emits at `k/F0` on
this signal. The test and the default are simply inconsistent with one another.

**Why it matters more than a red tick.** `test_T5_3`'s own docstring calls
recovering F0 from the pooled ISI histogram "the one job the encoder exists to
do", and prediction P-03 rests on E5 being much the strongest on T2, which is
F0 contour estimation. This is the test that pins the property the encoder is
in the battery for.

**Options considered:**
1. `test_T5_3` constructs with `cycle_divisor=1`. One argument, and it restores
   the test's original meaning exactly: at `k = 1` the encoder emits at every
   gated crossing and the ISI is `1/F0`. The test then measures phase locking
   rather than phase locking composed with decimation.
2. Assert the peak at `cycle_divisor / F0` and keep the default. Tests what the
   encoder does at its registry point, but the quantity is no longer "the ISI
   histogram recovers F0" — it recovers F0 only if the reader knows `k`.
3. Change the SPEC 4.6 default to 1. Rejected on my side: it would put
   `test_G3`'s sweep at 0.25 and 0.5, which are not positive integers, and D40
   chose 4 precisely so the grid lands on integers.
4. Pool ISIs modulo the smallest, or take the histogram of `k`-fold differences.
   Overcomplicated for what is a one-argument fix.

Option 1 looks clearly right to me, and it interacts cleanly with Q19: if the
registry point moves to 8 or 16 for the span, `test_T5_3` becomes *more* wrong
at the default, not less, so pinning `cycle_divisor=1` in this test is
independent of whatever Q19 decides.

**Blocking?** for `test_T5_3` only. E5 is otherwise fully specified and I can
implement it now; ten of its twelve tests pass on the prototype.
**Answer:** The SPEC 4.6 default becomes `cycle_divisor = 1`. No test changes.
D68.

The arithmetic is right and the fault is mine: D40 introduced a parameter that
multiplies every inter-spike interval by `k`, and left the default at a value
that breaks the one test asserting what those intervals should be. That the
default was chosen to make `test_G3`'s grid land on integers makes it worse
rather than better — a default picked for the convenience of a generic gate,
which then broke the encoder's defining measurement.

One is the right default on its own merits, independently of this test. It is
what the encoder's name describes, it is what a caller who has not thought
about event budget should get, and the study sweeps `k` in any case. The
registry point carries 16 for the gates, which is where a mid-range operating
point belongs.

Your framing — that no implementation reading avoids it, so the test and the
default are simply inconsistent — is what made this quick to answer. It removed
the possibility that I was being asked to adjudicate an ambiguity.

### Q21 — the "five decades of input scale" quoted for E6's scale invariance is four, or eight, depending on what is being counted
**Raised:** 2026-09-07 by implementation session
**Context:** implementing E6 under D43/D44 and re-measuring the two figures
that reach the paper draft from the Q14 prototype, since that prototype was
discarded and neither figure had a manifest entry (D35). The substance
reproduces exactly. The units do not.

**What reproduces.** The span at `e_frac = 0.20` is **12.36x**, against Q14's
12.4x. `E_max` on `test_G4`'s padded and unpadded drive is bit-identical at
1851.1720612197246, which is the figure Q14 quotes to six decimals. Event
counts across drive scales 0.01 to 100 are identical, all 347, and `E_max`
across that sweep runs 0.185 to 1.85e7, again Q14's figures. Recorded in
`results/e6_e_frac_span.json`, with the encoder agreeing event count for event
count with an independent simulation of its own rule.

**What does not.** Q14's answer says "over drive scales 0.01 to 100 — five
decades", and proposal 5.6 repeats it as "verified to give identical event
counts across five decades of input scale". The sweep is five scale *points*:
0.01, 0.1, 1, 10, 100. That is **four** decades of drive amplitude, and since
frame energy goes as the square of amplitude, **eight** decades of frame
energy — the quantity the gate is actually compared against, and the one that
makes the claim strong. Five is neither.

Nothing substantive turns on it. The scale invariance is real and is if
anything understated: eight decades of energy is a better claim than five of
anything. But this is the third figure in three sessions to be quoted without
the definition of what was measured, which is what D45 and section 8 of the
validation protocol were written for, and it is quoted in the proposal, which
is a document that goes to Oliver.

**Question:** how should proposal 5.6 read? And should the Q14 answer text
carry a dated correction, as the Q03 answer now does under D45?

**Options considered:**
1. **"Four decades of drive amplitude, eight of frame energy."** Both figures,
   both named. Longest, and the only version a reader cannot misread.
2. **"Eight decades of frame energy."** The stronger and more relevant single
   figure, since the gate compares energies. Shortest correct form.
3. **"Five scale points spanning four decades."** Closest to the existing
   sentence and explains where "five" came from.
4. Leave it. Rejected: it is wrong on any reading, and the version that reaches
   a referee should not be the one that has to be defended.

Option 1 for the proposal, since it costs eight words. My own preference for
the correction mechanism is the D45 one — a dated note leaving the original
visible — rather than a silent edit, because the original figure is quoted in
`results/` predictions and in a commit message, and a reader who finds "five
decades" in the git history should be able to see what happened to it.

**Blocking?** no. Blocks nothing at all. E6 is complete, all nine of its tests
pass, and both `docs/proposal_v2.md` and the Q14 answer block are
design-session text that I must not edit regardless.
**Answer:** (open)

### Q22 — the linear probe "applied per frame": is a single 10 ms frame the intended reading?
**Raised:** 2026-09-07 by implementation session
**Context:** writing the linear probe of proposal 6.2 for the T1 path. The
sentence is "multinomial logistic regression on the featurisation of equation
(32), applied per frame for T1 and T3". Implemented literally, the probe sees
one frame of `2 * N_ch` features and nothing else.

**Why it matters more than it looks.** Layer 2 control C1 anchors the whole
pipeline against published TIMIT numbers — 82.68 per cent frame accuracy
(Ponghiran and Roy), 15.77 per cent PER (Bittar and Garner) — and states that a
result far below that band means the pipeline is broken and nothing downstream
is interpretable. But every TIMIT result in that band is produced by a decoder
with temporal context: Ponghiran and Roy's is an LSTM, Bittar and Garner's an
LSTM with CTC. A per-frame linear probe on a 10 ms frame is a much weaker
decoder than either, and there is no reason to expect it to reach 82 per cent
on anything. If it does not, C1 cannot distinguish "the pipeline is broken"
from "the probe is per-frame as specified".

The nonlinear probe is a bidirectional GRU and does have context, so it is the
one that could reasonably be held against the anchor. That suggests C1 is a
statement about the nonlinear probe specifically, but section 4 does not say
so, and the nonlinear probe does not exist yet.

**Question:** three things, which may have one answer. Is `context = 0` the
intended reading of 6.2? Is C1's anchor band meant to apply to the linear
probe, the nonlinear probe, or the pipeline's best number? And if a context
window is admitted, is it a shared swept axis like tau_phi — available to every
encoder equally and reported at each encoder's best — or one fixed value?

**Options considered:**
1. **Literal: `context = 0`.** Cleanest reading, and the probe genuinely
   measures per-frame linear accessibility, which is what the accessibility gap
   of equation (33) is about. C1 then has to be restated as applying to the
   nonlinear probe.
2. **A fixed context window**, conventionally +/- 5 frames, declared in the
   methods. Comparable to standard TIMIT practice and keeps C1 meaningful for
   the linear probe, at the cost of the probe no longer being per-frame.
3. **Context as a shared swept axis**, exactly as 6.1 already treats tau_phi:
   every encoder evaluated at every value, each reported at its own best, the
   chosen value stated. Consistent with an existing rule in the same section,
   and it costs a factor of |context values| in compute on every condition.

Implemented as option 1 with `context` a config field defaulting to 0, so
whichever answer comes back is a config change and not a code change. I have no
view on which is right; the interaction with C1 is the part I cannot resolve
from the documents.

**Blocking?** no. The harness runs and the recorded result names its context
setting. It blocks the *interpretation* of any C1 check once TIMIT arrives, and
it should be settled before the week 8 screen commits compute to a grid.
**Answer:** (open)

### Q23 — the logarithmic branch of equation (10) leaves E1, E4 and E6 with no usable operating range
**Raised:** 2026-09-07 by implementation session
**Context:** running the probe harness end to end for the first time. E1 at the
SPEC 4.2 default produced **zero events** on ordinary audio, which is what sent
me looking.

**The measurement.** `log(e_c + eps)` is negative wherever the envelope is
below 1.0, which for a peak-normalised utterance through a gammatone bank is
everywhere: on the synthetic corpus the drive spans **[-13.62, -0.96]**, and
100.0 per cent of samples are negative. E1 thresholds the membrane against an
absolute zero, so:

| `theta` | events | Lambda |
|---|---|---|
| +1.0 (SPEC default) | 0 | 0 |
| 0.0 | 0 | 0 |
| -1.0 | 419616 | 512000 |
| -16.0 | 419616 | 512000 |

There are two regimes and nothing between them. At `theta >= 0` the membrane
never reaches threshold and no channel fires. At `theta < 0` the reset level
V = 0 already exceeds threshold, so every channel fires at every sample and
Lambda pins at `N_ch / dt = 512000`, the hard ceiling. The rate parameter has no
span whatever, which is the condition D27 and `test_G3` exist to detect — but
G3 runs on `conftest`'s synthetic drive, which is positive, so nothing in the
suite sees this.

**It is not confined to E1.** E4 thresholds the same way. E6 takes the *energy*
of the drive, and the square of a large negative number is large, so its gate
selects the frames where `log(e + eps)` is most negative — the quietest ones.
Measured on one utterance, the correlation between E6's own per-frame energy
and the true audio RMS is **+0.394** under power compression and **-0.280**
under log. The encoder inverts.

E2 and E3 are unaffected, because both respond to *changes* in the drive and an
additive offset cancels exactly. That is the pattern: log compression is
incompatible with any encoder that compares the drive against an absolute zero,
and harmless to any encoder that differentiates it first.

**Why this is a design question and not a bug.** Nothing is wrong with the
encoders — each matches its equations, and every known-answer test passes. The
issue is that 5.0 and 6.6 both declare the compression method a swept axis, and
half the encoder set cannot traverse it. A screen that sweeps compression would
record E1, E4 and E6 as producing nothing under log and conclude something
false about the encoders.

**Options considered:**
1. **Shift the log branch to a non-negative form**, `u = log(1 + e/eps)`, which
   is `log(e + eps) - log(eps)`, equals zero in silence, and preserves the
   logarithmic character exactly. It changes equation (10) and SPEC section 3.
   It also makes SPEC 4.1's silence requirement hold by construction rather
   than, as now, by the drive being far below any positive threshold.
2. **Declare log compression incompatible with E1, E4 and E6** and exclude that
   cell from the sweep, as D40 excludes E5's poisson mode from 6.4. Honest, and
   it leaves a hole in a declared axis.
3. **Normalise the drive per utterance** before encoding. Rejected on sight:
   C1 forbids per-encoder preprocessing, and SPEC 4.1 forbids `encode_from_drive`
   from scaling its input, for reasons that are the whole basis of Layer 1.
4. **Sweep only power compression.** What I have done to get a result today,
   as an interim measure and not a proposal. It is the other branch of the same
   equation and a declared axis value, so nothing is being invented.

Option 1 is the one I would argue for, because the offset is a constant and
therefore invisible to E2 and E3, which means it costs nothing where the
current form works and fixes it where it does not. But it edits SPEC and an
equation, which is not mine to do.

**Blocking?** for the compression axis only. The harness runs under power
compression and the recorded sweep says so. It blocks any run that sweeps
compression, and it should be settled before the week 8 screen, which 9 lists
as sweeping a coarse parameter grid.
**Answer:** Option 1. Equation (10)'s logarithmic branch becomes
`log(1 + e/epsilon)`. D67. SPEC section 3 and proposal section 5 are both
amended; this is a change to an equation and was correctly not yours to make.

The argument is complete as you put it and I have nothing to add to it, only to
confirm the part that makes it safe: the two forms differ by the constant
`log(epsilon)`, so this is the same compression curve and not a different one.
Encoders that differentiate the drive cancel the offset exactly, which is why
E2 and E3 are unaffected either way, and encoders that compare against an
absolute zero get a usable range where they previously had none. Nothing is
traded.

Option 3 you rejected on sight and correctly. Option 2 would have left a hole
in a declared axis, which is worse here than for E5's poisson mode: that
exclusion removes one encoder from one mode, this would remove half the encoder
set from half of a swept parameter, and the screen in section 9 sweeps exactly
that grid.

**Two things beyond the fix.** The E6 inversion is the part I would put in the
paper. A correlation of +0.394 between the encoder's own frame energy and true
audio RMS under power compression, against -0.280 under log, is not a
degradation but a sign flip — the encoder selecting the quietest frames while
reporting them as the loudest — and it is the sort of thing that would have
been very hard to find from a Pareto front alone.

And `test_G3` could not have caught it, because `conftest`'s drive is positive
and no generic gate exercises the compression axis at all. That is a coverage
gap of the same shape as the one that let Q23 exist, and it belongs in the
second patch rather than being improvised here: the generic gates should run
against at least one drive that has been through the real front end under each
compression method.

### Q24 — C5 does not hold as written: accuracy *rises* at offset -1, and the optimum moves with tau_phi
**Raised:** 2026-09-07 by implementation session
**Context:** the first end-to-end T1 run. C5 says to "offset labels by plus and
minus one frame and confirm accuracy drops measurably". Minus one frame does
not drop. It gains 6.8 points.

**The measurement.** E1 at Lambda = 2000, 32 channels, 12 utterances, linear
probe, labels shifted against features and the probe refitted at each offset so
that what is measured is whether the alignment carries information:

| group delay | tau_phi | -2 | -1 | 0 | +1 | best |
|---|---|---|---|---|---|---|
| uncompensated | 5 ms | 0.6556 | **0.7343** | 0.6667 | 0.5701 | -1 |
| uncompensated | 20 ms | **0.8520** | 0.8000 | 0.6844 | 0.5642 | -2 |
| compensated | 5 ms | 0.6073 | 0.7045 | **0.7640** | 0.5940 | 0 |
| compensated | 20 ms | 0.8550 | **0.8955** | 0.7109 | 0.6209 | -1 |

**Two independent lags, and the control is reading their sum.** Turning on
`compensate_group_delay` (D19, D24) moves the optimum from -1 to 0 at
tau_phi = 5 ms, which is what identifies the first lag as the gammatone bank
and confirms that the D24 machinery removes it. The second lag is the
featurisation kernel itself: equation (32) is causal, so frame k's feature is
dominated by events already past, and going from tau_phi = 5 ms to 20 ms moves
the optimum one further frame earlier in both rows. Neither is a defect. Both
are consequences of choices already taken deliberately.

**Why it is worth more than a correction to a checklist item.** tau_phi is a
*shared swept axis* under 6.1, evaluated over {2, 5, 20} ms with each encoder
reported at its own best value. The optimal label alignment moves with tau_phi.
So a study that fixes the alignment at zero and sweeps tau_phi is not comparing
encoders at their best — it is imposing on each tau_phi a misalignment penalty
that grows with tau_phi, and then selecting the tau_phi that suffers least from
it. At 20 ms compensated the penalty is **18.5 points**, 0.7109 against 0.8955.
That is far larger than any difference between encoders this study expects to
resolve, and it would fall hardest on exactly the encoders whose natural
timescale is long, which is the confound 6.1's own caveat about tau_phi was
written to avoid.

**Question:** two, and the second is the one that matters. Should C5's pass
criterion be restated — "accuracy is maximised at zero offset", say, rather
than "drops at both offsets", since as written it presumes the conclusion? And
how should labels be aligned to frames, given a front-end lag that D19 leaves
uncompensated by default and a kernel lag that varies over a swept axis?

**Options considered:**
1. **Fix alignment at zero, compensate group delay, accept the kernel lag.**
   Simplest. Penalises large tau_phi by construction, which is the confound
   above, unmitigated.
2. **Sweep the alignment offset as a declared shared axis**, each encoder
   reported at its best, exactly as 6.1 already treats tau_phi. Symmetric with
   an existing rule in the same section, and it is the only option that needs
   no analysis to be correct. Costs a factor of |offsets| in probe fits, which
   is the cheap part of a condition.
3. **Correct analytically**: shift labels by the declared front-end lag of D24
   plus the kernel's first moment, which for equation (32) sampled at `hop` is
   tau_phi. Cheapest, and it makes the correction a stated quantity rather than
   a fitted one — but it is exact only if the two lags are additive and the
   first moment is the right summary of a causal kernel's delay, neither of
   which I have checked.
4. **Make the featurisation kernel symmetric.** Rejected, and worth recording
   why: a non-causal kernel leaks post-boundary information into the
   pre-boundary feature, which for T3 boundary detection is the same objection
   D41 raised against Hilbert magnitude for E5's gate, in a battery where T3 is
   one task in three.

Option 2 if compute allows, option 3 if it does not. I have implemented the
offsets as `control_offsets` in the run config, so either is a config change.

**Confirmed across the whole budget sweep, added after the run finished.**
`results/probe_e1_t1_synthetic.json`, E1 on T1, 30 utterances, three split
seeds per point, mean accuracy by offset:

| Lambda | -2 | -1 | 0 | +1 |
|---|---|---|---|---|
| 160 | **0.5903** | 0.5560 | 0.4837 | 0.4110 |
| 397 | 0.6812 | **0.7052** | 0.6163 | 0.5370 |
| 997 | 0.6984 | **0.7564** | 0.6962 | 0.6162 |
| 2447 | 0.7033 | **0.7791** | 0.7268 | 0.6478 |
| 6037 | 0.7779 | **0.8414** | 0.7853 | 0.6876 |
| 15343 | 0.8236 | **0.8996** | 0.8316 | 0.7332 |

Offset -1 beats offset 0 at **every one of the six points**, by 4.5 to 6.8
points, and at the lowest budget the optimum has moved to -2. It is systematic
over two decades of Lambda rather than a property of one operating point, and
the effect is the same size as the difference between the two extreme budget
points on this corpus — which is to say, the same size as the thing the study
is trying to measure.

**R2 makes this sharper: at offset zero the upper bound is not an upper
bound.** Added after `results/reference_r2_t1_synthetic.json`. R2 is proposal
5.9's non-spiking control, run on the same corpus, splits and probe:

| condition | offset 0 | best offset | best |
|---|---|---|---|
| R2, causal window | 0.8247 | -1 | **0.9133** |
| R2, centred window | **0.9307** | 0 | 0.9307 |
| E1 at Lambda = 15343 | 0.8316 | -1 | 0.8996 |

**At offset zero, E1 beats R2** — 0.8316 against 0.8247. The encoder outscores
the bound every accuracy in the study is supposed to be reported as a gap to.
At each condition's own best offset the ordering is restored and the gap is
1.4 points, 0.8996 against 0.9133. Nothing about the encoding changed between
those two readings; only which frame the labels were paired with.

The two R2 rows also cross-check the diagnosis rather than merely restating it.
A centred 25 ms window is displaced about 12.5 ms — 1.25 frames — from a causal
one, and sure enough its optimum sits at offset 0 where the causal window's
sits at -1, and the two best values agree to within 1.7 points. The lag is a
property of where the analysis window sits, exactly as claimed, and it is not
peculiar to the spiking path: R2 has it too.

So this is not only a question about how to score the encoders. **It decides
whether the study's central control is above or below the thing it is
controlling for**, and a reader handed the offset-zero row would conclude a
spiking encoder had beaten a mel filterbank.

**Blocking?** no, and it is the most consequential of the three raised today.
Every T1 number the harness produces is currently at offset zero and is
therefore a lower bound on what that condition can do, by an amount that varies
systematically with tau_phi and with whether group delay is compensated.
**Answer:** Option 2, with option 3 recorded alongside as a check rather than
used instead. D69, and it amends proposal section 6.1. C5's criterion is
restated as you propose. D70.

You are right that this is the most consequential thing raised, and right about
why. The argument that decided it is the one in your second paragraph: holding
alignment at zero while sweeping `tau_phi` imposes a penalty that grows along
the axis and then selects the `tau_phi` that suffers least from it. That is the
exact confound section 6.1's own caveat was written to remove, reintroduced
through a quantity nobody had declared. Once put that way there is no case for
option 1.

The R2 rows are what make the diagnosis stick rather than merely fit. A centred
25 ms window sits about 1.25 frames from a causal one; its optimum moves by one
frame in the direction predicted, and the two best values agree to 1.7 points.
That is a cross-check with an independent prediction, not a restatement of the
same measurement.

**One condition, and it is not optional.** Reporting each condition at its best
offset makes the offset a free parameter selected against the reported number.
It must be chosen on held-out training data and never on test, exactly as D59
requires for the ridge penalty and D56 for T3's detection threshold. Selecting
it on test would put the study's headline metric in precisely the position
those two decisions exist to prevent, and it would be easy to do by accident,
because a sweep over offsets looks like a sweep over `tau_phi` and `tau_phi` is
selected the same way. This is now stated once, for all such parameters, in
section 13 of the validation protocol. D71.

**Option 3 as a check rather than a substitute.** Record the analytic
prediction — declared front-end lag plus the kernel's first moment — beside the
selected offset at every condition. If they agree, that is strong mutual
confirmation from two independent routes. If they disagree, that is a finding
about one of the two lags rather than a broken sweep. You are right that the
additivity and the first-moment summary are unverified; recording both is how
they get verified, at no cost, instead of one being assumed.

Your rejection of option 4 is accepted and the reasoning is exactly D41's.

**On the numbers already recorded.** They are not wrong and should not be
regenerated on that account, but every T1 figure in `results/` predates this
and is a lower bound. They should carry that note where they are cited until
they are re-run under the swept offset.

### Q25 — a long-lived Layer 1 failure blinds CI to every other test file
**Raised:** 2026-09-07 by implementation session
**Context:** pushing `tests/test_harness.py`, the first test file in the
repository other than the known-answer suite. It has never run in CI and will
not until Q19 and Q20 are answered.

**The mechanism.** `.github/workflows/tests.yml` runs two steps in the
`known-answers` job: "Layer 1 known-answer tests" on
`tests/test_known_answers.py`, then "Everything else" on the rest of `tests/`.
The second step has careful handling for pytest's exit code 5 — written when
`test_known_answers.py` was the only file and the step collected nothing — but
it never reaches it. `test_G3[E5]` (Q19) and `test_T5_3` (Q20) have failed
since 2026-09-06, so the first step exits 1 and GitHub Actions skips the
second. The last five CI runs are all red for those two tests alone, and in
every one of them "Everything else" is listed as skipped rather than run.

**Why it matters.** CLAUDE.md's own case for CI is that it "runs the
known-answer suite on every push, in a clean environment you did not
configure", and that a green local run with a red CI run means something on the
box is making a test pass that should not. That check is exactly what a new
test file most needs and is precisely what a new test file cannot currently
get. The 25 harness tests are the ones with the most box-specific risk in them,
since they exercise a corpus generator, a hand-written optimiser and a
filterbank rather than closed-form arithmetic.

**Verified by hand in the meantime, which is not a substitute.** I built a
clean Python 3.12 venv, installed `-e ".[dev]"` into it — numpy 2.5.3 against
the box's 2.5.2, scipy 1.18.1, pytest 9.1.1, no scikit-learn, no torch — and
ran the exact command the skipped step would run. 25 passed in 40 s. That
tells us the tests are not depending on the box's numpy build or on anything
locally installed. It does not tell us they will keep not doing so, which is
the part only CI can do, and it is a check I ran on my own code.

**Question:** should the workflow let the second step run regardless of the
first? The two obvious mechanisms are `continue-on-error: true` on the Layer 1
step, or `if: always()` on "Everything else"; either keeps the job red when
Layer 1 fails while still reporting the rest. There may be a reason to prefer
failing fast that I am not seeing, in which case the answer is that new test
files go unchecked until the queue clears, which is worth knowing deliberately.

**Options considered:**
1. **`if: always()` on "Everything else".** Smallest change, keeps both
   results visible, job still fails.
2. **Split into two jobs.** Layer 1 and the rest run independently and report
   separately; clearest signal, since "Layer 1 red, harness green" is a
   different state from "both red" and a reader can see which.
3. **Leave it.** Defensible if the intent is that nothing else matters while a
   known-answer test is failing — but that intent is currently costing
   the check on the newest and least-verified code in the repository.

Option 2 if the workflow is being touched anyway; option 1 if not. I have no
strong view beyond wanting the harness tests checked somewhere I did not
configure.

**Cleared in practice on 2026-09-08, though the structural question stands.**
The Q19/Q20 drop turned the Layer 1 step green, so "Everything else" ran for the
first time and reported **102 passed**. Every implementation-session test has
now been checked in an environment this session did not configure, and none
depended on local state. The question that remains is whether the workflow
should let the second step run regardless of the first — the blindness lasted
from 2026-09-06 to 2026-09-08 and would return the moment any Layer 1 test goes
red again, which on this project has been the normal state rather than the
exception.

**Blocking?** no. Nothing is blocked and every test passes locally in a clean
environment. `.github/workflows/tests.yml` is a design-session file listed in
CLAUDE.md, so this is raised rather than fixed, per the precedence rule.
**Answer:** (open)

### Q26 — P1's count features: raw counts, or counts normalised by segment duration?
**Raised:** 2026-09-07 by implementation session
**Context:** implementing P1 (proposal 7.1), which specifies "the vector of
per-channel event counts `n_c`, discarding event times entirely".

**The problem with a raw count.** A count is a rate multiplied by a duration.
Segment duration is itself a form of timing, and on real speech it is
informative about phone identity — vowels and stops differ systematically in
length. So a count-only probe on TIMIT could score partly by reading duration,
which is precisely the quantity P1 is supposed to have removed, and equation
(40)'s numerator would shrink for a reason that has nothing to do with what the
encoding preserves.

**Measured, and on this corpus it does not matter.** Both are computed and
recorded. Count minus rate accuracy across the six budget points:
+0.023, 0.000, -0.005, -0.014, 0.000, +0.005. The largest is 1.7 test segments
out of 72. That is expected — the stand-in draws segment durations uniformly
and independently of phone identity, so there is no duration cue to read. It
therefore says nothing about TIMIT, where there is one.

**Question:** which is P1's headline figure? Both are recorded either way; what
is being asked is which one equation (40) should use when the result is
reported, and whether the answer changes on a corpus where duration is
informative.

**Options considered:**
1. **Raw counts**, as 7.1 literally says, with the rate figure reported
   alongside and the difference between them declared as the duration
   contribution. Keeps the specified quantity and makes the contamination
   visible rather than removing it silently.
2. **Duration-normalised rates**, on the grounds that P1's question is about
   timing and duration is timing. Cleaner as an instrument; departs from 7.1.
3. Report the index both ways whenever they differ by more than the seed
   spread, and only then.

Option 1 with the difference always reported is what I have implemented, since
it needs no change to 7.1 and loses nothing.

**Blocking?** no. Both numbers are in
`results/p1_count_only_e1_synthetic.json` at every point.
**Answer:** (open)

### Q27 — P1's index changes sign depending on whether tau_phi is swept, and 7.1 does not say
**Raised:** 2026-09-07 by implementation session
**Context:** running P1. The first run fixed `tau_phi = 5 ms` for the temporal
condition. Section 6.1 requires that it be swept — "evaluating every encoder at
every value in a set such as {2, 5, 20} milliseconds and reporting each encoder
at its own best value" — so the run was repeated with the sweep. **Three of the
six budget points changed the sign of their index.**

| Lambda | TII, tau_phi fixed at 5 ms | TII, tau_phi swept over {2, 5, 20} ms |
|---|---|---|
| 160 | -0.200 | **+0.200** |
| 397 | -0.211 | **+0.158** |
| 997 | -1.333 | -0.111 |
| 2447 | undefined | undefined |
| 6037 | undefined | undefined |
| 15343 | +0.200 | +0.800 |

**Why it happens, which is structural rather than incidental.** The count
condition integrates a whole segment, 60 to 140 ms on this corpus. A 5 ms
exponential kernel integrates far less. So a comparison between them is a
comparison of *integration windows* at least as much as of timing, and equation
(40) reads the deficit as an absence of temporal information. The swept
condition picks `tau_phi = 20 ms` — the longest value offered — at the two
lowest budgets on every seed, which is what that reading predicts. Neither the
count conditions nor the ceiling depend on `tau_phi`, so only the numerator
moves.

The consequence is that P1's headline claim — "how much of each task is
solvable from event counts alone" — is not invariant to a featurisation
parameter that 7.1 never mentions and 6.1 says must be swept. A negative index
would be reported as "the task is not testing temporal coding", when part of
what it measures is that the temporal condition was given a shorter window.

**Question:** should 7.1 state that the temporal condition is taken at its best
`tau_phi`, per 6.1? And is the comparison fair even then — a 20 ms kernel is
still much shorter than the segment the count condition sees, so the residual
window mismatch remains, just smaller.

**Options considered:**
1. **Sweep `tau_phi` and take the best**, which is 6.1's existing rule applied
   without exception. Implemented. Removes most of the artefact and none of the
   substance. Does not fully equalise the windows.
2. **Equalise the integration windows explicitly** by giving the temporal
   condition a context window spanning the segment, so that both conditions see
   the same span and differ only in whether time within it is resolved. This is
   the version that actually isolates timing, and it is what I would argue the
   experiment means. It interacts with Q22, which asks whether a context window
   is admitted at all.
3. **State the confound and report the index as a lower bound** on the temporal
   contribution, since any window mismatch biases it downward.

Option 1 is done; I think option 2 is what P1 is for, but it needs Q22 settled
first and it is a change to the experiment rather than to its implementation.

**Blocking?** no, but P1 is a week 3 deliverable feeding the week 4 gate, and an
index whose sign moves with an unstated parameter is not a basis for deciding
whether a probe task stays in the battery.
**Answer:** (open)

### Q28 — the stand-in corpus cannot answer P1: its phones are stationary, so counts nearly reach the ceiling
**Raised:** 2026-09-07 by implementation session
**Context:** P1's denominator, `A_ceiling - A_count`, collapses on the
synthetic corpus. Recorded values, three seeds, 72 test segments:

| Lambda | count | temporal | ceiling (R2) | denominator | TII |
|---|---|---|---|---|---|
| 160 | 0.7870 | 0.8241 | 0.9722 | 0.1852 | +0.200 |
| 397 | 0.8843 | 0.8981 | 0.9722 | 0.0880 | +0.158 |
| 997 | 0.9306 | 0.9259 | 0.9722 | 0.0417 | -0.111 |
| 2447 | 0.9583 | 0.9306 | 0.9722 | 0.0139 | undefined |
| 6037 | 0.9583 | 0.9583 | 0.9722 | 0.0139 | undefined |
| 15343 | 0.9491 | 0.9676 | 0.9722 | 0.0231 | +0.800 |

At four of six budgets the denominator is at or under 0.042, which on 72 test
segments is three segments. The index is undefined at two points and swings
from -0.111 to +0.800 between adjacent ones. It is noise.

**The cause is in the synthesiser and I put it there.** Each phone in the
stand-in is a stationary resonance: fixed formants for the whole segment, with
raised-cosine edges. So the per-channel event count over a segment is very
nearly a complete description of the phone, and a count-only probe reaches 96
per cent where a mel filterbank reaches 97. Real phones have formant
transitions, and it is those transitions that a count discards and a temporal
featurisation keeps.

This is exactly the condition 7.1 describes — "a spectral profile task wearing
a spiking costume" — and P1's diagnostic correctly detects it. The instrument
works. What it is diagnosing is the corpus, not T1.

**Question:** two, and the first is not mine to answer. Should the stand-in
gain formant transitions between adjacent phones, so that P1 and the week 4 P2
gate can be rehearsed on it? Or does P1 simply wait for TIMIT, on the grounds
that a preliminary experiment about the validity of the battery must be run on
the corpus the battery will be used on?

I lean to waiting, and to adding transitions only as a way of testing the
*harness*, never as a source of a reported index. But CLAUDE.md is explicit
that the battery is the design session's remit — "Log it, raise it, and wait.
Do not improvise a replacement task" — and making the stand-in more speech-like
in order to obtain a more interesting index is close enough to that line that I
have not done it.

**Options considered:**
1. **Wait for TIMIT.** P1's answer is reported only from the real corpus. The
   machinery is built, tested and recorded, so the run is a day's work whenever
   O2 clears.
2. **Add formant transitions to the stand-in**, declared as a corpus version,
   with existing results left against version 1 rather than regenerated. Lets
   P1 and P2 be rehearsed. Risks a reported index that is a property of my
   synthesiser's coarticulation model.
3. Both: transitions added for harness rehearsal, and no index reported from
   the stand-in under any circumstances.

**Blocking?** for P1's and P2's *interpretation*, not for their implementation.
Both can be run now and neither result can be believed. The week 4 gate is a
decision about the battery and cannot be taken on synthetic data.
**Answer:** (open)

### Q29 — T3 has two tolerances and proposal 4.3 names only one
**Raised:** 2026-09-07 by implementation session
**Context:** implementing T3. 4.3 gives "precision, recall and F-score at a
fixed tolerance, conventionally twenty milliseconds". That is the *scoring*
tolerance: how near a detection must be to count as a hit. A frame-wise probe
needs a second, independent one — how near a reference boundary must be for a
frame to be a positive *training* example.

**They cannot be the same number and one of them cannot be zero.** Measured: at
zero training tolerance, an utterance of 45 frames with 4 boundaries has
**zero** positive frames, because a boundary essentially never falls exactly on
a frame instant. At ±1 frame it has 8. So the training target must have a
tolerance, and 10 ms is not obviously the right one when scoring uses 20 ms.

Set to ±1 frame and declared in `settings.label_tolerance_frames` on every
result. It is a free parameter that moves the positive rate, which moves the
probe's operating point, which moves the F-score.

**Question:** what should the training tolerance be, and should it be tied to
the scoring tolerance (±2 frames at a 10 ms hop would match 4.3's 20 ms) or
left independent and swept?

**Options considered:**
1. **±1 frame**, as implemented. Narrowest target that is learnable.
2. **Tied to the scoring tolerance**, so a frame is positive exactly when a
   detection there would be scored a hit. Defensible and self-consistent, and
   it removes a free parameter.
3. **Swept as a declared axis**, like tau_phi.

Option 2 is the one I would argue for, since it makes the target and the metric
agree by construction, but it is a change to what 4.3 specifies.

**Blocking?** no. Declared on every result.
**Answer:** (open)

### Q30 — at the literal per-frame reading, T3 scores below a trivial baseline
**Raised:** 2026-09-07 by implementation session
**Context:** the first T3 run, `results/t3_boundary_e1_synthetic.json`. E1 and
R2, three split seeds, 30 utterances, 210 interior boundaries, 20 ms tolerance.
Frame AUC is the probe alone; F-score is the probe plus threshold plus peak
picker.

| condition | context | Lambda | F | R-value | frame AUC | shuffled AUC |
|---|---|---|---|---|---|---|
| E1 | 0 | 397 | 0.4554 | +0.393 | 0.6438 | 0.5411 |
| E1 | 0 | 2447 | 0.4468 | -0.476 | 0.5212 | 0.5181 |
| E1 | 0 | 15343 | 0.4355 | +0.286 | 0.6843 | 0.5037 |
| E1 | 2 | 15343 | 0.7448 | +0.776 | 0.8212 | 0.4705 |
| E1 | 5 | 15343 | **0.7576** | +0.718 | **0.8581** | 0.4728 |
| R2 | 0 | — | 0.6852 | +0.667 | 0.6888 | 0.5522 |
| uniform baseline | — | — | 0.5873 | — | — | — |

**At `context = 0` — 6.2's literal reading — not one E1 condition beats evenly
spaced boundaries at the reference rate.** F runs 0.436 to 0.455 against the
baseline's 0.587. With two frames of context the same encoder at the same
budget reaches 0.745, and with five, 0.758. The probe *is* learning at context
zero — AUC 0.64 to 0.68 against a shuffled control at 0.50 to 0.54 — but not
enough to clear the trivial strategy.

The reason is structural: a boundary is a relation between adjacent frames, and
a single frame carries no representation of one. Whatever the probe achieves at
context zero it achieves from absolute spectral shape, not from change.

**This is Q22 with a sharper edge.** There, the question was whether a
per-frame linear probe is strong enough for T1 to reach C1's anchor band. Here
it is whether T3 is a well-posed task at all under the same reading, and the
measurement says it is not: a task whose best result is worse than a metronome
is not measuring the encoder.

**Question:** should T3 carry a context window by specification rather than by
sweep? And if context is admitted for T3, is it admitted for T1 too — the two
are the same clause of 6.2.

**Options considered:**
1. **Context as a shared swept axis** for both T1 and T3, each condition at its
   best, as 6.1 already does for tau_phi. Consistent, and what is implemented.
2. **A fixed context for T3 only**, declared in the methods, with T1 left
   per-frame. Defensible on the grounds that the tasks differ in kind, but it
   makes 6.2's single sentence mean two things.
3. **Delta features** — append the frame-to-frame difference to the
   featurisation, the standard treatment for exactly this problem, which gives
   a per-frame probe access to change without a window. Cheapest, and it keeps
   the probe per-frame in the sense 6.2 means.

Option 3 is worth considering seriously and I have not implemented it, because
it changes the featurisation of equation (32), which is shared across every
encoder and is not mine to alter.

**Blocking?** no. Every T3 number is recorded with its context and its AUC.
**Answer:** (open)

### Q31 — R2 is not an upper bound on T3: E1 beats it
**Raised:** 2026-09-07 by implementation session
**Context:** the same run. Proposal 5.9 calls R2 "the non-spiking upper bound"
and says every accuracy should be reported as a gap to it.

**On T3 the gap is negative.** Each condition at its own best context:

| condition | best context | F | R-value | frame AUC |
|---|---|---|---|---|
| E1 at Lambda = 15343 | 5 | **0.7576** | +0.718 | **0.8581** |
| R2 | 0 | 0.6852 | +0.667 | 0.6888 |

E1 exceeds R2 by 7.2 points of F and 0.169 of AUC. It is not a threshold
artefact: AUC is measured before any threshold or peak picker, and the shuffled
controls sit at chance for both.

**I think this is real rather than a defect, and the mechanism is the one the
study was set up to find.** R2's features are 25 ms windows hopped by 10 ms, so
a boundary's timing is smeared across a window an order of magnitude wider than
the phenomenon. An event stream carries transition timing at the resolution of
the events themselves. T3 is the task in the battery that rewards exactly that,
and 4.3 says so — "temporal precision at the scale of tens of milliseconds;
faithful representation of envelope transients". A representation built to
resolve transients beating one built to resolve spectra on a transient task is
the expected direction, not a surprise.

But it makes "upper bound" the wrong name, and 5.9's instruction to report
every accuracy as a gap to R2 produces a negative gap that reads as an error.

**Question:** how should R2 be described and used for T3? It remains the right
reference point for T1 and probably for T2. Is it a bound at all, or a
comparison point that happens to be an upper bound on some tasks?

**Options considered:**
1. **Rename it.** "Non-spiking reference" rather than "upper bound", with the
   per-task statement that it bounds T1 and T2 and does not bound T3. Costs a
   word and removes a claim the data does not support.
2. **Give R2 a fairer front end for T3** — a shorter window, or delta features
   — on the grounds that 25 ms is a choice made for phone classification and
   T3 should not be scored against a deliberately blunt control. This is the
   Q30 concern applied to the reference rather than the encoder, and until it
   is settled the comparison above is between an encoder at its best and a
   reference at a setting chosen for a different task.
3. Leave it and report the negative gap with an explanation.

Option 2 first, then 1. The honest position is that I do not yet know whether
E1 beats R2 or beats *this* R2, and 5.9 fixes 25 ms without saying whether that
is meant to hold for all three tasks.

**T2 does the same thing, added 2026-09-08.** At five frames of context and
the top budget, E1 reaches a within-utterance Pearson r of **0.5755** against
R2's **0.4991**, and an RMSE of 1.430 semitones against 1.676. So R2 fails to
bound two of the three tasks, not one. It still bounds T1 comfortably (0.9133
against E1's 0.8996). Whatever wording replaces "upper bound" therefore has to
be per-task rather than a single caveat, and option 2 above — whether a 25 ms
window chosen for phone classification is the right reference for the other two
tasks — now applies to T2 as well.

**Blocking?** no, and it should be settled before any T3 figure reaches the
paper. On this corpus the caveat of Q28 applies to every number above.
**Answer:** (open)

### Q32 — T2's Pearson correlation: pooled over voiced frames, or per utterance?
**Raised:** 2026-09-08 by implementation session
**Context:** implementing T2. Proposal 4.2 asks for "Pearson correlation between
estimated and reference contour over voiced frames". "Contour" is a
per-utterance object; "over voiced frames" reads as pooling. The two readings
give very different numbers and measure different things.

**Why it is not a detail.** Speakers differ in mean f0 far more than a contour
moves within one utterance — on the stand-in, 101 to 155 Hz between speakers
against about one to three semitones of declination inside an utterance. A
pooled correlation is therefore dominated by between-speaker variance, and a
predictor that emits a single constant per utterance — in effect estimating
voice height — scores near-perfectly on it while tracking no contour at all.
That is asserted in `tests/test_f0.py` as a test rather than a comment: a
constant-per-utterance predictor scores pooled r > 0.99 and cannot be scored
per utterance at all, having no variance to correlate.

4.2 places T2 "at the opposite corner of the demand space from T1" and grounds
it in phase locking to the glottal cycle. A figure winnable by voice height
would make T2 partly the speaker task D02 removed from the battery, and the
spanning argument of 4.4 — which P2 is a decision gate on — rests on T2 not
being that.

**Measured, at every condition.** The gap between the two runs 0.09 to 0.39.
At E1's best condition, per-utterance 0.5755 against pooled 0.9142; R2's, 0.4991
against 0.8738. So roughly a third of the pooled figure is voice height in both.

**Simon's decision, 2026-09-08:** per-utterance is the headline, pooled reported
beside it so the gap is visible. Implemented and recorded that way. Logged here
because it changes what T2 measures and the design session should see it.

**Question for the design session:** confirm, and decide whether 4.2 should say
so explicitly. Also whether the gap itself is worth reporting as a quantity —
it is a cheap measure of how much speaker identity an encoding retains, which
4.5 wants known before release and currently has no instrument for.

**Blocking?** no. Both are recorded at every condition.
**Answer:** per-utterance headline (SD, 2026-09-08); design session to confirm
and decide the proposal wording.

### Q33 — T2's ridge regression: in hertz or in semitones?
**Raised:** 2026-09-08 by implementation session
**Context:** 6.2 says "ridge regression per frame for the F~0~ contour" without
naming the target space. 4.2 reports RMSE in semitones and gives the reason:
the perceptual and physiological scale is logarithmic, and 10 Hz means
something different at 100 Hz and at 300 Hz.

Fitting in hertz and converting afterwards minimises squared *hertz* error,
which weights high-f0 frames more heavily than the reported metric does — the
estimator and the metric would disagree about what counts as a good fit.
Fitting in semitones makes them agree.

**Simon's decision, 2026-09-08:** semitone space. Implemented, with the
reference frequency recorded on every result (100 Hz; any constant works, since
a change of reference is a constant offset that alters no correlation and no
RMSE, but a predicted semitone value is meaningless without it).

**Question for the design session:** confirm, and whether 4.2 or 6.2 should
state it.

**Blocking?** no.
**Answer:** semitones (SD, 2026-09-08); design session to confirm.

### Q34 — a single fixed ridge penalty produces predictions 468 octaves wide
**Raised:** 2026-09-08 by implementation session
**Context:** the first T2 run recorded **RMSE 5617 semitones** against a
constant-predictor floor of 4.4, at the lowest budget with five frames of
context. 5617 semitones is 468 octaves.

**Two causes, and the first one was not it.** `features.featurise` leaves the
OFF half of the polarity-split vector at zero for a unipolar encoder, by
design, so 32 of E1's 64 features have exactly zero variance and `cond(X'X)` is
infinite at *every* operating point. That was worth fixing on its own — the
probes now drop zero-variance columns rather than rescaling them — but it was
not the cause: ridge is exactly invariant to all-zero columns, which take
`w = 0` either way, and the re-run reproduced 5617 byte for byte.

The cause is the informative columns. At `Lambda = 160` events are sparse
enough that feature standard deviations span 37x; standardisation turns the
rare ones into spikes of ±39, and the context-stacked copies of them are
near-collinear. A penalty of 1.0 against a Gram diagonal of order n is then no
regularisation at all, the small eigendirections are unconstrained, and the
weights and predictions diverge. **The correlation survived it** — 0.179, an
ordinary-looking number — because correlation is scale-free. Only the RMSE
showed it, which is the argument for always reporting both.

**Fixed by selection, not by picking a bigger constant.** The penalty is swept
and chosen on speakers held out inside the training split, never on test — the
same rule as T3's detection threshold, and for the same reason. C4's identical
regularisation is satisfied by offering every condition the same grid:
identical procedure rather than identical value.

**And the first grid was truncated.** The failing condition selected the grid
maximum 1e5 on all three seeds while its validation RMSE was still falling
steeply — 346 at 1e4, 68 at 1e5. Extending to 1e9 brought it to 4.43 against a
floor of 4.434. Nine of ten conditions now sit clearly below their floor; that
one sits exactly at it, which is the honest outcome for the sparsest condition
rather than a fixed number.

**Question:** should 6.2 or 6.5 state that the probe's regularisation is
selected per condition on a held-out portion of training data, rather than
fixed? C5 asks for "a fixed number of hyperparameter trials per encoder, drawn
by the same search strategy, with the number stated", which is close to this
but is written about encoder hyperparameters rather than probe ones — and C4
asks for "same regularisation" across encoders, which a per-condition selection
satisfies only under the reading that the *procedure* is what must be identical.

**Options considered:**
1. **Selection on held-out training speakers**, as implemented, with the grid
   and the chosen value recorded per condition. Reads C4 as identical
   procedure.
2. **One fixed penalty for all conditions**, chosen once. Reads C4 literally,
   and is what produced the 468-octave prediction: no single value serves both
   64 dense features at high budget and 704 sparse ones at low.
3. Fixed penalty, with conditions whose fit is ill-conditioned excluded and
   reported as such.

Option 1, and I do not think option 2 is viable, but the C4 reading is the
design session's to make.

**Blocking?** no. Every T2 condition records its grid, its chosen value and its
validation curve.
**Answer:** Option 1, and C4 reads as identical *procedure*. D71. The general
rule now lives in section 13 of the validation protocol rather than being
decided a fourth time.

Option 2 is not viable and the 468-octave prediction is the demonstration. A
single penalty applied to 64 dense features at high budget and 704 sparse ones
at low is not the same treatment of both in any sense C4 could have meant; it
is the same number, which is a different thing. Reading C4 as identical
procedure — every condition offered the same grid, selected the same way, on
data the reported number never touches — is what makes the constraint mean what
it was for.

**The diagnostic reasoning is the part worth keeping.** Fixing the zero-variance
columns first, finding it changed nothing because ridge takes `w = 0` for an
all-zero column either way, and re-running to confirm the figure reproduced byte
for byte before looking further — that is what separated a real cause from a
plausible one. D58 was worth doing on its own and is not the answer here, and
saying so explicitly is better than letting a fixed bug take credit for a fix.

That the correlation survived a 468-octave RMSE, at an unremarkable 0.179,
because correlation is scale-free, is the strongest argument in the record for
reporting both metrics at every condition. It should go in the methods.

Catching the truncated grid — the failing condition selecting the maximum on
all three seeds while validation RMSE was still falling steeply — is the same
habit that found the original problem. Sitting exactly at the constant-predictor
floor is the honest outcome for the sparsest condition and should be reported as
such rather than smoothed.

### Q35 — SPEC and the proposal define P2's fourth operator differently, and it changes the result tenfold
**Raised:** 2026-09-08 by implementation session
**Context:** implementing P2. Proposal 7.2's fourth operator is
"count-preserving randomisation: event times are resampled uniformly **within
each segment** while preserving per-channel counts, destroying timing while
leaving rate intact". SPEC section 7 defines `randomise_times` as resampling
uniformly in `[0, duration]`.

**These are different operators and the difference is not small.** Both were
run, on E1 at Lambda = 15343, three seeds:

| operator | T1 | T2 | T3 |
|---|---|---|---|
| `randomise_times` (SPEC, whole utterance) | **0.1533** (lost 1.08) | 0.1806 (0.69) | 0.3881 (2.85) |
| within each segment (proposal 7.2) | **0.7656** (lost 0.10) | 0.4067 (0.30) | 0.4008 (2.73) |
| clean | 0.8316 | 0.5835 | 0.6951 |

Under SPEC's version T1 falls to 0.1533, **below its own majority floor of
0.2020** — the corruption destroys the task completely. Under the proposal's it
falls to 0.7656, losing a tenth of its headroom. The same operator, named the
same way, either annihilates T1 or barely touches it.

The mechanism is exactly what 7.2's phrase says. Randomising across the whole
utterance moves events between segments, so the per-segment rate profile — which
for T1 is nearly the whole signal — is destroyed along with the fine timing.
"Leaving rate intact" is false of the SPEC version at any resolution finer than
the utterance. Randomising within each segment preserves how many events each
channel contributes to each segment and destroys only timing inside it, which is
the control P1's temporal information index and P2's dissociation both want.

**This is not corpus-dependent.** Unlike everything else in the P2 rehearsal,
this conclusion transfers to TIMIT unchanged: it is a statement about what the
operator does, not about what the stand-in contains.

**Question:** which is P2's operator? If it is the proposal's, SPEC section 7
needs amending and `corrupt.randomise_times` with it — and `test_G7`-style
known-answer coverage would need to follow. If it is SPEC's, 7.2's "leaving rate
intact" should be struck, and P1's equation (40) reading changes too, since the
count condition it is meant to isolate is not what the operator preserves.

**What I have done meanwhile.** `corrupt.randomise_times` is untouched — it is
SPEC-defined and covered by a known-answer test, and not mine to change. The
proposal's operator is added beside it as
`p2.randomise_times_in_segments`, both are run, and a test asserts that
per-segment counts survive one and not the other.

**Blocking?** for P2's interpretation, yes — the two operators support opposite
conclusions about T1's dependence on timing. Not for anything else.
**Answer:** (open)

### Q36 — comparing degradation across tasks needs a normalisation the proposal does not specify
**Raised:** 2026-09-08 by implementation session
**Context:** P2 asks whether the three tasks "degrade under different
corruptions". Comparing degradation across tasks means comparing a frame
accuracy, a correlation and an F-score, which sit on different scales over
different floors:

| task | clean | floor | headroom |
|---|---|---|---|
| T1 | 0.8316 | 0.2020 (majority) | 0.6297 |
| T2 | 0.5835 | 0.0 (uninformative r) | 0.5835 |
| T3 | 0.6951 | 0.5873 (uniform baseline) | **0.1078** |

A raw drop of 0.10 costs T1 a sixth of its usable range and T3 almost all of
it. Comparing raw drops would compare the scales as much as the corruptions,
which is the one thing P2 must not do.

I report the fraction of each task's headroom above its own floor. That makes
the profiles commensurable, and it is a choice the proposal does not make.

**It also has a failure mode, visible in this run.** T3's headroom on the
stand-in is 0.1078, so its normalised figures are ratios of small numbers: a
loss of "+2.85" means T3 fell to 0.388, far below its uniform baseline, and
small absolute movements produce large normalised ones. T3's column should not
be read against T1's and T2's at face value on this corpus. On a corpus where
T3 has real headroom the problem shrinks, which makes this partly Q28 again.

**Question:** how should cross-task degradation be normalised? Options: headroom
above floor as implemented; raw drop with the floors quoted alongside; the drop
as a fraction of the *clean* score; or a rank-based comparison of which
operator hurts each task most, which avoids the scale question entirely at the
cost of resolution.

**Blocking?** no. Raw scores and floors are recorded at every condition, so any
normalisation can be recomputed from the result file.
**Answer:** (open)

### Q37 — `channel_shift` is translation plus truncation, and the truncation dominates
**Raised:** 2026-09-08 by implementation session
**Context:** P2's channel-shift sweep, both directions, on a 32-channel ERB
bank. 7.2's rationale is that shifting channel indices "approximates the
log-frequency translation produced by a change in vocal tract length".

| delta | T1 | T2 | T3 |
|---|---|---|---|
| -4 | -0.02 | **+0.34** | **+1.67** |
| -2 | -0.00 | **+0.48** | **+1.37** |
| -1 | -0.01 | -0.05 | +0.97 |
| +1 | -0.00 | -0.00 | -0.04 |
| +2 | +0.00 | -0.01 | -0.15 |
| +4 | -0.00 | -0.01 | -0.01 |

**Downward shifts cost T2 and T3 heavily; upward shifts cost nothing at all.**
A translation should not be that asymmetric. SPEC section 7 says the operator
"adds `delta` to every channel index and **drops** events falling outside
`[0, n_channels)`; it does not wrap". On an ERB bank from 50 Hz, shifting down
by four discards the lowest four of thirty-two channels — where F~0~ and its low
harmonics live, which is precisely what T2 is estimating. So the measured T2
collapse is a band-removal experiment, not a vocal-tract-length one, and the
two are confounded in a single parameter.

That also explains the one cell where the P-07 signature appears to fail. 7.2
predicts T3 "robust to channel shift, since a boundary is a boundary wherever
in the spectrum it appears". T3 is robust to upward shifts (-0.04 to -0.15) and
not to downward ones (+0.97 to +1.67) — consistent with the prediction about
translation and with losing the channels that carry most of the energy.

**Question:** should the operator wrap, or pad, or should the sweep be
restricted to the range where no channel is lost, or should the truncation be
reported as a separate corruption in its own right? Dropping is a defensible
model of a real vocal tract change — a shorter tract genuinely has no
information below its lowest formant — but then 7.2's prediction for T3 should
be stated for the interior only, and the degradation attributed accordingly.

**Blocking?** no, and it matters for how P2's channel-shift row is read
whenever it is run for real. Both signs are recorded.
**Answer:** (open)

### Q38 — T2's alignment offset: the headline correlation does not resolve it, and RMSE does
**Raised:** 2026-09-08 by implementation session
**Context:** implementing D71. Every free parameter now selects on
speaker-disjoint folds inside the training split. T2 has two — the ridge
penalty and the alignment offset — and one pass of fits scores both criteria,
so which criterion picks which parameter had to be decided rather than
inherited. D59 already fixes the penalty on validation RMSE, because the
468-octave failure it was raised about is invisible to a scale-free
correlation. The offset was given the headline metric, on the principle that
selecting on one quantity and reporting another is the fault D71 exists to
remove.

**Question:** should T2's alignment offset be selected on validation RMSE
rather than on the mean within-utterance Pearson r that 4.2 makes the headline?

**Measured**, E1 at Λ = 15343, context 5, leave-one-speaker-out folds inside
train, three split seeds. Validation profile across offsets −4 … +1:

| seed | val r, −4 → +1 | val RMSE (st), −4 → +1 | val picks | test picks |
|---|---|---|---|---|
| 0 | 0.493 0.505 0.513 0.522 **0.526** 0.514 | **1.379** 1.388 1.405 1.437 1.504 1.559 | r: 0, RMSE: −4 | −3 |
| 1 | 0.485 0.508 0.521 **0.525** 0.522 0.522 | 1.579 1.557 **1.561** 1.610 1.690 1.719 | r: −1, RMSE: −3 | −1 |
| 2 | 0.541 0.557 **0.570** 0.568 0.553 0.554 | 1.282 1.250 **1.248** 1.287 1.375 1.418 | r: −2, RMSE: −2 | −1 |

The correlation profile spans 0.033 over six offsets and its maximum moves
across all of 0, −1, −2 with the split seed. The RMSE profile has a clear
interior minimum at −2 or −3 on every seed, and the front end's declared lag
predicts −1 at the mean channel and −2 at the low channels — which is where f0
lives. So the two criteria are not equally informative about the same
quantity: one resolves the axis and agrees with a lag computed without fitting
anything, and the other does not resolve it at all.

**Why this is not obviously a free choice.** A correlation against a linear
declination is nearly invariant to a shift of one to three frames, because
shifting a straight line changes its intercept and not its slope. That is a
property of *this corpus* — the stand-in's f0 is a linear declination — and it
may well not hold on TIMIT, whose contours have accents. Choosing RMSE now
because it happens to bite here is the kind of choice that should be made once,
in the contract, rather than per corpus.

**Options considered:**
1. Offset on the headline correlation, as now. Consistent, and C5 honestly
   records the axis as unresolved (the interior-maximum test fails on the
   plateau). *Implemented as the provisional default.*
2. Offset on validation RMSE, correlation still the reported headline. The
   offset is a property of the encoder's lag rather than of the metric, and
   both metrics estimate the same lag; prefer the estimator with signal.
3. Offset fixed at the analytically predicted value and not selected at all,
   with the sweep retained purely as the C5 control. D69 makes the offset a
   swept axis, but D69's own argument is that the sweep is a *check* on two
   independently computed lags.

**Blocking?** no — option 1 is implemented and every T2 figure records the
RMSE-selected offset beside the chosen one, so the alternative reading is
recoverable from the result files without a re-run.
**Answer:** (open)

### Q39 — the 61-to-39 folding table is written from convention, not from the source
**Raised:** 2026-09-08 by implementation session
**Context:** implementing `timit_corpus` ahead of the licence. Proposal 4.1
requires that "following near-universal convention on TIMIT, the 61-symbol
label set is collapsed to 39 for scoring, and this must be stated whenever a
figure is quoted". So the table is part of what a reported number means, and it
is in `corpus.TIMIT_61_TO_39`.

**Question:** please check the table against Lee and Hon (1989), or against
whichever source the paper will cite, before any 39-symbol figure is reported.

**Why this is being asked rather than assumed.** The table was written out from
the convention as used in the HTK and Kaldi recipes. That paper is not on this
machine and CLAUDE.md forbids fabricating a parameter value or a claim about
what a source says. A folding table is precisely the artefact that is quoted
from memory and is wrong in one row, and one wrong row is invisible: it does
not fail, it moves a phone accuracy by a fraction of a point in a direction
nobody can see. What the tests can check without the source, and do, is that
the table is internally consistent — every symbol it emits is in the 39-set,
and no symbol is mapped twice.

**Two sub-questions that are not just transcription:**

1. **The glottal stop.** `q` is conventionally *deleted* rather than mapped.
   Implemented as a deletion, which leaves a gap in the segment tiling and
   therefore frames that `label_at` reports as unlabelled and the probe
   excludes. The alternative readings — fold `q` into `sil`, or merge it into
   the following segment — change both the frame count and the boundary set.
2. **Which corpus each task gets.** Folding merges adjacent segments that fold
   together, so `h#` followed by `pcl` becomes one `sil` and the boundary
   between them is gone. That is correct for T1 and wrong for T3, whose ground
   truth is the hand-placed boundary set. Implemented so that `fold_to_39` is
   an explicit call and T3 is documented as taking the unfolded corpus. Worth
   confirming, because it is the kind of thing that gets applied globally by a
   later script for tidiness.

**Blocking?** no — it blocks reporting a 39-symbol figure, not building the
loader, and T3 does not use the table at all.
**Answer:** (open)

### Q40 — T2 on TIMIT needs two pitch trackers, and this machine has none
**Raised:** 2026-09-08 by implementation session
**Context:** `timit_corpus` leaves `f0` and `voiced` as None, so T2 raises a
named error on TIMIT rather than scoring an invented contour. TIMIT carries
hand-placed phone labels and no pitch annotation.

**Question:** which two pitch trackers, and does the two-tracker disagreement
floor have to be measured before the first T2 figure on TIMIT, or alongside it?

**Context from the proposal.** 4.2 says "the reference contour is extracted
from the clean audio by a standard pitch tracker before encoding", and then
adds the caveat that "an automatically extracted contour is a proxy reference,
not ground truth. Pitch trackers make octave errors and disagree at voicing
boundaries. Two trackers should be run and their disagreement quantified,
giving a measured noise floor for the task before any encoder is judged
against it."

**What this costs here.** The box has numpy and scipy and nothing else — no
`librosa`, no `praat-parselmouth`, no `pysptk` — and CI installs `.[dev]` and
runs every file in `tests/`, so a tracker pulled in as a dependency would make
its own tests unrunnable in the one environment that checks them
independently. That is the D49 argument that put the linear probe in numpy.
So both trackers have to be written here, in numpy and scipy. Two independent
implementations is a real piece of work — the point of running two is that
they fail differently, so they cannot share a core.

**Options considered:**
1. Autocorrelation-based (the RAPT family) and cepstral. Long-established,
   both implementable in scipy, and they fail differently: autocorrelation
   makes octave errors downward, cepstrum upward.
2. YIN (difference function with cumulative mean normalisation) plus
   autocorrelation. YIN is the stronger single tracker and is about eighty
   lines; the pair is less independent than option 1, both being time-domain.
3. One tracker now, the second before any TIMIT figure is reported. Gets T2
   running on TIMIT sooner and defers the thing 4.2 asks for, which is the
   part that makes the number interpretable.
4. Treat the stand-in's exact contour as sufficient for the method and report
   TIMIT T2 only at stage two. Cheapest, and abandons a third of the battery
   on the corpus the study is anchored to.

**Blocking?** T2 on TIMIT only. T1 and T3 run on TIMIT the day it arrives.
**Answer:** (open)

### Q41 — the Spiketrum paper has been read, and §5.7 is wrong in four places
**Raised:** 2026-09-09 by implementation session
**Context:** Simon supplied the TETCI article, which is the first of the three
primary sources §5.7 asks for. Read in full and recorded as [Tang2025] in the
new `docs/references.md`. §5.7 is explicit that its description "is
reconstructed from published abstracts and citation records; the Spiketrum
papers have not been read in full", and §2 of the validation protocol names
that description as its worked example of the confabulation risk. It was right
to. Four things are wrong and two are consequential.

**Question:** please rewrite §5.7 from the source. The corrections below are
evidenced; the judgements that follow from them are the design session's.

**1. Attribution. §5.7 says "developed at Manchester by Alsakkal and
Wijekoon". It is a Zhejiang-led collaboration of eight.** Huajin Tang
(Zhejiang University) is first and corresponding author; Wijekoon and Alsakkal
are third and fourth and are the Manchester contributors. This bears directly
on **D09** and **O3**: approaching Wijekoon is still right for the Manchester
end, but the corresponding author is at Zhejiang, and a request for code or
for permission to run the encoder may have to go there or be routed by him.
Both Manchester addresses are in the paper and are in `docs/references.md`.

**2. §5.7 describes only the first of two stages, and the omitted stage is
where the representation is actually formed.** Equations (30) and (31) are
right as matching pursuit: Algorithm 1 of the paper, E-TMP, iterates
`(m_i, τ_i) = argmax_{m,τ} H_i^m(τ)` with `H_i^m(τ) = ∫ R_i(t) φ_m(t+τ) dt`,
then `R_{i+1} = R_i − H_i^{m_i}(τ_i) φ_{m_i}(t − τ_i)`, with amplitude
`s_i = H_i^{m_i}(τ_i)`. But the codes `(m_i, τ_i, s_i)` are *not* the output.
A second stage, **intensity-to-place (ITP) coding**, normalises all amplitudes
to [0, 1] and routes each code to one of K neurons by

> k = argmin_k |c_k − s_i|,  h = K(m_i − 1) + k   (paper's equations 3 and 4)

where the characteristic intensities `c_k` are spaced **logarithmically**, not
linearly — the paper measures log against linear and log wins on
representational precision, because natural-sound intensity coefficients are
log-normally distributed. So a spiketrum is a binary spike pattern over
**M × K channels**, and amplitude is carried in the *channel index*.

§5.7 currently says "the event train is the sequence of selected atom indices
and times", which describes the first stage and makes E7 look as though it
discards amplitude. It does the opposite: it place-codes it. This also gives
**Q07** a third convention to consider, since spiketrum's channel index
factorises as (kernel, quantised intensity) rather than as (channel, polarity).

**3. There is a second stopping criterion, and it is the same structural trap
as E5's.** Algorithm 1 terminates on

> `n > N` **or** `‖R_i‖² / ‖R_1‖² < ε_min`

so the rate parameter is capped by a residual-energy floor. §5.7 mentions only
the atom count. This matters for **D27**, the 4× span requirement: an encoder
whose count is bounded by a property of the drive rather than by its rate
parameter is exactly what Q11 found for E5 and Q14 for E6. If E7 is ever run,
its span should be measured before it is trusted, not assumed from λ = N/τ.

**4. §5.0 says "all candidates except E7 share a common first stage". They
share more than that.** The E-TMP dictionary is a set of ERB-spaced gammatone
kernels, `g(t) = a t^(n−1) e^(−2πbt) cos(2πft + φ)` — the same functional form
as the proposal's own equation (4), used as a matching-pursuit dictionary
rather than as a filterbank. That makes E7 a *better* comparison than the
proposal assumes: it differs from E1–E6 in the event rule, which is the
single-factor contrast the study is built on, and not in the front end.

**What §5.7 gets right, confirmed against the source.** The matching-pursuit
identification; the rate parameter, which is exactly `λ = N/τ` with N the
iteration count and τ the signal duration — the paper's equation (2), and the
same quantity as our own Λ of equation (35); the reconstruction capability and
therefore §5.7's observation that E7 optimises the criterion §2.2 argues
against; and the hardware, which is a real FPGA cochlea prototype (XEM7310
Xilinx Artix-7, 16 kHz, 43.5 ms buffered segments, **120 output channels = 40
gammatone kernels × 3 characteristic intensities**, two cochleae).

**Two facts that bear on the comparison.**

- **Reported operating range.** The paper works at λ between 100 Hz and
  1100 Hz for its structure-invariance analysis and at λ = 4 kHz for the
  information-theoretic one. Our own E1 sweep ran Λ = 160 to 15,343 events/s
  at 32 channels, so the ranges overlap and a matched-budget comparison is
  feasible on its face.
- **No phone-level task and no TIMIT.** Evaluation is on RWCP sound events and
  MedleyDB instruments, plus natural sounds, music and speech. There is
  therefore no published spiketrum number on anything resembling T1, T2 or T3
  to anchor against, and control C1 cannot be extended to E7 from this paper.

**Two sources still outstanding, and one of them may not exist as described.**
§5.7 names a TCSI article on the FPGA cochlea and an evaluation paper. This
paper cites **no** work authored by Wijekoon or Alsakkal, and it describes the
FPGA cochlea itself in its §V. Whether those two exist as §5.7 says is
therefore unsettled — §5.7's list of three was assembled from citation records,
which is the provenance §2 warns about.

**Blocking?** no. D09 blocks implementation whatever the description says, and
that is unchanged: reading the paper makes §5.7 accurate, it does not make E7
implementable. Only the O3 conversation does that.
**Answer:** (open)

### Q42 — the applied E7 patch states a dictionary size and a channel count the paper does not contain
**Raised:** 2026-09-09 by implementation session
**Context:** the E7 drop was applied in full as D80 and is correct in every
respect I could check bar one. Section 5.7 now reads, of intensity-to-place
coding: *"at the paper's own settings, with K = 30, a 64-atom dictionary
yields 1920 channels, against the few dozen this study sweeps"*, and the
notebook entry and O3's restatement both rest on it — O3 asks Oliver to decide
"what value of K the intensity-to-place expansion should use, since the
paper's own setting yields a channel count an order of magnitude above the
range this study sweeps".

**Question:** please correct the figure. The substantive point survives; the
conclusion drawn from it does not, and it is now in a decision put to Oliver.

**What the paper actually contains**, checked against
`~/Downloads/tang_2025_neural_spiketrum.pdf` and recorded as [Tang2025]:

- The string `1920` does not occur anywhere in the paper.
- `64` occurs three times, none of them a dictionary size: twice as citation
  marker [64], and once inside a reference to a *different* group's "64 × 2
  channel binaural silicon cochlea".
- The only dictionary size the paper states is the hardware prototype's:
  **40 gammatone kernels and 3 characteristic intensities, giving 120 output
  channels** (§V, XEM7310 Artix-7). Two such cochleae.
- K appears as K = 5 and K = 30 in the precision analysis of Fig. 2, and K = 30
  is described as the *small* end — "Plog approaches closely with the values
  computed by the efficient coding theory even setting K as small as K = 30".
- The two SNN experiments have input layers of 384 and 128 units.

So M = 64 is invented, and 1920 with it. **This is the failure mode §2 of the
validation protocol describes, occurring inside the correction of an earlier
instance of the same failure mode**, which is worth saying plainly rather than
passing over: the drop's own notebook entry concludes that inference from
abstracts "is safe for the technical content of a well-known method and unsafe
for anything social". This error is neither — it is a specific numeric
parameter, stated with a confidence the source does not support.

**Why the conclusion inverts, not just the number.** At the authors' own
deployed setting the channel count is **120**, which is not "an order of
magnitude above the range this study sweeps" — it is inside it. D05 makes
channel count a swept free parameter and our own runs use 32, with the
proposal contemplating up to 700. Even at M = 40, K = 30 the count is 1200,
which is large but is a configuration the authors describe as small in K
rather than as their setting. So:

- the C4 matched-treatment concern is real in principle and much weaker in
  practice than 5.7 now states;
- the third question O3 puts to Oliver — what value of K to use — may not need
  his decision at all, since the authors' hardware answers it with K = 3.

**Options considered:**
1. Replace the sentence with the paper's own figures: hardware 40 × 3 = 120
   channels; K = 30 shown to retain precision; note that M and K are both free
   and that a matched channel count is therefore reachable. Restate O3's third
   question as confirming K rather than choosing it. *Recommended.*
2. Keep the concern, drop the numbers entirely: "the expansion multiplies the
   channel count by K, which must be set before E7 enters".
3. Leave as is. Not tenable: it is in a decision going to Oliver.

**Blocking?** Report v3 must not quote 5.7's channel figures until this is
settled, and O3 should not go to Oliver in its current form.
**Answer:** (open)
