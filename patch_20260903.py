#!/usr/bin/env python3
"""
Design-session patch, 2026-09-03 — answers Q05.

  1. SPEC.md 3 — group-delay compensation redefined as a property of the whole
     envelope path rather than of the filterbank alone: advance each channel by
     the sum of the declared lags of the stages actually used. Raise rather
     than silently under-compensate if a stage cannot declare its lag.

  2. tests/test_known_answers.py — new test_F6, which measures onset alignment
     on the path actually selected. This is the third timing bias in a row that
     no test detects (D19, Q05); the pattern is the point.

Run from the repository root:  python3 patch_20260903.py
"""
import io, os, sys

SPEC_ANCHOR = "**Envelope cutoff (equation 9).**"
SPEC_NEW = '''**Group-delay compensation applies to the path, not the filterbank.** When
`compensate_group_delay=True`, each channel is advanced by the sum of the
declared lags of every stage between the input and the returned envelope:

    lag_c = gammatone_lag_c + envelope_stage_lag_c

with `gammatone_lag_c = (order - 1) / (2 * pi * b_c)` and the envelope-stage
lag being zero for `method="hilbert"` and `method="none"`, and the lowpass
group delay at DC for `method="rectify_lowpass"`. Every stage that introduces a
channel-dependent lag must declare it; a stage that cannot must raise rather
than allow silent partial compensation.

The reason for stating it this way is that compensation applied inside
`subbands` cannot remove a lag introduced downstream of it. Under the
channel-relative cutoff above, the envelope lowpass contributes the *larger* of
the two lags, and contributes most in the low channels where the gammatone
delay is already worst. Compensating only the first stage would leave roughly
two thirds of the onset skew in place while the flag reported alignment, which
is worse than not compensating at all: an uncompensated bias is a known
quantity, a partially compensated one is not.

Compensation is exact only for components slow relative to the stage
bandwidths, since Butterworth group delay is not flat. For T3, where the
quantity of interest is onset timing, `test_F6` measures the alignment actually
achieved rather than assuming the analytic value; report the measured residual
spread alongside any T3 result taken with compensation on.

'''

F6_ANCHOR = '''# ===========================================================================
# E1 — LIF. Closed-form firing period, equation (V1) of the protocol.
# ==========================================================================='''

F6_TEST = '''def test_F6_group_delay_compensation_aligns_onsets():
    """SPEC 3: compensation aligns onsets across the bank.

    Measured on the envelope path actually selected, because the gammatone
    delay is only one of the stages contributing channel-dependent lag. A
    broadband click should emerge from every channel at the same time once
    compensation is applied; uncompensated it should not.

    Thresholds are deliberately loose. The claim being tested is that
    compensation substantially removes the skew, not that it removes it to any
    particular precision — Butterworth group delay is not flat, so exact
    alignment of a broadband transient is not available. Record the measured
    spreads in NOTEBOOK.md so this can be tightened later.
    """
    n = FS
    click = np.zeros(n)
    click[n // 3] = 1.0
    for method in ("hilbert", "rectify_lowpass"):
        spread = {}
        for comp in (False, True):
            fb = Filterbank(n_channels=16, f_min=150.0, f_max=6000.0,
                            sample_rate=FS, compensate_group_delay=comp)
            env = fb.envelope(click, method=method)
            peaks = np.array([np.argmax(env[c]) for c in range(16)]) / FS
            spread[comp] = float(peaks.max() - peaks.min())
        assert spread[False] > 0.004, (
            f"{method}: uncompensated spread only {spread[False]*1000:.2f} ms — "
            "expected several ms of skew across the bank")
        assert spread[True] < spread[False] / 3.0, (
            f"{method}: compensation reduced onset spread only from "
            f"{spread[False]*1000:.2f} ms to {spread[True]*1000:.2f} ms")


'''

Q05_ANSWER = """**Answer:** Option 1, restated so the flag means what it says, with option 3
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
"""


def main():
    if not os.path.exists("CLAUDE.md"):
        sys.exit("error: run this from the repository root.")
    rep = []

    p = "SPEC.md"; t = io.open(p, encoding="utf-8").read()
    if "**Group-delay compensation applies to the path" in t:
        rep.append(f"{p}: already patched")
    elif SPEC_ANCHOR in t:
        io.open(p, "w", encoding="utf-8").write(t.replace(SPEC_ANCHOR, SPEC_NEW + SPEC_ANCHOR, 1))
        rep.append(f"patched {p}")
    else:
        sys.exit(f"ANCHOR NOT FOUND in {p}; nothing written.")

    p = "tests/test_known_answers.py"; t = io.open(p, encoding="utf-8").read()
    if "test_F6_group_delay_compensation_aligns_onsets" in t:
        rep.append(f"{p}: already patched")
    elif F6_ANCHOR in t:
        io.open(p, "w", encoding="utf-8").write(t.replace(F6_ANCHOR, F6_TEST + F6_ANCHOR, 1))
        rep.append(f"patched {p} (test_F6 added)")
    else:
        sys.exit(f"ANCHOR NOT FOUND in {p}; SPEC.md was written, test file was not.")

    p = "QUESTIONS.md"; t = io.open(p, encoding="utf-8").read()
    if "D24" in t:
        rep.append(f"{p}: already answered")
    else:
        old = ("**Blocking?** no — `\"hilbert\"` is the default and nothing currently sweeps\n"
               "either axis. It blocks the envelope-method sweep crossed with the group-delay\n"
               "axis.\n**Answer:** (design session)")
        if old not in t:
            rep.append(f"WARNING: {p} anchor not found — paste the answer by hand")
        else:
            io.open(p, "w", encoding="utf-8").write(
                t.replace(old, old.replace("**Answer:** (design session)", Q05_ANSWER), 1))
            rep.append(f"patched {p} (Q05 answered)")

    for line in rep:
        print(line)
    print("""
Add to DECISIONS.md:

D24 | 2026-09-03 | SD+Claude | compensate_group_delay advances each channel by the summed declared lag of every stage in the envelope path, not the filterbank alone; a stage that cannot declare its lag raises | compensation applied in subbands cannot remove a lag added downstream, and under D21 the envelope lowpass is the larger contributor in exactly the channels where the gammatone delay is worst
D25 | 2026-09-03 | SD+Claude | test_F6 added, measuring onset spread across the bank with and without compensation on both envelope methods | third channel-dependent timing bias in a row that no test detected

  git add -A
  git commit -m 'Answer Q05: compensation covers the whole envelope path, add test_F6 [spec]'
  git push""")


if __name__ == "__main__":
    main()
