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
        abs_err = np.abs(shipped - literal)
        # Two relative measures, because they answer different questions and
        # quoting one without saying which is what made the original 9.4e-16
        # unreproducible. `pointwise` divides by each entry's own value and so
        # is dominated by entries that have decayed to near nothing;
        # `scaled` divides by the largest value in the array, which is the
        # error that matters to a probe consuming these features.
        floor = cfg["relative_error_floor"]
        rel_pointwise = float(np.max(abs_err / np.maximum(np.abs(literal), floor)))
        scale = float(np.max(np.abs(literal))) or 1.0
        rel_scaled = float(np.max(abs_err) / scale)

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
            "worst_relative_error_pointwise": rel_pointwise,
            "worst_relative_error_scaled_to_array_max": rel_scaled,
            "worst_absolute_error": float(np.max(abs_err)),
            "largest_feature_value": scale,
            "bit_identical_under_permutation": bool(np.array_equal(shipped, permuted)),
            "max_abs_error_under_permutation": float(np.max(np.abs(shipped - permuted))),
            "polarity_folding_max_abs_error": fold_err,
        }

    values = {
        "tau": tau, "hop": hop, "by_encoder": results,
        "worst_relative_error_pointwise_overall": max(
            r["worst_relative_error_pointwise"] for r in results.values()),
        "worst_relative_error_scaled_overall": max(
            r["worst_relative_error_scaled_to_array_max"] for r in results.values()),
        "reproduction_note": (
            "NOTEBOOK.md 2026-09-04 quotes 9.4e-16 as the worst relative error "
            "against equation (32). That identifies the normalisation the "
            "original used: it is the scaled measure, and E4 gives 9.39e-16. "
            "But it was not the worst of the three - E3 gives 1.31e-15 under "
            "the same measure, about 40 per cent larger. The conclusion is "
            "unaffected, since agreement is a few ulp of the largest feature "
            "value either way, but the figure as quoted understates the worst "
            "case. The pointwise measure, about 2e-14, is a different question "
            "and is recorded alongside so the two cannot be confused again. "
            "See Q15."),
        "definitions": {
            "worst_relative_error_pointwise": "max |shipped-literal| / max(|literal|, floor), over all entries",
            "worst_relative_error_scaled_to_array_max": "max |shipped-literal| / max(|literal|), per encoder"}}
    out = record(cfg["id"], script=__file__, config=cfg["_path"], seed=cfg["seed"],
                 values=values, predictions=cfg.get("predictions"))

    print(f"{'encoder':>8} {'events':>7} {'rel pointwise':>14} {'rel scaled':>11} "
          f"{'bit-exact perm':>15} {'fold err':>10}")
    for name, r in results.items():
        print(f"{name:>8} {r['n_events']:>7} "
              f"{r['worst_relative_error_pointwise']:>14.2e} "
              f"{r['worst_relative_error_scaled_to_array_max']:>11.2e} "
              f"{str(r['bit_identical_under_permutation']):>15} "
              f"{r['polarity_folding_max_abs_error']:>10.2e}")
    print(f"written: {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "configs/featurise_accuracy.json")
