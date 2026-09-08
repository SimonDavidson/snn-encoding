"""Run one encoder across a budget sweep on T1, with the Layer 2 controls.

This is the driver for the weeks 1-2 deliverable of proposal section 9. It
takes a committed config, calibrates the encoder's rate parameter to each
target event rate, encodes the corpus, scores T1 with the linear probe at
several split seeds, and records everything through `spikeenc.provenance`.

The sweep is specified in **event rate**, not in rate-parameter values.
Proposal 6.4 compares encoders at matched budget, so a budget is the thing a
config should name; and a rate parameter's useful range depends on the scale of
the drive, which differs by encoder and by compression, so a config naming
parameter values would not be portable across the row of encoders it has to be
run over. `calibrate_rate_param` inverts the relation numerically.

Usage:
    python scripts/run_probe.py configs/probe_e1_t1_synthetic.json

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-08
"""
import sys
import time

import numpy as np

from spikeenc.corpus import synthetic_corpus
from spikeenc.harness import (calibrate_rate_param, encode_corpus,
                              encoder_class, predicted_alignment, run_t1)
from spikeenc.provenance import load_config, record


def build_corpus(spec):
    """Only the synthetic stand-in exists. TIMIT is open O2; when it arrives
    this grows a branch and nothing else in the file changes."""
    kind = spec.get("kind", "synthetic")
    if kind != "synthetic":
        raise NotImplementedError(
            f"corpus kind {kind!r} is not available on this machine. TIMIT is "
            "LDC-licensed and the licence question is open O2; the MANCHESTER "
            "Dataset is unrecorded.")
    return synthetic_corpus(
        n_speakers=spec.get("n_speakers", 12),
        utterances_per_speaker=spec.get("utterances_per_speaker", 4),
        phones_per_utterance=spec.get("phones_per_utterance", 8),
        sample_rate=spec.get("sample_rate", 16000),
        seed=spec.get("seed", 0),
        noise_level=spec.get("noise_level", 0.005))


def main(config_path):
    cfg = load_config(config_path)
    corpus = build_corpus(cfg["corpus"])
    feat = cfg["featurisation"]
    front_end = cfg["front_end"]
    n_channels = cfg["n_channels"]
    encoder = cfg["encoder"]

    offsets = tuple(cfg.get("offsets", (0,)))
    prediction = predicted_alignment(
        front_end, n_channels, cfg["corpus"]["sample_rate"],
        encoder_class(encoder).DRIVE_KIND, [feat["tau"]], feat["hop"])

    print(f"{corpus.name}: {len(corpus)} utterances, "
          f"{corpus.total_duration:.1f} s, {len(corpus.speakers)} speakers")
    predicted = prediction["by_tau"][f"{feat['tau']}"]["offset"]
    print(f"alignment offset swept over {list(offsets)}, selected on "
          f"{cfg.get('n_folds', 3)} speaker-disjoint folds inside train "
          f"(D71); declared lags predict {predicted}")

    points = []
    for target in cfg["target_lambda"]:
        t0 = time.time()
        value, achieved, n_iter = calibrate_rate_param(
            corpus, encoder, float(target), n_channels, front_end,
            encoder_params=cfg.get("encoder_params"),
            bracket=tuple(cfg.get("bracket", (1e-4, 1e2))),
            tol=cfg.get("calibration_tol", 0.05))
        trains = encode_corpus(corpus, encoder, [value], n_channels,
                               front_end)[float(value)]

        # C8 asks for at least three seeds per condition. The probe is
        # deterministic and the corpus is held fixed, so what the seed varies
        # here is the split — which speakers land in test. On a corpus of this
        # many speakers that is the dominant source of spread, and naming it is
        # what D45 requires of any reported figure.
        runs = [run_t1(corpus, trains, tau=feat["tau"], hop=feat["hop"],
                       context=feat.get("context", 0),
                       test_fraction=cfg["split"]["test_fraction"], seed=s,
                       alpha=cfg["probe"]["alpha"], offsets=offsets,
                       n_folds=cfg.get("n_folds", 3),
                       c5_radius=cfg.get("c5_radius", 2),
                       alignment_prediction=prediction)
                for s in cfg["split_seeds"]]

        acc = [r["accuracy"] for r in runs]
        point = {
            "target_lambda": float(target),
            "achieved_lambda": achieved,
            "rate_param": value,
            "calibration_iterations": n_iter,
            "accuracy_mean": float(np.mean(acc)),
            "accuracy_std": float(np.std(acc, ddof=1)) if len(acc) > 1 else 0.0,
            "accuracy_by_seed": acc,
            "offset_by_seed": [r["best_offset"] for r in runs],
            "predicted_offset": predicted,
            "selection_bias_by_seed": [r["selection"]["selection_bias"]
                                       for r in runs],
            "c5_interior_maximum_by_seed": [
                r["c5_alignment"]["validation"]["interior_maximum"]
                for r in runs],
            "runs": runs,
            "seconds": time.time() - t0,
        }
        points.append(point)
        print(f"  Lambda {achieved:8.1f} ({encoder}.{cfg.get('rate_param','')}"
              f"={value:.5g}): accuracy {point['accuracy_mean']:.4f} "
              f"+/- {point['accuracy_std']:.4f}, floor "
              f"{runs[0]['majority_floor']:.4f}, shuffled "
              f"{np.mean([r['shuffled_label_accuracy'] for r in runs]):.4f}, "
              f"offsets {point['offset_by_seed']} "
              f"(predicted {point['predicted_offset']}) "
              f"[{point['seconds']:.0f} s]")

    values = {
        "encoder": encoder,
        "task": "T1",
        "corpus": {"name": corpus.name, "n_utterances": len(corpus),
                   "duration_s": corpus.total_duration,
                   "n_speakers": len(corpus.speakers),
                   **cfg["corpus"]},
        "n_channels": n_channels,
        "front_end": front_end,
        "featurisation": feat,
        "probe": cfg["probe"],
        "split": cfg["split"],
        "split_seeds": cfg["split_seeds"],
        "points": points,
        "caveat": ("Synthetic stand-in corpus. Layer 2 control C1, the "
                   "upper-bound anchor against published TIMIT accuracy, "
                   "cannot be evaluated and has not been. These numbers show "
                   "the pipeline is self-consistent, not that it is "
                   "calibrated against a real corpus."),
    }
    out = record(cfg["result_id"], script=__file__, config=cfg["_path"],
                 seed=cfg["corpus"].get("seed", 0), values=values,
                 predictions=cfg.get("predictions", []),
                 supersede=cfg.get("supersede", False))
    print(f"recorded -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/run_probe.py <config.json>")
    main(sys.argv[1])
