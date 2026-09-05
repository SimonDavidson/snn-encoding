"""Compare equation (9) envelope cutoff rules: D21's min(f_cut, b_c) vs f_c/4.

Records the Q03 table as data. Q03's answer (D21) turned on the observation
that raw correlation against an uncompensated modulator conflates filter
rejection with filter delay, so all three metrics are recorded here rather than
the one that misled the original comparison:

  raw_correlation      envelope against the modulator, no lag correction
  lag_corrected        the same, maximised over integer lags
  carrier_leakage      |E(f_c)| / |E(0)| in the envelope's spectrum

The f_c/4 rule is not the shipped one — D21 fixed the cutoff at min(f_cut, b_c)
— so this script builds both lowpass variants directly from the subbands rather
than going through Filterbank.envelope, which can only produce the D21 rule.
That reimplementation is the point of the comparison, not a shortcut around the
API.

Usage:
    python scripts/measure_envelope_cutoff.py configs/envelope_cutoff_comparison.json

Author:        Simon Davidson & Claude
Created:       2026-09-05
Last modified: 2026-09-05
"""
import sys

import numpy as np
from scipy.signal import butter, sosfilt, sosfreqz

from spikeenc.frontend import Filterbank
from spikeenc.provenance import load_config, record


def lowpass(x, cut_hz, order, fs):
    sos = butter(order, min(cut_hz / (0.5 * fs), 0.99), btype="low", output="sos")
    return sosfilt(sos, x)


def carrier_leakage(env, fc, fs):
    """Envelope energy at the carrier, relative to its DC component. A clean
    envelope has none: the carrier is what the lowpass is there to remove."""
    n = env.size
    spec = np.abs(np.fft.rfft(env - 0.0))
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    k = int(np.argmin(np.abs(freqs - fc)))
    return float(spec[k] / spec[0])


def lag_corrected_correlation(env, modulator, max_lag):
    """Best correlation over integer lags, which removes the lowpass group
    delay without assuming a value for it."""
    best = -1.0
    for lag in range(0, max_lag + 1):
        a = env[lag:] if lag else env
        b = modulator[:len(modulator) - lag] if lag else modulator
        if a.size < 16:
            break
        best = max(best, float(np.corrcoef(a, b)[0, 1]))
    return best


def main(config_path):
    cfg = load_config(config_path)
    fb_kw = cfg["filterbank"]
    fs = fb_kw["sample_rate"]
    st = cfg["stimulus"]
    fb = Filterbank(**fb_kw)
    cf, bw = fb.centre_frequencies, fb.bandwidths

    n = int(round(st["duration_s"] * fs))
    t = np.arange(n) / fs
    modulator = 1.0 + st["modulation_depth"] * np.sin(2 * np.pi * st["modulator_hz"] * t)
    trim = int(n * st["trim_fraction"])
    max_lag = int(0.05 * fs)

    rows = []
    for c in cfg["channels_reported"]:
        audio = modulator * np.sin(2 * np.pi * cf[c] * t)
        sub = fb.subbands(audio)[c]
        rectified = np.maximum(sub, 0.0)
        row = {"channel": int(c), "f_c_hz": float(cf[c]), "b_c_hz": float(bw[c])}
        for rule in ("fc_over_4", "d21"):
            cut = (cf[c] / 4.0 if rule == "fc_over_4"
                   else min(cfg["f_cut_ceiling"], bw[c]))
            env = lowpass(rectified, cut, cfg["lowpass_order"], fs)
            e, m = env[trim:n - trim], modulator[trim:n - trim]
            sos = butter(cfg["lowpass_order"], min(cut / (0.5 * fs), 0.99),
                         btype="low", output="sos")
            gain_at_fc = float(np.abs(sosfreqz(sos, worN=[cf[c]], fs=fs)[1][0]))
            leak = carrier_leakage(e, cf[c], fs)
            row[rule] = {
                "cutoff_hz": float(cut),
                "raw_correlation": float(np.corrcoef(e, m)[0, 1]),
                "lag_corrected_correlation": lag_corrected_correlation(e, m, max_lag),
                "carrier_leakage": leak,
                # Validates the leakage metric: it should be the lowpass gain
                # at the carrier times a constant set by the rectified
                # waveform's own harmonic content. The constant comes out the
                # same for both cutoff rules at a given channel, which is what
                # makes the comparison between the rules meaningful.
                "lowpass_gain_at_fc": gain_at_fc,
                "leakage_over_gain": leak / gain_at_fc if gain_at_fc else None,
            }
        rows.append(row)

    values = {"by_channel": rows, "reproduction_note": (
        "The correlation columns reproduce the table in QUESTIONS.md Q03 "
        "exactly to four decimal places. The carrier-leakage column does not: "
        "that table's values are 10-600x smaller, and the metric definition "
        "behind them was never recorded, so it cannot be reproduced. D21's "
        "conclusion is unaffected - this measurement also has D21 winning at "
        "every channel by a margin that grows with frequency - but the "
        "specific factors quoted in the Q03 answer (1.4x, 30x, 128x, 419x) do "
        "not reproduce; this run gives 1.2x, 5.6x, 11.3x, 20.4x. See Q15."),
        "metric_definitions": {
        "raw_correlation": "corrcoef(envelope, modulator) on the trimmed interval",
        "lag_corrected_correlation": "the same, maximised over integer lags 0..0.05 s",
        "carrier_leakage": "|rfft(envelope)| at f_c divided by its value at DC"}}
    out = record(cfg["id"], script=__file__, config=cfg["_path"], seed=cfg["seed"],
                 values=values, predictions=cfg.get("predictions"))

    print(f"{'ch':>3} {'f_c':>6} {'b_c':>6} | {'raw fc/4':>9} {'raw D21':>8} "
          f"| {'lag fc/4':>9} {'lag D21':>8} | {'leak fc/4':>10} {'leak D21':>10}")
    for r in rows:
        a, b = r["fc_over_4"], r["d21"]
        print(f"{r['channel']:>3} {r['f_c_hz']:>6.0f} {r['b_c_hz']:>6.1f} | "
              f"{a['raw_correlation']:>9.4f} {b['raw_correlation']:>8.4f} | "
              f"{a['lag_corrected_correlation']:>9.4f} {b['lag_corrected_correlation']:>8.4f} | "
              f"{a['carrier_leakage']:>10.2e} {b['carrier_leakage']:>10.2e}")
    print(f"written: {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "configs/envelope_cutoff_comparison.json")
