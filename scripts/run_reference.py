"""Run R2, the non-spiking upper bound of proposal 5.9, on T1.

R2 is the control every other number is reported against. Proposal 5.9: "Every
accuracy in the study should be reported as a gap to this bound rather than in
isolation. Without it, a phone accuracy figure means nothing."

The corpus, the split seeds and the probe settings must match the spiking run
this is a bound for, or the gap measures the configuration rather than the
encoding. They are given in the config rather than derived, and the script
prints them so a mismatch is visible in the log rather than only in the file.

Both window alignments of `reference.mel_features` are run. The choice is not
fixed by 5.9 and Q24 measured a one-frame misalignment as worth 4.5 to 18.5
accuracy points, so it is measured rather than assumed.

Usage:
    python scripts/run_reference.py configs/reference_r2_t1_synthetic.json

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-08
"""
import sys
import time

import numpy as np

from spikeenc.harness import run_t1_reference
from spikeenc.provenance import load_config, record
from spikeenc.reference import (feature_bandwidth_bps,
                                mel_alignment_prediction)

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from run_probe import build_corpus  # noqa: E402  — one corpus builder, not two


def main(config_path):
    cfg = load_config(config_path)
    corpus = build_corpus(cfg["corpus"])
    feat = cfg["features"]

    print(f"{corpus.name}: {len(corpus)} utterances, "
          f"{corpus.total_duration:.1f} s, {len(corpus.speakers)} speakers")
    print(f"R2: {feat['n_mels']} mel bands, {feat['frame'] * 1000:.0f} ms "
          f"window, {feat['hop'] * 1000:.0f} ms hop, context "
          f"{feat.get('context', 0)}")

    offsets = tuple(cfg.get("offsets", (0,)))
    print(f"alignment offset swept over {list(offsets)}, selected on "
          f"{cfg.get('n_folds', 3)} speaker-disjoint folds inside train (D71)")

    conditions = []
    for alignment in cfg["alignments"]:
        t0 = time.time()
        prediction = mel_alignment_prediction(frame=feat["frame"],
                                              hop=feat["hop"],
                                              alignment=alignment)
        runs = [run_t1_reference(
            corpus, n_mels=feat["n_mels"], frame=feat["frame"],
            hop=feat["hop"], alignment=alignment,
            context=feat.get("context", 0), f_min=feat.get("f_min", 50.0),
            f_max=feat.get("f_max", 8000.0),
            test_fraction=cfg["split"]["test_fraction"], seed=s,
            alpha=cfg["probe"]["alpha"],
            bits_per_feature=cfg.get("bits_per_feature", 32),
            offsets=offsets, n_folds=cfg.get("n_folds", 3),
            c5_radius=cfg.get("c5_radius", 2),
            alignment_prediction=prediction)
            for s in cfg["split_seeds"]]

        acc = [r["accuracy"] for r in runs]
        # The test-side profile, averaged over seeds. Reported, never selected
        # on: each run's offset was chosen on folds inside its own training
        # split (D71), and the gap between the two is recorded as the bias.
        profile = {k: float(np.mean([r["selection"]["test_profile"][k]
                                     for r in runs]))
                   for k in runs[0]["selection"]["test_profile"]}
        cond = {
            "alignment": alignment,
            "accuracy_mean": float(np.mean(acc)),
            "accuracy_std": float(np.std(acc, ddof=1)) if len(acc) > 1 else 0.0,
            "accuracy_by_seed": acc,
            "offset_profile": profile,
            "offset_by_seed": [r["best_offset"] for r in runs],
            "predicted_offset": prediction["offset"],
            "selection_bias_by_seed": [r["selection"]["selection_bias"]
                                       for r in runs],
            "c5_interior_maximum_by_seed": [
                r["c5_alignment"]["validation"]["interior_maximum"]
                for r in runs],
            "test_argmax_offset": max(profile, key=profile.get),
            "test_argmax_accuracy": max(profile.values()),
            "runs": runs,
            "seconds": time.time() - t0,
        }
        conditions.append(cond)
        print(f"  {alignment:8s}: accuracy {cond['accuracy_mean']:.4f} "
              f"+/- {cond['accuracy_std']:.4f}, floor "
              f"{runs[0]['majority_floor']:.4f}, shuffled "
              f"{np.mean([r['shuffled_label_accuracy'] for r in runs]):.4f}, "
              f"offsets {cond['offset_by_seed']} "
              f"(predicted {cond['predicted_offset']}) "
              f"[{cond['seconds']:.0f} s]")

    values = {
        "reference": "R2",
        "task": "T1",
        "corpus": {"name": corpus.name, "n_utterances": len(corpus),
                   "duration_s": corpus.total_duration,
                   "n_speakers": len(corpus.speakers), **cfg["corpus"]},
        "features": feat,
        "probe": cfg["probe"],
        "split": cfg["split"],
        "split_seeds": cfg["split_seeds"],
        "feature_bandwidth_bps": feature_bandwidth_bps(
            feat["n_mels"], feat["hop"], cfg.get("bits_per_feature", 32)),
        "conditions": conditions,
        "compare_with": cfg.get("compare_with"),
        "caveat": ("Synthetic stand-in corpus. Layer 2 control C1 anchors R2 "
                   "against published TIMIT accuracy (82.68 per cent frame "
                   "level, Ponghiran and Roy) and cannot be evaluated here: "
                   "R2 is the condition C1 is really about, so until TIMIT "
                   "arrives this bound is internally comparable only."),
    }
    out = record(cfg["result_id"], script=__file__, config=cfg["_path"],
                 seed=cfg["corpus"].get("seed", 0), values=values,
                 predictions=cfg.get("predictions", []),
                 supersede=cfg.get("supersede", False))
    print(f"recorded -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/run_reference.py <config.json>")
    main(sys.argv[1])
