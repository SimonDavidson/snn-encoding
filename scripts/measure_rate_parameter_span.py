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
Last modified: 2026-09-07
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


def e5_cycle_divisor_count(drive, dt, params):
    """SPEC 4.6 under D40: upward zero crossings of the subband, discard those
    where the internal envelope does not exceed `threshold`, keep every
    `cycle_divisor`-th survivor counting from the first in that channel, then
    apply `refractory`.

    The gating envelope is half-wave rectification then a fourth-order
    Butterworth at `env_cutoff` (D41), computed inside the encoder because
    encode_from_drive receives the subband waveform.
    """
    from scipy.signal import butter, sosfilt
    fs = 1.0 / dt
    sos = butter(4, min(params["env_cutoff"] / (0.5 * fs), 0.99),
                 btype="low", output="sos")
    env = sosfilt(sos, np.maximum(drive, 0.0), axis=-1)
    k = int(params["cycle_divisor"])
    total = 0
    for c in range(drive.shape[0]):
        x = drive[c]
        crossings = np.where((x[:-1] <= 0.0) & (x[1:] > 0.0))[0] + 1
        survivors = [i for i in crossings if env[c, i] > params["threshold"]]
        kept = survivors[::k]
        last = -(1 << 40)
        for i in kept:
            # Integer sample difference, matching _integrate_and_fire. Comparing
            # absolute times is not shift-invariant: (i+s)*dt - (j+s)*dt is not
            # bit-identical to i*dt - j*dt, so an interval of exactly
            # refractory/dt samples flips across a shift and breaks test_G4.
            if (i - last) * dt >= params["refractory"]:
                total += 1
                last = i
    return total


def e5_cycle_divisor_diagnostics(drive, dt, params):
    from scipy.signal import butter, sosfilt
    fs = 1.0 / dt
    sos = butter(4, min(params["env_cutoff"] / (0.5 * fs), 0.99),
                 btype="low", output="sos")
    env = sosfilt(sos, np.maximum(drive, 0.0), axis=-1)
    n_cross = int(np.sum((drive[:, :-1] <= 0.0) & (drive[:, 1:] > 0.0)))
    gated = 0
    for c in range(drive.shape[0]):
        x = drive[c]
        idx = np.where((x[:-1] <= 0.0) & (x[1:] > 0.0))[0] + 1
        gated += int(np.sum(env[c, idx] > params["threshold"]))
    return {
        "upward_zero_crossings_total": n_cross,
        "survivors_after_envelope_gate": gated,
        "note": ("cycle_divisor moves the count as 1/k; the span is not exactly "
                 "1/k because refractory is already binding in the high "
                 "channels at k = 1 (SPEC 4.6, D40)"),
    }


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


def e6_e_frac_count(drive, dt, params):
    """SPEC 4.7 under D43: at most one event per channel per frame, emitted
    where the frame energy *strictly* exceeds `e_frac * E_max`, with `E_max`
    the largest frame energy over all channels and all frames of the utterance.

    Reimplemented here rather than imported from `spikeenc.encoders`, which is
    the whole point of this script: an independent count of the same rule is a
    cross-check on the encoder, and `e6_e_frac_diagnostics` reports whether the
    two agree. The earlier `e6_frame_energy` rule is left in place rather than
    edited -- it measured the absolute `e_min` that Q14 retired, and its result
    stays visible in the manifest, as DECISIONS.md does for superseded entries.
    """
    E = _e6_energies(drive, dt, params)
    if E.size == 0:
        return 0
    return int(np.sum(E > params["e_frac"] * E.max()))


def e6_e_frac_diagnostics(drive, dt, params):
    """Diagnostics for the relative gate, with every figure carrying the
    definition of what was measured, as section 8 of the validation protocol
    now requires (D45).

    That discipline is why the scale-invariance block reports decades of drive
    *amplitude* and decades of frame *energy* separately. Q14 recorded the same
    sweep as "five decades" and proposal 5.6 repeats it; the sweep is five
    scale *points*, spanning four decades of amplitude and eight of energy, and
    an undefined "decades" is exactly what D45 was written for.
    """
    from spikeenc import encoders as enc_mod

    E = _e6_energies(drive, dt, params)
    e_max = float(E.max())
    gate = params["e_frac"] * e_max

    # The relative gate should give identical counts at any input level. This
    # is the claim proposal 5.6 rests the absolute-to-relative change on.
    scales = [1e-2, 1e-1, 1.0, 1e1, 1e2]
    scale_counts, scale_e_max = [], []
    for s in scales:
        Es = _e6_energies(drive * s, dt, params)
        scale_counts.append(int(np.sum(Es > params["e_frac"] * Es.max())))
        scale_e_max.append(float(Es.max()))

    # Independent-reimplementation check, in the spirit of validation layer 3:
    # the encoder's own count against this script's simulation of the rule.
    e6 = enc_mod.TTFS(n_channels=drive.shape[0], e_frac=params["e_frac"],
                      frame=params["frame"], hop=params["hop"])
    train, state = e6.encode_from_drive(drive, dt, return_state=True)
    simulated = e6_e_frac_count(drive, dt, params)

    return {
        "ceiling_n_ch_times_n_frames": int(E.size),
        "frame_energy_min": float(E.min()),
        "frame_energy_p1": float(np.percentile(E, 1)),
        "frame_energy_median": float(np.median(E)),
        "frame_energy_max": e_max,
        "gate_at_base_e_frac": gate,
        "gate_log10_ratio_to_quietest_frame": float(np.log10(E.min() / gate)),
        "gate_definition": ("gate = e_frac * E_max, E_max the largest frame "
                            "energy over all channels and all frames; "
                            "gate_log10_ratio_to_quietest_frame is "
                            "log10(min frame energy / gate), so a negative "
                            "value means the gate sits above the quietest "
                            "frame and therefore gates something"),
        "scale_invariance": {
            "drive_amplitude_scales": scales,
            "n_scale_points": len(scales),
            "decades_of_drive_amplitude": float(np.log10(max(scales)
                                                         / min(scales))),
            "decades_of_frame_energy": float(np.log10(max(scale_e_max)
                                                      / min(scale_e_max))),
            "frame_energy_max_per_scale": scale_e_max,
            "event_count_per_scale_at_base_e_frac": scale_counts,
            "counts_identical_across_scales": len(set(scale_counts)) == 1,
            "definition": ("the drive is multiplied by each scale and the full "
                           "rule re-run; energy scales as the square of "
                           "amplitude, so the two decade figures differ by a "
                           "factor of two by construction"),
        },
        "encoder_cross_check": {
            "encoder_event_count": len(train),
            "simulated_event_count": simulated,
            "counts_agree": bool(len(train) == simulated),
            "frame_energy_max_abs_difference": float(
                np.max(np.abs(state["energy"] - E))) if E.size else 0.0,
            "definition": ("spikeenc.encoders.TTFS at the base e_frac against "
                           "this script's independent simulation of the same "
                           "SPEC 4.7 rule, on the same drive"),
        },
        "note": ("the relative gate is scale-free, so unlike the absolute "
                 "e_min of the superseded e6_rate_parameter_span run it cannot "
                 "drift below the signal when the corpus changes"),
    }

RULES = {"e5_cycle_divisor": (e5_cycle_divisor_count, e5_cycle_divisor_diagnostics),
         "e5_deterministic": (e5_count, e5_diagnostics),
         "e6_frame_energy": (e6_count, e6_diagnostics),
         "e6_e_frac": (e6_e_frac_count, e6_e_frac_diagnostics)}


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
