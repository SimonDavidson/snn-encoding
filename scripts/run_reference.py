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
Last modified: 2026-09-07
"""
import sys
import time

import numpy as np

from spikeenc.harness import run_t1_reference
from spikeenc.provenance import load_config, record
from spikeenc.reference import feature_bandwidth_bps

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

    conditions = []
    for alignment in cfg["alignments"]:
        t0 = time.time()
        runs = [run_t1_reference(
            corpus, n_mels=feat["n_mels"], frame=feat["frame"],
            hop=feat["hop"], alignment=alignment,
            context=feat.get("context", 0), f_min=feat.get("f_min", 50.0),
            f_max=feat.get("f_max", 8000.0),
            test_fraction=cfg["split"]["test_fraction"], seed=s,
            alpha=cfg["probe"]["alpha"],
            bits_per_feature=cfg.get("bits_per_feature", 32),
            control_offsets=tuple(cfg.get("control_offsets", (-1, 1))))
            for s in cfg["split_seeds"]]

        acc = [r["accuracy"] for r in runs]
        offsets = {k: float(np.mean([r["misaligned_accuracy"][k] for r in runs]))
                   for k in runs[0]["misaligned_accuracy"]}
        best = max({**offsets, "0": float(np.mean(acc))}.items(),
                   key=lambda kv: kv[1])
        cond = {
            "alignment": alignment,
            "accuracy_mean": float(np.mean(acc)),
            "accuracy_std": float(np.std(acc, ddof=1)) if len(acc) > 1 else 0.0,
            "accuracy_by_seed": acc,
            "offset_profile": offsets,
            "best_offset": best[0],
            "best_offset_accuracy": best[1],
            "runs": runs,
            "seconds": time.time() - t0,
        }
        conditions.append(cond)
        print(f"  {alignment:8s}: accuracy {cond['accuracy_mean']:.4f} "
              f"+/- {cond['accuracy_std']:.4f}, floor "
              f"{runs[0]['majority_floor']:.4f}, shuffled "
              f"{np.mean([r['shuffled_label_accuracy'] for r in runs]):.4f}, "
              f"best offset {best[0]} at {best[1]:.4f} "
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
