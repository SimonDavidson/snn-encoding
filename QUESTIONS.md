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

