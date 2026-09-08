"""Preliminary experiment P2 — corruption and dissociation (proposal 7.2).

**This is a rehearsal, not the week 4 decision gate.** Q28 established that the
stand-in corpus cannot answer P1, for reasons that apply here too: its phones
are stationary resonances and its f0 contour is a linear declination, so the
demands the three tasks place on an encoding are weaker and more alike here than
on speech. A degradation profile measured on it exercises the machinery and
finds pipeline faults; it cannot confirm or refute the spanning argument of 4.4,
and the result file says so. CLAUDE.md: "if preliminary experiment P2 shows the
probe battery does not span the demand space, that is a *design* question, not
an implementation one. Log it, raise it, and wait."

Run on E1 alone, as 7.2 requires, at one budget point.

**Alignment is fixed at each task's clean best and held there.** A corruption
should be measured against the same decoder configuration it is corrupting; if
each condition re-picked its own offset, part of every degradation would be the
alignment moving rather than the information being destroyed.

Usage:
    python scripts/run_p2.py configs/p2_corruption_e1_synthetic.json

Author:        Simon Davidson & Claude
Created:       2026-09-08
Last modified: 2026-09-08
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

from spikeenc.harness import encode_corpus, run_t1, run_t2, run_t3
from spikeenc.p2 import apply_corruption, corruption_grid, headroom_lost
from spikeenc.provenance import load_config, record, repo_root

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_probe import build_corpus  # noqa: E402


def score_all(corpus, trains, cfg, offsets):
    """T1, T2 and T3 on one (possibly corrupted) set of trains."""
    feat, seed = cfg["featurisation"], cfg["_seed"]
    t1 = run_t1(corpus, trains, tau=feat["tau"], hop=feat["hop"],
                context=cfg["contexts"]["T1"],
                test_fraction=cfg["split"]["test_fraction"], seed=seed,
                alpha=cfg["probe"]["alpha"],
                control_offsets=(offsets["T1"],))
    t2 = run_t2(corpus, trains, tau=feat["tau"], hop=feat["hop"],
                context=cfg["contexts"]["T2"],
                test_fraction=cfg["split"]["test_fraction"], seed=seed,
                alpha=cfg["probe"]["alpha"],
                ridge_alphas=cfg["t2"]["ridge_alphas"],
                offsets=(offsets["T2"],))
    t3 = run_t3(corpus, trains, tau=feat["tau"], hop=feat["hop"],
                context=cfg["contexts"]["T3"],
                test_fraction=cfg["split"]["test_fraction"], seed=seed,
                alpha=cfg["probe"]["alpha"],
                tolerance=cfg["t3"]["tolerance"],
                label_tolerance_frames=cfg["t3"]["label_tolerance_frames"],
                min_separation=cfg["t3"]["min_separation"],
                n_thresholds=cfg["t3"]["n_thresholds"],
                offsets=(offsets["T3"],))
    return {
        "T1": {"score": t1["accuracy"], "floor": t1["majority_floor"]},
        "T2": {"score": t2["pearson_per_utterance"], "floor": 0.0},
        "T3": {"score": t3["f_score"],
               "floor": t3["uniform_baseline"]["f_score"]},
    }


def main(config_path):
    cfg = load_config(config_path)
    with open(repo_root() / "results" / f"{cfg['rate_params_from']}.json",
              encoding="utf-8") as fh:
        source = json.load(fh)
    corpus = build_corpus(cfg["corpus"])
    point = next(p for p in source["points"]
                 if p["target_lambda"] == cfg["target_lambda"])
    trains = encode_corpus(corpus, cfg["encoder"], [point["rate_param"]],
                           cfg["n_channels"],
                           source["front_end"])[float(point["rate_param"])]

    print(f"{corpus.name}: {len(corpus)} utterances, "
          f"E1 at Lambda = {point['achieved_lambda']:.0f}")
    print("REHEARSAL: this corpus cannot settle the week 4 gate (Q28)")

    # Alignment: taken from the clean condition of the first seed, then held.
    cfg["_seed"] = cfg["split_seeds"][0]
    probe_offsets = cfg["offsets"]
    scan = {}
    for task, run in (("T1", run_t1), ("T3", run_t3)):
        r = run(corpus, trains, tau=cfg["featurisation"]["tau"],
                hop=cfg["featurisation"]["hop"],
                context=cfg["contexts"][task],
                test_fraction=cfg["split"]["test_fraction"],
                seed=cfg["_seed"], alpha=cfg["probe"]["alpha"],
                **({"control_offsets": tuple(probe_offsets)} if task == "T1"
                   else {"offsets": tuple(probe_offsets),
                         "tolerance": cfg["t3"]["tolerance"],
                         "label_tolerance_frames":
                             cfg["t3"]["label_tolerance_frames"],
                         "min_separation": cfg["t3"]["min_separation"],
                         "n_thresholds": cfg["t3"]["n_thresholds"]}))
        if task == "T1":
            by = dict(r["misaligned_accuracy"]); by["0"] = r["accuracy"]
            scan[task] = int(max(by, key=by.get))
        else:
            scan[task] = int(r["best_offset"])
    r2t = run_t2(corpus, trains, tau=cfg["featurisation"]["tau"],
                 hop=cfg["featurisation"]["hop"], context=cfg["contexts"]["T2"],
                 test_fraction=cfg["split"]["test_fraction"],
                 seed=cfg["_seed"], alpha=cfg["probe"]["alpha"],
                 ridge_alphas=cfg["t2"]["ridge_alphas"],
                 offsets=tuple(probe_offsets))
    scan["T2"] = int(r2t["best_offset"])
    print(f"alignment fixed at clean best: {scan}")

    grid = corruption_grid(
        jitter_sigmas=tuple(cfg["p2"]["jitter_sigmas"]),
        channel_deltas=tuple(cfg["p2"]["channel_deltas"]),
        delete_probabilities=tuple(cfg["p2"]["delete_probabilities"]))

    clean, conditions = None, []
    for operator, level in grid:
        t0 = time.time()
        per_seed = []
        for s in cfg["split_seeds"]:
            cfg["_seed"] = s
            rng = np.random.default_rng(cfg["corruption_seed"] + s)
            corrupted = apply_corruption(trains, corpus, operator, level, rng)
            per_seed.append(score_all(corpus, corrupted, cfg, scan))

        entry = {"operator": operator, "level": level, "seconds": time.time() - t0}
        for task in ("T1", "T2", "T3"):
            score = float(np.mean([p[task]["score"] for p in per_seed]))
            floor = float(np.mean([p[task]["floor"] for p in per_seed]))
            entry[task] = {
                "score": score, "floor": floor,
                "std": float(np.std([p[task]["score"] for p in per_seed],
                                    ddof=1)),
                "headroom_lost": (None if clean is None else
                                  headroom_lost(clean[task]["score"], score,
                                                clean[task]["floor"])),
            }
        if operator == "clean":
            clean = entry
        conditions.append(entry)

        lost = {t: entry[t]["headroom_lost"] for t in ("T1", "T2", "T3")}
        label = f"{operator}" + (f"={level}" if level is not None else "")
        print(f"  {label:<34} T1 {entry['T1']['score']:.4f} "
              f"T2 {entry['T2']['score']:+.4f} T3 {entry['T3']['score']:.4f}"
              + ("" if clean is entry else
                 "   lost " + " ".join(
                     f"{t}{'  n/a' if lost[t] is None else f'{lost[t]:+.2f}'}"
                     for t in ("T1", "T2", "T3")))
              + f"  [{entry['seconds']:.0f}s]")

    values = {
        "experiment": "P2", "status": "rehearsal, not the week 4 gate",
        "encoder": cfg["encoder"], "target_lambda": cfg["target_lambda"],
        "achieved_lambda": point["achieved_lambda"],
        "rate_param": point["rate_param"],
        "rate_params_from": cfg["rate_params_from"],
        "corpus": {"name": corpus.name, "n_utterances": len(corpus),
                   **cfg["corpus"]},
        "n_channels": cfg["n_channels"], "front_end": source["front_end"],
        "featurisation": cfg["featurisation"], "contexts": cfg["contexts"],
        "alignment_offsets": scan, "probe": cfg["probe"],
        "split": cfg["split"], "split_seeds": cfg["split_seeds"],
        "corruption_seed": cfg["corruption_seed"],
        "conditions": conditions,
        "caveat": ("REHEARSAL. The stand-in corpus has stationary phones and a "
                   "linear f0 declination, so the demands the three tasks place "
                   "on an encoding are weaker and more alike here than on "
                   "speech (Q28). These profiles exercise the machinery; they "
                   "cannot confirm or refute the spanning argument of 4.4, and "
                   "must not be read as P2's answer or as a test of P-07. "
                   "Degradation is reported as fraction of each task's headroom "
                   "above its own floor, which is a choice the proposal does "
                   "not make (Q36)."),
    }
    out = record(cfg["result_id"], script=__file__, config=cfg["_path"],
                 seed=cfg["corpus"].get("seed", 0), values=values,
                 predictions=cfg.get("predictions", []),
                 supersede=cfg.get("supersede", False))
    print(f"recorded -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/run_p2.py <config.json>")
    main(sys.argv[1])
