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
**Answer:** (open)

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
**Answer:** (open)

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
**Answer:** (open)

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
**Answer:** (open)
