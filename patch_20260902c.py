#!/usr/bin/env python3
"""
Design-session patch, 2026-09-02c — answers Q03 and Q04.

  1. SPEC.md 3 — envelope cutoff for equation (9) becomes channel-relative:
     f_cut_c = min(f_cut, b_c). Answers Q03.

  2. SPEC.md 4.3 — the D20 threshold tolerance is promoted from an
     implementation decision into the contract. It has to be in SPEC because
     Layer 3 of the validation protocol requires Simon to reimplement E2
     independently and compare event for event; without the tolerance in the
     contract the two implementations disagree at exactly the crest events.

  3. tests/test_known_answers.py — T2.4 builds a signal that genuinely closes.
     Answers Q04.

  4. tests/conftest.py — sine_drive docstring corrected; it does not end at
     zero phase.

Run from the repository root:  python3 patch_20260902c.py
Idempotent. Exits without writing if an anchor is missing.
"""
import io
import os
import sys

SPEC_ENVELOPE_ANCHOR = "**Compression method strings.**"
SPEC_ENVELOPE = '''**Envelope cutoff (equation 9).** The `"rectify_lowpass"` branch uses a
channel-relative cutoff rather than one value for the whole bank:

    f_cut_c = min(f_cut, b_c)

with `b_c` the channel's own bandwidth from equation (5) and `f_cut` a global
ceiling, default 1000 Hz. Fourth order.

The reason is physical rather than empirical. A subband of bandwidth `b_c`
cannot carry envelope modulation faster than `b_c`, so a cutoff above the
channel bandwidth admits carrier without admitting any more envelope. A single
fixed cutoff cannot satisfy both ends of the bank at once: 300 Hz sits above
the carrier in a 196 Hz channel and removes nothing, while a cutoff low enough
for that channel would discard genuine envelope at 3 kHz.

This departs from equation (9) as written in proposal v2, which specifies one
cutoff. The equation is underspecified rather than wrong, and proposal 5.0
should carry the channel-relative form when v3 is issued.

Note for the record why the fixed-cutoff alternative was rejected on more than
accuracy. Carrier leaking into the low-channel envelope would make E1, E2, E3,
E4 and E6 partly phase-locking encoders in exactly the channels where F_0 and
its low harmonics live. E5 exists to be the encoder that carries fine
structure, and prediction P-03 turns on the contrast between it and the
envelope encoders on T2. An envelope method that smuggles periodicity into the
others would not merely lose accuracy; it would blur the distinction the probe
battery is built to measure, and it would do so invisibly.

`method="none"` returns the rectified subband without lowpass filtering, for
callers that want to supply their own.

'''

SPEC_D20_ANCHOR = "regardless of duration.\n"
SPEC_D20 = '''regardless of duration.

**Threshold comparison tolerance.** Outstanding lattice steps are measured as
`(u - r0)/C - m`, never as `(u - r0 - m*C)/C`, and the comparison against the
threshold carries a tolerance of `1e-9` lattice units.

This is part of the contract, not an implementation detail, because Layer 3 of
the validation protocol calls for an independent reimplementation of E2 whose
output is compared event for event. Two implementations that differ here
disagree at every excursion crest, and the disagreement would look like a bug
in one of them.

The reason it is needed: drive landing exactly on a lattice point is routine,
not exceptional. With `u = 1.0` and `r = 9C = 0.9`, equation (14) asks whether
`u - r >= C`. In exact arithmetic `0.1 >= 0.1` fires; in doubles the
subtraction yields `0.09999999999999998` and it does not, so the crest event of
every excursion is dropped and the descent begins one step in. The tolerance
can only fire an event early, never late, so the bound of equation (16)
tightens rather than loosens.

'''

T24_OLD = '''def test_T2_4_polarity_balances_over_a_closed_loop():
    """A signal returning to its starting value must emit equal ON and OFF
    counts. Follows exactly from equation (16)."""
    enc = E.SendOnDelta(n_channels=1, C=0.1, refractory=0.0)
    train = enc.encode_from_drive(sine_drive(1.0, 5.0, n_channels=1, duration=2.0), DT)
'''

T24_NEW = '''def test_T2_4_polarity_balances_over_a_closed_loop():
    """A signal returning exactly to its starting value must emit equal ON and
    OFF counts.

    The signal is built here rather than taken from sine_drive, which samples
    the half-open interval [0, D) and so ends one sample short of closing. That
    matters more than it looks. Writing the net lattice displacement as m and
    the endpoint mismatch as eps, equation (16) gives |eps - m*C| < C, which
    pins m to zero only when eps is exactly zero: at eps = -2e-3, and even at
    eps = -2e-15, both m = 0 and m = -1 satisfy the bound and the encoder is
    entitled to either. The endpoint is therefore forced to equal the first
    sample exactly, which makes the assertion a theorem again rather than a
    property of floating-point sine.
    """
    n = int(round(2.0 / DT)) + 1               # closed interval [0, D]
    t = np.arange(n) * DT
    u = np.sin(2 * np.pi * 5.0 * t)
    u[-1] = u[0]                               # close it exactly
    enc = E.SendOnDelta(n_channels=1, C=0.1, refractory=0.0)
    train = enc.encode_from_drive(u[None, :], DT)
'''

