"""T2, fundamental frequency contour (proposal 4.2), on E1 with R2 alongside.

Two correlations are reported at every condition. The headline is the mean
within-utterance Pearson r; the pooled figure is carried beside it because the
gap between them is how much of a pooled correlation is voice height rather
than contour, and on this corpus that gap is about 0.2 (Q32).

Context is swept as for T3. 4.2 grounds T2 in phase locking to the glottal
cycle, which is a within-frame property, so unlike T3 there is no structural
reason context should be needed — measuring it is how that gets checked rather
than assumed.

Usage:
    python scripts/run_t2.py configs/t2_f0_contour_e1_synthetic.json

Author:        Simon Davidson & Claude
Created:       2026-09-08
Last modified: 2026-09-08
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

from spikeenc.harness import (encode_corpus, encoder_class,
                              predicted_alignment, run_t2)
from spikeenc.provenance import load_config, record, repo_root
from spikeenc.reference import mel_alignment_prediction, mel_features
from spikeenc.tasks import stack_context

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_probe import build_corpus  # noqa: E402


def main(config_path):
    cfg = load_config(config_path)
    with open(repo_root() / "results" / f"{cfg['rate_params_from']}.json",
              encoding="utf-8") as fh:
        source = json.load(fh)
    corpus = build_corpus(cfg["corpus"])
    feat, t2 = cfg["featurisation"], cfg["t2"]

    voiced_frac = float(np.mean([u.voiced.mean() for u in corpus]))
    print(f"{corpus.name}: {len(corpus)} utterances, "
          f"{voiced_frac:.1%} voiced frames")
    print(f"context swept over {cfg['contexts']}, headline is the mean "
          f"within-utterance Pearson r")
    spiking_prediction = predicted_alignment(
        source["front_end"], cfg["n_channels"], cfg["corpus"]["sample_rate"],
        encoder_class(cfg["encoder"]).DRIVE_KIND, [feat["tau"]], feat["hop"])
    r2_prediction = mel_alignment_prediction(frame=feat["frame"],
                                             hop=feat["hop"],
                                             alignment=feat["alignment"])
    print(f"offset swept over {cfg['offsets']}, selected on "
          f"{cfg.get('n_folds', 3)} speaker-disjoint folds inside train "
          f"(D71); declared lags predict "
          f"{spiking_prediction['by_tau'][f'{feat["tau"]}']['offset']} for "
          f"E-conditions and {r2_prediction['offset']} for R2")

    def call(trains, context, features=None):
        return [run_t2(corpus, trains, tau=feat["tau"], hop=feat["hop"],
                       context=context,
                       test_fraction=cfg["split"]["test_fraction"], seed=s,
                       alpha=cfg["probe"]["alpha"],
                       ridge_alpha=t2["ridge_alpha"],
                       ridge_alphas=t2.get("ridge_alphas"),
                       ref=t2["semitone_ref_hz"],
                       min_frames=t2["min_frames_per_utterance"],
                       offsets=tuple(cfg["offsets"]),
                       n_folds=cfg.get("n_folds", 3),
                       c5_radius=cfg.get("c5_radius", 2),
                       alignment_prediction=(r2_prediction if features
                                             is not None
                                             else spiking_prediction),
                       features=features)
                for s in cfg["split_seeds"]]

    def summarise(runs, label, context, lam):
        mean = lambda k: float(np.nanmean([r[k] for r in runs]))  # noqa: E731
        out = {"condition": label, "context": context,
               "lambda_events_per_s": lam,
               "pearson_per_utterance": mean("pearson_per_utterance"),
               "pearson_pooled": mean("pearson_pooled"),
               "rmse_semitones": mean("rmse_semitones"),
               "floor_rmse_semitones": mean("floor_rmse_semitones"),
               "shuffled_pearson_per_utterance":
                   mean("shuffled_pearson_per_utterance"),
               "shuffled_pearson_pooled": mean("shuffled_pearson_pooled"),
               "voicing_accuracy": mean("voicing_accuracy"),
               "voicing_floor": mean("voicing_floor"),
               "ridge_alpha_chosen": [r["ridge_alpha_chosen"] for r in runs],
               "offset_by_seed": [r["best_offset"] for r in runs],
               "predicted_offset": runs[0]["selection"]["predicted"]["by_tau"][
                   next(iter(runs[0]["selection"]["predicted"]["by_tau"]))
               ]["offset"],
               "selection_bias_by_seed": [r["selection"]["selection_bias"]
                                          for r in runs],
               "c5_interior_maximum_by_seed": [
                   r["c5_alignment"]["validation"]["interior_maximum"]
                   for r in runs],
               "pearson_std": float(np.nanstd(
                   [r["pearson_per_utterance"] for r in runs], ddof=1)),
               "runs": runs}
        out["voice_height_share"] = (out["pearson_pooled"]
                                     - out["pearson_per_utterance"])
        print(f"  {label:>2} ctx {context}: r/utt {out['pearson_per_utterance']:+.4f} "
              f"pooled {out['pearson_pooled']:+.4f} (gap "
              f"{out['voice_height_share']:+.4f}) RMSE "
              f"{out['rmse_semitones']:.3f} st vs floor "
              f"{out['floor_rmse_semitones']:.3f}  voicing "
              f"{out['voicing_accuracy']:.4f}  shuffled r/utt "
              f"{out['shuffled_pearson_per_utterance']:+.4f}  offsets "
              f"{out['offset_by_seed']} (pred {out['predicted_offset']}) "
              f"alpha {out['ridge_alpha_chosen']}")
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
            if p["target_lambda"] not in cfg["target_lambdas"]:
                continue
            trains = encode_corpus(corpus, cfg["encoder"], [p["rate_param"]],
                                   cfg["n_channels"],
                                   source["front_end"])[float(p["rate_param"])]
            conditions.append(summarise(call(trains, context), "E1", context,
                                        p["achieved_lambda"]))
        conditions.append(summarise(call(trains, context, features=mel), "R2",
                                    context, 0.0))
        print(f"    [{time.time() - t0:.0f} s]")

    values = {
        "task": "T2",
        "encoder": cfg["encoder"],
        "rate_params_from": cfg["rate_params_from"],
        "headline": "pearson_per_utterance",
        "corpus": {"name": corpus.name, "n_utterances": len(corpus),
                   "voiced_fraction": voiced_frac, **cfg["corpus"]},
        "n_channels": cfg["n_channels"],
        "front_end": source["front_end"],
        "featurisation": feat, "t2": t2,
        "probe": cfg["probe"], "split": cfg["split"],
        "split_seeds": cfg["split_seeds"], "contexts": cfg["contexts"],
        "conditions": conditions,
        "caveat": ("Synthetic stand-in corpus, whose f0 contour is a linear "
                   "declination within each utterance and moves only about one "
                   "to three semitones. Real speech carries accents and "
                   "question intonation and moves far more, so the "
                   "within-utterance correlation here is measured against a "
                   "contour with little to track. The reference is the "
                   "commanded f0 and is exact, so the two-tracker noise floor "
                   "4.2 requires does not apply and has not been measured; it "
                   "must be before any TIMIT figure is reported."),
    }
    out = record(cfg["result_id"], script=__file__, config=cfg["_path"],
                 seed=cfg["corpus"].get("seed", 0), values=values,
                 predictions=cfg.get("predictions", []),
                 supersede=cfg.get("supersede", False))
    print(f"recorded -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/run_t2.py <config.json>")
    main(sys.argv[1])
