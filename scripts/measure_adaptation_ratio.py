"""Measure E4's onset emphasis against adaptation strength — D35 registration.

Section 7 of the encoder survey has carried a table of `ISI_ss / ISI_1` against
`delta_a` since v1, marked "not yet registered in the manifest". This script is
that registration. Every reported number is produced by a script under a
committed config (D35), and a table in a document sent to a colleague is a
reported number whatever else it is.

What it measures. `test_T4_3`'s premise was that early/late spike-count ratio
rises monotonically with adaptation strength; D39 replaced that assertion after
Q10 established the ALIF has no such monotonicity. The quantity underneath is
onset emphasis — the steady-state interspike interval divided by the first —
and it is non-monotone with a peak, because adaptation from the first spike
suppresses the second and so lengthens the *onset* interval as well as the
steady-state one. Where the peak sits matters to P-01, which predicts T1 and
T2 moving in opposite directions "as adaptation strength increases": a sweep
that straddles the peak can confirm or contradict that prediction according to
which side its points land on.

The drive is a step into steady state, held long enough that the late interval
is a steady state rather than the tail of a transient — the earlier unregistered
measurement used 5 s with 200 ms windows for that reason, and this keeps it.

Usage:
    python scripts/measure_adaptation_ratio.py configs/e4_adaptation_ratio.json

Author:        Simon Davidson & Claude
Created:       2026-09-09
Last modified: 2026-09-09
"""
import sys

import numpy as np

from spikeenc.encoders import ALIF
from spikeenc.provenance import load_config, record


def isi_ratio(delta_a, cfg):
    """(ISI_ss / ISI_1, ISI_1, ISI_ss, n_events) for one adaptation strength.

    ISI_1 is the first interspike interval after onset and ISI_ss the mean of
    the final `n_steady` intervals. A fixed time window was tried first and is
    wrong: at delta_a = 8 the steady interval is longer than a 200 ms window,
    so no interval starts inside it and the ratio comes back NaN at exactly the
    adaptation strengths the measurement is about. Counting intervals rather
    than seconds is rate-independent, which is the property needed when the
    rate is the thing being swept.

    Returns NaN where there are too few events to define either, rather than a
    number that looks like a measurement.
    """
    dt = 1.0 / cfg["sample_rate"]
    n = int(round(cfg["duration"] * cfg["sample_rate"]))
    drive = np.full((1, n), float(cfg["drive_level"]))

    enc = ALIF(1, theta_0=cfg["theta_0"], tau_m=cfg["tau_m"],
               tau_a=cfg["tau_a"], delta_a=float(delta_a),
               refractory=cfg["refractory"])
    train = enc.encode_from_drive(drive, dt)
    t = np.sort(train.time)
    if len(t) < 3:
        return np.nan, np.nan, np.nan, len(t)

    isi = np.diff(t)
    first = float(isi[0])
    n_steady = min(int(cfg["n_steady"]), max(1, isi.size - 1))
    late = isi[-n_steady:]
    if late.size == 0 or first <= 0:
        return np.nan, first, np.nan, len(t)
    steady = float(np.mean(late))
    return steady / first, first, steady, len(t)


def main(config_path):
    cfg = load_config(config_path)
    values, rows = [], []
    for d in cfg["delta_a"]:
        ratio, first, steady, n_ev = isi_ratio(d, cfg)
        rows.append({"delta_a": float(d), "isi_ratio": ratio,
                     "isi_first_s": first, "isi_steady_s": steady,
                     "n_events": int(n_ev)})
        values.append(ratio)
        print(f"  delta_a {d:>6}: ISI_1 {first * 1e3:7.2f} ms  "
              f"ISI_ss {steady * 1e3:7.2f} ms  ratio {ratio:5.2f}  "
              f"({n_ev} events)")

    finite = [v for v in values if np.isfinite(v)]
    peak_at = (float(cfg["delta_a"][int(np.nanargmax(values))]) if finite
               else None)
    monotonic = bool(finite == sorted(finite)) if finite else None

    out = record(cfg["id"], script=__file__, config=cfg["_path"],
                 seed=cfg.get("seed", 0),
                 values={"rule": "E4 onset emphasis, ISI_ss / ISI_1",
                         "points": rows,
                         "peak_delta_a": peak_at,
                         "peak_ratio": (float(np.nanmax(values)) if finite
                                        else None),
                         "monotonic_in_delta_a": monotonic,
                         "settings": {k: cfg[k] for k in
                                      ("sample_rate", "duration", "n_steady",
                                       "drive_level", "theta_0", "tau_m",
                                       "tau_a", "refractory")},
                         "note": ("Registers the table carried unregistered in "
                                  "the encoder survey since v1. Bears on P-01: "
                                  "a delta_a sweep straddling the peak can "
                                  "confirm or contradict it depending on which "
                                  "side its points fall. Does not reproduce "
                                  "the unregistered table carried in survey v1 "
                                  "and v2, whose parameters were never "
                                  "recorded; those numbers are withdrawn.")},
                 predictions=cfg.get("predictions", []),
                 supersede=cfg.get("supersede", False))
    print(f"\n  peak at delta_a = {peak_at}, ratio {np.nanmax(values):.2f}; "
          f"monotonic in delta_a: {monotonic}")
    print(f"written: {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/measure_adaptation_ratio.py "
                         "<config.json>")
    main(sys.argv[1])