CONFTEST_OLD = '''def sine_drive(amplitude, frequency, n_channels=4, duration=2.0, dt=DT):
    """Sinusoidal drive, starting and ending at zero phase."""'''

CONFTEST_NEW = '''def sine_drive(amplitude, frequency, n_channels=4, duration=2.0, dt=DT):
    """Sinusoidal drive over the half-open interval [0, duration).

    Note that this does NOT end at zero phase: the last sample sits at
    duration - dt. Any test needing a signal that closes exactly must build its
    own and force the endpoint, as test_T2_4 does.
    """'''

Q03_ANSWER = """**Answer:** Option 2, with the cutoff tied to the channel's own bandwidth
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
"""

Q04_ANSWER = """**Answer:** The analysis is right and the encoder is right; the test premise
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
"""


def patch(path, old, new, marker, report, required=True):
    if not os.path.exists(path):
        report.append(f"WARNING: {path} not present")
        return True
    t = io.open(path, encoding="utf-8").read()
    if marker in t:
        report.append(f"{path}: already patched, skipped")
        return True
    if old not in t:
        report.append(f"ANCHOR NOT FOUND in {path}")
        return not required
    io.open(path, "w", encoding="utf-8").write(t.replace(old, new, 1))
    report.append(f"patched {path}")
    return True


def main():
    if not os.path.exists("CLAUDE.md"):
        sys.exit("error: run this from the repository root.")

    report, ok = [], True
    ok &= patch("SPEC.md", SPEC_ENVELOPE_ANCHOR, SPEC_ENVELOPE + SPEC_ENVELOPE_ANCHOR,
                "**Envelope cutoff (equation 9).**", report)
    ok &= patch("SPEC.md", SPEC_D20_ANCHOR, SPEC_D20,
                "**Threshold comparison tolerance.**", report)
    ok &= patch("tests/test_known_answers.py", T24_OLD, T24_NEW,
                "closed interval [0, D]", report)
    ok &= patch("tests/conftest.py", CONFTEST_OLD, CONFTEST_NEW,
                "does NOT end at zero phase", report)

    # answers appended to QUESTIONS.md
    p = "QUESTIONS.md"
    t = io.open(p, encoding="utf-8").read()
    if "D21" not in t:
        t = t.replace("**Blocking?** no — `\"hilbert\"` is the SPEC section 3 default and every current\ntest path uses it. It blocks only the envelope-method sweep.\n**Answer:** (design session)",
                      "**Blocking?** no — `\"hilbert\"` is the SPEC section 3 default and every current\ntest path uses it. It blocks only the envelope-method sweep.\n" + Q03_ANSWER)
        t = t.replace("**Blocking?** no — E2 is otherwise complete and its four analytic tests pass.\nIt blocks only the T2.4 assertion itself.\n**Answer:** (design session)",
                      "**Blocking?** no — E2 is otherwise complete and its four analytic tests pass.\nIt blocks only the T2.4 assertion itself.\n" + Q04_ANSWER)
        io.open(p, "w", encoding="utf-8").write(t)
        report.append(f"patched {p} (Q03, Q04 answered)")
    else:
        report.append(f"{p}: answers already present, skipped")

    for line in report:
        print(line)
    if not ok:
        sys.exit("\nOne or more anchors missing — send this output back to the design session.")

    print("""
Add to DECISIONS.md:

D21 | 2026-09-02 | SD+Claude | Equation (9) envelope cutoff is channel-relative, f_cut_c = min(f_cut, b_c), fourth order | a subband cannot carry envelope faster than its own bandwidth, and fixed-cutoff carrier leakage would make E1-E4 and E6 partly phase-locking in the channels carrying F0, blurring the E5 contrast that P-03 rests on
D22 | 2026-09-02 | SD+Claude | test_T2_4 builds its own signal with the endpoint forced equal to the first sample | eq (16) pins the net lattice displacement to zero only when the closure is exact; sine_drive samples a half-open interval
D23 | 2026-09-02 | SD+Claude | D20 promoted from implementation decision into SPEC 4.3 | Layer 3 requires an independent reimplementation of E2 compared event for event, which needs the tolerance in the contract

  git add -A
  git commit -m 'Answer Q03 and Q04: envelope cutoff, T2.4 closure, D20 into spec [spec]'
  git push""")


if __name__ == "__main__":
    main()
