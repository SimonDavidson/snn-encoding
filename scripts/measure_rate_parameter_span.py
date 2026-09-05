"""Measure whether an encoder's declared RATE_PARAM clears D27's 4x span.

D27 requires the declared rate parameter to move the event count monotonically
and by at least a factor of four across test_G3's 16x sweep. Whether it can is
a property of the event *rule*, not of any implementation, so this simulates
the rule from SPEC directly and can be run before the encoder exists — which is
the point: E5's rule was measured at 1.04x (Q11) before an encoder was written
whose constructor signature is still in question.

The drive is imported from tests/conftest.py rather than reimplemented, so the
measurement is on test_G3's own drive. A local copy could drift and would then
silently be measuring something else.

Usage:
    python scripts/measure_rate_parameter_span.py configs/e5_rate_parameter_span.json

Author:        Simon Davidson & Claude
Created:       2026-09-05
Last modified: 2026-09-05
"""
import sys

import numpy as np
from scipy.signal import hilbert

from spikeenc.provenance import load_config, record, repo_root

sys.path.insert(0, str(repo_root() / "tests"))
from conftest import DT, drive_for  # noqa: E402


class _DriveKind:
    """Shim: drive_for dispatches on the class attribute alone."""
    def __init__(self, kind):
        self.DRIVE_KIND = kind


def e5_count(drive, dt, params):
    """SPEC 4.6, mode="deterministic": emit at each upward zero crossing of the
    subband where the envelope exceeds `threshold`, subject to `refractory`.

    Which envelope gates the crossings is not stated in SPEC 4.6 and is the
    first half of Q12; the Hilbert envelope is assumed here and declared in the
    config. With centre_frequencies=None every channel is below f_lock, so the
    LIF fallback — the second half of Q12 — does not arise.
    """
    env = np.abs(hilbert(drive, axis=-1))
    total = 0
    for c in range(drive.shape[0]):
        x = drive[c]
        crossings = np.where((x[:-1] <= 0.0) & (x[1:] > 0.0))[0] + 1
        last = -np.inf
        for i in crossings:
            t = i * dt
            if env[c, i] > params["threshold"] and t - last >= params["refractory"]:
                total += 1
                last = t
    return total


def e5_diagnostics(drive, dt, params):
    env = np.abs(hilbert(drive, axis=-1))
    x = drive
    n_cross = int(np.sum((x[:, :-1] <= 0.0) & (x[:, 1:] > 0.0)))
    return {
        "upward_zero_crossings_total": n_cross,
        "envelope_p25": float(np.percentile(env, 25)),
        "envelope_median": float(np.median(env)),
        "note": ("the count is bounded above by the number of upward zero "
                 "crossings, a property of the carrier; the threshold only "
                 "gates quiet passages"),
    }


def e6_count(drive, dt, params):
    """SPEC 4.7: at most one event per channel per frame, emitted where the
    frame energy reaches `e_min`. Frame energy is the sum of squared drive
    samples in the frame; frame m covers [m*hop, m*hop + frame)."""
    return int(np.sum(_e6_energies(drive, dt, params) >= params["e_min"]))


def _e6_energies(drive, dt, params):
    frame, hop = params["frame"], params["hop"]
    n_ch, n = drive.shape
    n_frames = int(np.floor((n * dt - frame) / hop)) + 1
    E = np.empty((n_ch, n_frames))
    for m in range(n_frames):
        i0 = int(round(m * hop / dt))
        i1 = int(round((m * hop + frame) / dt))
        E[:, m] = np.sum(drive[:, i0:i1] ** 2, axis=1)
    return E


def e6_diagnostics(drive, dt, params):
    E = _e6_energies(drive, dt, params)
    return {
        "ceiling_n_ch_times_n_frames": int(E.size),
        "frame_energy_min": float(E.min()),
        "frame_energy_p1": float(np.percentile(E, 1)),
        "frame_energy_median": float(np.median(E)),
        "frame_energy_max": float(E.max()),
        "decades_below_quietest_frame": float(np.log10(E.min() / params["e_min"])),
        "note": ("e_min gates nothing while it sits below the quietest frame; "
                 "the parameter itself is not structurally flat"),
    }


RULES = {"e5_deterministic": (e5_count, e5_diagnostics),
         "e6_frame_energy": (e6_count, e6_diagnostics)}


def main(config_path):
    cfg = load_config(config_path)
    count_fn, diag_fn = RULES[cfg["rule"]]
    drive = drive_for(_DriveKind(cfg["drive_kind"]),
                      n_channels=cfg["n_channels"],
                      duration=cfg["duration_s"], seed=cfg["seed"])

    base = dict(cfg["params"])
    param = cfg["rate_param"]
    counts = []
    for factor in cfg["sweep_factors"]:
        p = dict(base)
        p[param] = base[param] * factor
        counts.append(count_fn(drive, DT, p))
    counts = np.array(counts)

    direction = cfg["rate_direction"]
    if direction < 0:
        monotonic = bool(np.all(np.diff(counts) <= 0))
        hi, lo = int(counts[0]), int(counts[-1])
    else:
        monotonic = bool(np.all(np.diff(counts) >= 0))
        hi, lo = int(counts[-1]), int(counts[0])
    span = hi / max(lo, 1)

    values = {
        "rule": cfg["rule"],
        "rate_param": param,
        "rate_direction": direction,
        "sweep_factors": cfg["sweep_factors"],
        "param_values": [base[param] * f for f in cfg["sweep_factors"]],
        "counts": counts,
        "span": span,
        "monotonic": monotonic,
        "d27_required_span": cfg["d27_required_span"],
        "d27_pass": bool(monotonic and hi >= cfg["d27_required_span"] * max(lo, 1)),
        "diagnostics": diag_fn(drive, DT, base),
    }
    out = record(cfg["id"], script=__file__, config=cfg["_path"], seed=cfg["seed"],
                 values=values, predictions=cfg.get("predictions"))
    print(f"  {cfg['rule']}: counts {[int(x) for x in counts]}")
    print(f"  span {span:.3f}x against D27's {cfg['d27_required_span']}x  "
          f"monotonic {monotonic}  -> {'PASS' if values['d27_pass'] else 'FAIL'}")
    print(f"written: {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "configs/e5_rate_parameter_span.json")
