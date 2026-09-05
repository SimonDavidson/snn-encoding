"""Measure the onset spread the group-delay compensation of D24 leaves behind.

SPEC section 3: "report the measured residual spread alongside any T3 result
taken with compensation on". test_F6 asserts the compensation works; this
records by how much, as data, so the figure can be quoted and the test's
thresholds tightened later from a recorded number rather than a remembered one.

Usage:
    python scripts/measure_group_delay_residual.py \
        configs/front_end_group_delay_residual.json

Author:        Simon Davidson & Claude
Created:       2026-09-05
Last modified: 2026-09-05
"""
import sys

import numpy as np

from spikeenc.frontend import Filterbank
from spikeenc.provenance import load_config, record


def onset_peaks(env, sample_rate):
    """Time of the envelope peak in each channel."""
    return np.array([np.argmax(env[c]) for c in range(env.shape[0])]) / sample_rate


def main(config_path):
    cfg = load_config(config_path)
    fb_kw = cfg["filterbank"]
    fs = fb_kw["sample_rate"]

    n = int(round(cfg["stimulus"]["duration_s"] * fs))
    click = np.zeros(n)
    click[int(n * cfg["stimulus"]["onset_fraction"])] = 1.0

    values = {"by_method": {}}
    arrays = {}
    for method in cfg["envelope"]["methods"]:
        peaks = {}
        for compensate in (False, True):
            fb = Filterbank(**fb_kw, compensate_group_delay=compensate)
            env = fb.envelope(click, method=method,
                              f_cut=cfg["envelope"]["f_cut"],
                              lowpass_order=cfg["envelope"]["lowpass_order"])
            peaks[compensate] = onset_peaks(env, fs)
        unc, com = float(np.ptp(peaks[False])), float(np.ptp(peaks[True]))
        values["by_method"][method] = {
            "uncompensated_spread_s": unc,
            "compensated_spread_s": com,
            "residual_fraction": com / unc if unc else 0.0,
            "test_F6_limit_s": unc / 3.0,
            "test_F6_margin": (unc / 3.0) / com if com else float("inf"),
        }
        arrays[f"{method}_peaks_uncompensated_s"] = peaks[False]
        arrays[f"{method}_peaks_compensated_s"] = peaks[True]

    fb = Filterbank(**fb_kw)
    values["centre_frequencies_hz"] = fb.centre_frequencies
    values["bandwidths_hz"] = fb.bandwidths
    values["gammatone_lag_s"] = fb.group_delays
    values["lowpass_lag_s"] = fb._envelope_stage_lag(
        "rectify_lowpass", cfg["envelope"]["f_cut"],
        cfg["envelope"]["lowpass_order"])

    out = record(
        cfg["id"],
        script=__file__,
        config=cfg["_path"],
        seed=cfg["seed"],
        values=values,
        arrays=arrays,
        predictions=cfg.get("predictions"),
    )
    for method, v in values["by_method"].items():
        print(f"{method:>16}: {v['uncompensated_spread_s']*1000:6.2f} ms -> "
              f"{v['compensated_spread_s']*1000:5.2f} ms  "
              f"(limit {v['test_F6_limit_s']*1000:5.2f} ms, "
              f"margin {v['test_F6_margin']:.2f}x)")
    print(f"written: {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "configs/front_end_group_delay_residual.json")
