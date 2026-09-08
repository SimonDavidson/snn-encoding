"""Preliminary experiment P1 — the count-only baseline (proposal 7.1).

Run on E1 alone, as 7.1 requires, at segment level, across the same budget
points as the recorded E1 sweep.

**The rate-parameter values are taken from a recorded result rather than
recalibrated.** P1 is a comparison against that sweep's temporal condition, so
the operating points must be the same ones; re-bisecting would land a hair
differently and the difference would sit inside equation (40). The config names
the source result and the values, and the script checks the corpus it was run
on matches.

Usage:
    python scripts/run_p1.py configs/p1_count_only_e1_synthetic.json

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-08
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

from spikeenc.harness import (ceiling_accuracies, encode_corpus,
                              encoder_class, mel_dataset,
                              predicted_alignment, run_p1)
from spikeenc.provenance import load_config, record, repo_root
from spikeenc.reference import mel_alignment_prediction
from spikeenc.segments import temporal_information_index
from spikeenc.tasks import LabelSet

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_probe import build_corpus  # noqa: E402


def check_corpus_matches(cfg, source_id):
    """Refuse to compare against a sweep run on a different corpus."""
    path = repo_root() / "results" / f"{source_id}.json"
    with open(path, encoding="utf-8") as fh:
        source = json.load(fh)
    mine = cfg["corpus"]
    theirs = {k: v for k, v in source["corpus"].items() if k in mine}
    if theirs != mine:
        raise SystemExit(
            f"corpus mismatch against {source_id}: {theirs} vs {mine}. P1 "
            "compares against that run's temporal condition and must use the "
            "same corpus.")
    return source


def main(config_path):
    cfg = load_config(config_path)
    source = check_corpus_matches(cfg, cfg["rate_params_from"])
    corpus = build_corpus(cfg["corpus"])
    feat = cfg["featurisation"]
    labelset = LabelSet(corpus.labels)
    offsets = tuple(cfg.get("offsets", (-2, -1, 0)))

    n_segments = sum(len(u.segments) for u in corpus)
    print(f"{corpus.name}: {len(corpus)} utterances, {n_segments} segments, "
          f"{corpus.total_duration:.1f} s")
    print(f"rate parameters from {cfg['rate_params_from']}")

    # R2's ceiling does not depend on the encoder, so it is computed once per
    # split seed and reused across every budget point (see run_p1's docstring
    # on why the cache must be keyed by seed).
    mel_x = mel_dataset(corpus, n_mels=feat["n_mels"], frame=feat["frame"],
                        hop=feat["hop"], alignment=feat["alignment"],
                        context=feat.get("context", 0))
    print(f"tau_phi swept over {feat['taus']} (section 6.1)")
    r2_prediction = mel_alignment_prediction(frame=feat["frame"],
                                             hop=feat["hop"],
                                             alignment=feat["alignment"])
    spiking_prediction = predicted_alignment(
        source["front_end"], cfg["n_channels"], cfg["corpus"]["sample_rate"],
        encoder_class(cfg["encoder"]).DRIVE_KIND, feat["taus"], feat["hop"])
    print(f"offset swept over {list(offsets)}, selected jointly with tau_phi "
          f"on {cfg.get('n_folds', 3)} speaker-disjoint folds inside train "
          f"(D71); declared lags predict "
          + ", ".join(f"tau {k}: {v['offset']}"
                      for k, v in spiking_prediction["by_tau"].items())
          + f", R2: {r2_prediction['offset']}")
    ceilings = {}
    for s in cfg["split_seeds"]:
        ceilings[s] = ceiling_accuracies(
            corpus, mel_x, labelset=labelset, hop=feat["hop"],
            offsets=offsets, test_fraction=cfg["split"]["test_fraction"],
            seed=s, alpha=cfg["probe"]["alpha"],
            n_folds=cfg.get("n_folds", 3),
            c5_radius=cfg.get("c5_radius", 2),
            alignment_prediction=r2_prediction)
        print(f"  ceiling (seed {s}): selected offset "
              f"{ceilings[s]['chosen_offset']} at "
              f"{ceilings[s]['accuracy']:.4f}; profile "
              + ", ".join(f"{k}:{v:.4f}"
                          for k, v in ceilings[s]["test_profile"].items()))

    points = []
    for p in source["points"]:
        t0 = time.time()
        value = p["rate_param"]
        trains = encode_corpus(corpus, cfg["encoder"], [value],
                               cfg["n_channels"], source["front_end"])[float(value)]
        runs = [run_p1(corpus, trains, labelset=labelset,
                       taus=feat["taus"],
                       hop=feat["hop"], context=feat.get("context", 0),
                       test_fraction=cfg["split"]["test_fraction"], seed=s,
                       alpha=cfg["probe"]["alpha"], offsets=offsets,
                       n_mels=feat["n_mels"], frame=feat["frame"],
                       alignment=feat["alignment"], mel_x=mel_x,
                       n_folds=cfg.get("n_folds", 3),
                       c5_radius=cfg.get("c5_radius", 2),
                       alignment_prediction=spiking_prediction,
                       ceiling=ceilings[s])
                for s in cfg["split_seeds"]]

        count = [r["accuracy_count"] for r in runs]
        rate = [r["accuracy_rate"] for r in runs]
        best_t = [r["best_accuracy_temporal"] for r in runs]
        # The ceiling at *its* selected offset, not at the best it reached on
        # test: equation (40)'s denominator is a free parameter of R2's like
        # any other, and D71 applies to it (see `ceiling_accuracies`).
        best_c = [r["accuracy_ceiling"][str(r["best_offset_ceiling"])]
                  for r in runs]
        zero_t = [r["accuracy_temporal"][f'{feat["taus"][0]}']["0"]
                  for r in runs
                  if "0" in r["accuracy_temporal"][f'{feat["taus"][0]}']]
        zero_c = [r["accuracy_ceiling"]["0"] for r in runs
                  if "0" in r["accuracy_ceiling"]]

        point = {
            "target_lambda": p["target_lambda"],
            "achieved_lambda": p["achieved_lambda"],
            "rate_param": value,
            "accuracy_count_mean": float(np.mean(count)),
            "accuracy_count_std": float(np.std(count, ddof=1)),
            "accuracy_rate_mean": float(np.mean(rate)),
            "accuracy_temporal_best_mean": float(np.mean(best_t)),
            "accuracy_temporal_zero_mean": (float(np.mean(zero_t))
                                            if zero_t else None),
            "accuracy_ceiling_best_mean": float(np.mean(best_c)),
            "accuracy_ceiling_zero_mean": (float(np.mean(zero_c))
                                           if zero_c else None),
            "best_tau_by_seed": [r["best_tau_temporal"] for r in runs],
            "best_offset_by_seed": [r["best_offset_temporal"] for r in runs],
            "ceiling_offset_by_seed": [r["best_offset_ceiling"] for r in runs],
            "predicted_offset_by_tau": {
                k: v["offset"] for k, v in spiking_prediction["by_tau"].items()},
            "predicted_offset_ceiling": r2_prediction["offset"],
            "selection_bias_by_seed": [r["selection"]["selection_bias"]
                                       for r in runs],
            "c5_interior_maximum_by_seed": [
                r["c5_alignment"]["temporal"]["validation"]["interior_maximum"]
                for r in runs],
            "tii_at_test_argmax": float(np.mean(
                [r["tii_at_test_argmax"] for r in runs
                 if r["tii_at_test_argmax"] is not None])) if any(
                     r["tii_at_test_argmax"] is not None for r in runs)
                else None,
            "tii_denominator_at_best": float(np.mean(best_c))
                                       - float(np.mean(count)),
            # Equation (40) on the seed means, rather than the mean of
            # per-seed indices: a ratio of small differences is unstable
            # per seed, and averaging the ratio would weight the noisiest
            # seeds most.
            "tii_at_best": temporal_information_index(
                float(np.mean(best_t)), float(np.mean(count)),
                float(np.mean(best_c))),
            "tii_at_zero": (temporal_information_index(
                float(np.mean(zero_t)), float(np.mean(count)),
                float(np.mean(zero_c))) if zero_t and zero_c else None),
            "runs": runs,
            "seconds": time.time() - t0,
        }
        points.append(point)
        tii = point["tii_at_best"]
        print(f"  Lambda {p['achieved_lambda']:8.1f}: count "
              f"{point['accuracy_count_mean']:.4f} rate "
              f"{point['accuracy_rate_mean']:.4f} temporal "
              f"{point['accuracy_temporal_best_mean']:.4f} ceiling "
              f"{point['accuracy_ceiling_best_mean']:.4f}  TII "
              f"{'undefined' if tii is None else f'{tii:+.3f}'} "
              f"[{point['seconds']:.0f} s]")

    values = {
        "experiment": "P1",
        "task": "T1",
        "level": "segment",
        "encoder": cfg["encoder"],
        "rate_params_from": cfg["rate_params_from"],
        "corpus": {"name": corpus.name, "n_utterances": len(corpus),
                   "n_segments": n_segments,
                   "duration_s": corpus.total_duration, **cfg["corpus"]},
        "n_channels": cfg["n_channels"],
        "front_end": source["front_end"],
        "featurisation": feat,
        "probe": cfg["probe"],
        "split": cfg["split"],
        "split_seeds": cfg["split_seeds"],
        "offsets": list(offsets),
        "points": points,
        "caveat": ("Synthetic stand-in corpus, whose phones are stationary "
                   "resonances with no formant transitions. A segment's "
                   "per-channel count vector is therefore very close to a "
                   "complete description of the phone, which is exactly the "
                   "condition 7.1 calls 'a spectral profile task wearing a "
                   "spiking costume'. The index measured here is a property "
                   "of this corpus and must not be read as P1's answer for "
                   "T1; that needs TIMIT (O2)."),
    }
    out = record(cfg["result_id"], script=__file__, config=cfg["_path"],
                 seed=cfg["corpus"].get("seed", 0), values=values,
                 predictions=cfg.get("predictions", []),
                 supersede=cfg.get("supersede", False))
    print(f"recorded -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/run_p1.py <config.json>")
    main(sys.argv[1])
