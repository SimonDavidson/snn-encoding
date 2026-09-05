"""Check spikeenc.features.featurise against equation (32) written literally.

featurise accumulates recursively, phi[k] = phi[k-1]*exp(-hop/tau) + ..., which
is O(N+F) rather than O(N*F). That is an optimisation of the defining equation,
so it is checked against a direct transcription of the equation rather than
against its own test. Three properties are recorded:

  agreement        worst relative error against the literal double sum
  order_invariance SPEC section 5 requires it, and test_G8 allows rtol=1e-10;
                   the shipped version is bit-exact under permutation because
                   it lexsorts before accumulating
  polarity_folding split_polarity=False must equal the ON and OFF halves summed

Usage:
    python scripts/verify_featurise_accuracy.py configs/featurise_accuracy.json

Author:        Simon Davidson & Claude
Created:       2026-09-05
Last modified: 2026-09-05
"""
import sys

import numpy as np

from spikeenc import encoders as E
from spikeenc.features import featurise
from spikeenc.provenance import load_config, record, repo_root
from spikeenc.spiketrain import SpikeTrain

sys.path.insert(0, str(repo_root() / "tests"))
from conftest import DT, drive_for  # noqa: E402


def literal_equation_32(train, tau, hop, split_polarity=True):
    """Equation (32) transcribed as written: for each frame, sum the kernel
    over every earlier event. O(N*F) and obviously correct, which is the point."""
    n_frames = int(np.floor(train.duration / hop)) + 1
    n_groups = 2 * train.n_channels if split_polarity else train.n_channels
    out = np.zeros((n_frames, n_groups))
    if len(train) == 0:
        return out
    group = train.channel.astype(np.int64)
    if split_polarity:
        group = group + np.where(train.polarity < 0, train.n_channels, 0)
    for k in range(n_frames):
        t_k = k * hop
        for j in range(len(train)):
            u = t_k - train.time[j]
            if u >= 0.0:
                out[k, group[j]] += np.exp(-u / tau)
    return out


def main(config_path):
    cfg = load_config(config_path)
    tau, hop = cfg["tau"], cfg["hop"]
    rng = np.random.default_rng(cfg["seed"])

    results = {}
    for name in cfg["encoders"]:
        cls_name, kwargs = cfg["encoder_specs"][name]
        cls = getattr(E, cls_name)
        drive = drive_for(cls, n_channels=cfg["n_channels"],
                          duration=cfg["duration_s"], seed=cfg["seed"])
        train = cls(**kwargs).encode_from_drive(drive, DT, seed=cfg["seed"])

        shipped = featurise(train, tau=tau, hop=hop)
        literal = literal_equation_32(train, tau, hop)
        denom = np.maximum(np.abs(literal), cfg["relative_error_floor"])
        rel = float(np.max(np.abs(shipped - literal) / denom))

        perm = rng.permutation(len(train))
        shuffled = SpikeTrain(train.channel[perm], train.time[perm],
                              train.polarity[perm], train.n_channels,
                              train.duration, train.params)
        permuted = featurise(shuffled, tau=tau, hop=hop)

        folded = featurise(train, tau=tau, hop=hop, split_polarity=False)
        halves = shipped[:, :train.n_channels] + shipped[:, train.n_channels:]
        fold_err = float(np.max(np.abs(folded - halves)))

        results[name] = {
            "n_events": len(train),
            "worst_relative_error_vs_equation_32": rel,
            "bit_identical_under_permutation": bool(np.array_equal(shipped, permuted)),
            "max_abs_error_under_permutation": float(np.max(np.abs(shipped - permuted))),
            "polarity_folding_max_abs_error": fold_err,
        }

    values = {"tau": tau, "hop": hop, "by_encoder": results,
              "worst_relative_error_overall": max(
                  r["worst_relative_error_vs_equation_32"] for r in results.values())}
    out = record(cfg["id"], script=__file__, config=cfg["_path"], seed=cfg["seed"],
                 values=values, predictions=cfg.get("predictions"))

    print(f"{'encoder':>8} {'events':>7} {'rel err vs eq32':>16} "
          f"{'bit-exact perm':>15} {'fold err':>10}")
    for name, r in results.items():
        print(f"{name:>8} {r['n_events']:>7} "
              f"{r['worst_relative_error_vs_equation_32']:>16.2e} "
              f"{str(r['bit_identical_under_permutation']):>15} "
              f"{r['polarity_folding_max_abs_error']:>10.2e}")
    print(f"written: {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "configs/featurise_accuracy.json")
