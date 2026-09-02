#!/usr/bin/env python3
"""
Patch SPEC.md — design session amendment, 2026-09-02.

Three changes, all arising from questions raised by the implementation session:

  1. §3   Filterbank gains a declared `compensate_group_delay` option.
  2. §4.2 LIF refractory semantics pinned (clamp, drive discarded), with the
          reason it must be zero for E1/E4 comparison runs.
  3. §4.3 E2 reference held as an integer lattice index.

Run from the repository root:   python3 patch_spec_20260902.py
Idempotent: re-running is a no-op. Fails loudly if an anchor is missing rather
than silently producing a half-patched file.
"""
import io
import sys

PATH = "SPEC.md"

EDITS = [
    # ---------------------------------------------------------------- §3
    dict(
        name="Filterbank: compensate_group_delay argument",
        anchor="    order: int = 4,\n",
        replacement="    order: int = 4,\n    compensate_group_delay: bool = False,\n",
        skip_if="compensate_group_delay",
    ),
    dict(
        name="Filterbank: group delay explanation",
        anchor="equation (6) between `f_min` and `f_max` inclusive, so `centre_frequencies[0] ==\n`f_min` and `centre_frequencies[-1] == f_max`.\n",
        replacement=(
            "equation (6) between `f_min` and `f_max` inclusive, so `centre_frequencies[0] ==\n"
            "`f_min` and `centre_frequencies[-1] == f_max`.\n"
            "\n"
            "**Group delay.** Gammatone filters have frequency-dependent group delay: a\n"
            "low-frequency channel responds later than a high-frequency one to the same\n"
            "acoustic event. This is biologically faithful and is the default\n"
            "(`compensate_group_delay=False`).\n"
            "\n"
            "It is also a systematic, frequency-dependent bias on event timing, and\n"
            "therefore on T3 boundary detection, where a single onset appears at different\n"
            "times in different channels. **No test in the known-answer suite detects\n"
            "it** — F1 checks spectral peaks, and G4 passes because a uniform shift of the\n"
            "input remains uniform at the output. It has to be handled by declaration\n"
            "rather than by test.\n"
            "\n"
            "With `compensate_group_delay=True`, each channel's output is advanced by that\n"
            "channel's group delay at its centre frequency, aligning onsets across the\n"
            "bank. Treated as a swept binary axis in the study; whichever setting produced\n"
            "a reported result is stated in the paper, since a reader comparing T3 figures\n"
            "against another group's has no way to infer it.\n"
        ),
        skip_if="**Group delay.**",
    ),
    # -------------------------------------------------------------- §4.2
    dict(
        name="LIF: refractory semantics",
        anchor="polarities `+1`. State keys: `\"v\"`.\n",
        replacement=(
            "polarities `+1`. State keys: `\"v\"`.\n"
            "\n"
            "**Refractory semantics.** During an absolute refractory period the membrane\n"
            "potential is clamped to the reset value and incoming drive is discarded. The\n"
            "interspike interval under saturating drive is therefore exactly `refractory`,\n"
            "and the rate ceiling exactly `1/refractory`.\n"
            "\n"
            "This is a declared modelling choice rather than an implementation detail,\n"
            "because clamping is itself mildly adaptive: discarding drive during recovery\n"
            "suppresses the response to sustained strong input, in the same direction as\n"
            "spike-frequency adaptation. E1 must be a clean *non*-adapting baseline for the\n"
            "E1-against-E4 contrast that prediction P-01 rests on, so **`refractory` is\n"
            "fixed at `0.0` for all E1 and E4 comparison runs.**\n"
            "\n"
            "Note also that `refractory` is a second rate-limiting mechanism alongside the\n"
            "declared RATE_PARAM `theta`. Sweeping both would confound the matched-budget\n"
            "comparison of proposal §6.4, so `refractory` is a fixed, declared parameter\n"
            "and never a swept axis.\n"
        ),
        skip_if="**Refractory semantics.**",
    ),
    # -------------------------------------------------------------- §4.3
    dict(
        name="E2: integer lattice reference",
        anchor="`refractory == 0` the bound holds strictly. State keys: `\"reference\"`.\n",
        replacement=(
            "`refractory == 0` the bound holds strictly. State keys: `\"reference\"`.\n"
            "\n"
            "**Reference representation.** In the `\"lattice\"` variant the reference is held\n"
            "as an integer lattice index `m`, with the value computed as `r = r0 + m * C`,\n"
            "not accumulated by repeated addition of `C`. Repeated floating-point addition\n"
            "accumulates rounding error across a long utterance and can erode the equation\n"
            "(16) bound that `test_T2_1` asserts; an integer index keeps the bound exact\n"
            "regardless of duration.\n"
        ),
        skip_if="**Reference representation.**",
    ),
    # -------------------------------------------------------------- §4.5
    dict(
        name="ALIF: cross-reference to refractory rule",
        anchor="Share the implementation rather than duplicating it. State\nkeys: `\"v\"`, `\"threshold\"`.\n",
        replacement=(
            "Share the implementation rather than duplicating it. State\n"
            "keys: `\"v\"`, `\"threshold\"`.\n"
            "\n"
            "The refractory rule of §4.2 applies unchanged, including the requirement that\n"
            "`refractory == 0.0` for comparison runs.\n"
        ),
        skip_if="The refractory rule of §4.2 applies unchanged",
    ),
]


def main():
    try:
        text = io.open(PATH, encoding="utf-8").read()
    except FileNotFoundError:
        sys.exit(f"error: {PATH} not found. Run this from the repository root.")

    applied, skipped, failed = [], [], []
    for e in EDITS:
        if e["skip_if"] in text:
            skipped.append(e["name"])
            continue
        if e["anchor"] not in text:
            failed.append(e["name"])
            continue
        text = text.replace(e["anchor"], e["replacement"], 1)
        applied.append(e["name"])

    if failed:
        print("ANCHOR NOT FOUND — nothing written:")
        for n in failed:
            print(f"  - {n}")
        sys.exit("SPEC.md unchanged. Send this output back to the design session.")

    io.open(PATH, "w", encoding="utf-8").write(text)
    for n in applied:
        print(f"applied : {n}")
    for n in skipped:
        print(f"already present, skipped : {n}")
    print(f"\n{PATH} updated. Commit it, then tell Claude Code to re-read SPEC.md.")


if __name__ == "__main__":
    main()
