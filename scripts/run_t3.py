"""T3, boundary detection (proposal 4.3), on E1 across a budget sweep, with R2.

The context width is swept as well as the budget. That is not a refinement:
a boundary is a relation between adjacent frames, and a per-frame probe with
`context = 0` has no representation of one, so the literal reading of 6.2 is
the condition under which T3 cannot work rather than a baseline it should be
compared against. Sweeping it is what makes the claim measurable instead of
asserted (Q30).

Every condition reports its frame AUC beside its F-score. An F-score alone
cannot distinguish a detector from a metronome running at the right rate, and
on this corpus that distinction turns out to be the whole result.

Usage:
    python scripts/run_t3.py configs/t3_boundary_e1_synthetic.json

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-08
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

from spikeenc.boundaries import score_boundaries, uniform_baseline
from spikeenc.harness import (encode_corpus, encoder_class,
                              predicted_alignment, run_t3)
from spikeenc.provenance import load_config, record, repo_root
from spikeenc.reference import mel_alignment_prediction, mel_features
from spikeenc.tasks import stack_context

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_probe import build_corpus  # noqa: E402


def main(config_path):
    cfg = load_config(config_path)
    source_path = repo_root() / "results" / f"{cfg['rate_params_from']}.json"
    with open(source_path, encoding="utf-8") as fh:
        source = json.load(fh)
    corpus = build_corpus(cfg["corpus"])
    feat = cfg["featurisation"]
    t3 = cfg["t3"]

    print(f"{corpus.name}: {len(corpus)} utterances, "
          f"{sum(len(u.boundaries()) for u in corpus)} interior boundaries")
    print(f"context swept over {cfg['contexts']}, tolerance "
          f"{t3['tolerance'] * 1000:.0f} ms")
    spiking_prediction = predicted_alignment(
        source["front_end"], cfg["n_channels"], cfg["corpus"]["sample_rate"],
        encoder_class(cfg["encoder"]).DRIVE_KIND, [feat["tau"]], feat["hop"])
    r2_prediction = mel_alignment_prediction(frame=feat["frame"],
                                             hop=feat["hop"],
                                             alignment=feat["alignment"])
    print(f"offset swept over {cfg['offsets']}, selected on "
          f"{cfg.get('n_folds', 3)} speaker-disjoint folds inside train (D71)")

    def call(trains, context, features=None):
        return [run_t3(corpus, trains, tau=feat["tau"], hop=feat["hop"],
                       context=context,
                       test_fraction=cfg["split"]["test_fraction"], seed=s,
                       alpha=cfg["probe"]["alpha"],
                       offsets=tuple(cfg["offsets"]),
                       n_folds=cfg.get("n_folds", 3),
                       c5_radius=cfg.get("c5_radius", 2),
                       alignment_prediction=(r2_prediction if features
                                             is not None
                                             else spiking_prediction),
                       tolerance=t3["tolerance"],
                       label_tolerance_frames=t3["label_tolerance_frames"],
                       min_separation=t3["min_separation"],
                       n_thresholds=t3["n_thresholds"],
                       features=features)
                for s in cfg["split_seeds"]]

    def summarise(runs, label, context, lam):
        mean = lambda k: float(np.mean([r[k] for r in runs]))  # noqa: E731
        out = {"condition": label, "context": context,
               "lambda_events_per_s": lam,
               "f_score": mean("f_score"), "r_value": mean("r_value"),
               "precision": mean("precision"), "recall": mean("recall"),
               "over_segmentation": mean("over_segmentation"),
               "frame_auc": mean("frame_auc"),
               "shuffled_f_score": mean("shuffled_f_score"),
               "shuffled_frame_auc": mean("shuffled_frame_auc"),
               "f_score_std": float(np.std([r["f_score"] for r in runs],
                                           ddof=1)),
               "offset_by_seed": [r["best_offset"] for r in runs],
               "predicted_offset": runs[0]["selection"]["predicted"]["by_tau"][
                   next(iter(runs[0]["selection"]["predicted"]["by_tau"]))
               ]["offset"],
               "selection_bias_by_seed": [r["selection"]["selection_bias"]
                                          for r in runs],
               "c5_interior_maximum_by_seed": [
                   r["c5_alignment"]["validation"]["interior_maximum"]
                   for r in runs],
               "threshold_by_seed": [r["selection"]["chosen"]["threshold"]
                                     for r in runs],
               "uniform_baseline_f": float(np.mean(
                   [r["uniform_baseline"]["f_score"] for r in runs])),
               "uniform_baseline_r": float(np.mean(
                   [r["uniform_baseline"]["r_value"] for r in runs])),
               "runs": runs}
        print(f"  {label:>6} ctx {context}: F {out['f_score']:.4f} "
              f"R {out['r_value']:+.4f} AUC {out['frame_auc']:.4f} "
              f"(shuffled F {out['shuffled_f_score']:.4f} AUC "
              f"{out['shuffled_frame_auc']:.4f}) baseline F "
              f"{out['uniform_baseline_f']:.4f}")
        return out

    conditions = []
    for context in cfg["contexts"]:
        mel = np.concatenate([
            stack_context(mel_features(u, n_mels=feat["n_mels"],
                                       frame=feat["frame"], hop=feat["hop"],
                                       alignment=feat["alignment"]), context)
            for u in corpus])
        t0 = time.time()
        for p in source["points"]:
            # Selected by the config's integer target, not by the achieved
            # float: comparing achieved_lambda by equality would silently
            # select nothing the moment a sweep is re-run.
            if p["target_lambda"] not in cfg["target_lambdas"]:
                continue
            trains = encode_corpus(corpus, cfg["encoder"], [p["rate_param"]],
                                   cfg["n_channels"],
                                   source["front_end"])[float(p["rate_param"])]
            conditions.append(summarise(
                call(trains, context), f"E1", context, p["achieved_lambda"]))
        conditions.append(summarise(
            call(trains, context, features=mel), "R2", context, 0.0))
        print(f"    [{time.time() - t0:.0f} s]")

    values = {
        "task": "T3",
        "encoder": cfg["encoder"],
        "rate_params_from": cfg["rate_params_from"],
        "corpus": {"name": corpus.name, "n_utterances": len(corpus),
                   "n_boundaries": sum(len(u.boundaries()) for u in corpus),
                   **cfg["corpus"]},
        "n_channels": cfg["n_channels"],
        "front_end": source["front_end"],
        "featurisation": feat,
        "t3": t3,
        "probe": cfg["probe"],
        "split": cfg["split"],
        "split_seeds": cfg["split_seeds"],
        "contexts": cfg["contexts"],
        "conditions": conditions,
        "caveat": ("Synthetic stand-in corpus. Its phone durations are drawn "
                   "uniformly on [60, 140] ms, so boundaries are quasi-regular "
                   "and evenly spaced guesses at the reference rate score "
                   "well. The uniform baseline is therefore far stronger here "
                   "than on real speech, and no learned detector on this "
                   "corpus should be read as a statement about T3."),
    }
    out = record(cfg["result_id"], script=__file__, config=cfg["_path"],
                 seed=cfg["corpus"].get("seed", 0), values=values,
                 predictions=cfg.get("predictions", []),
                 supersede=cfg.get("supersede", False))
    print(f"recorded -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/run_t3.py <config.json>")
    main(sys.argv[1])
