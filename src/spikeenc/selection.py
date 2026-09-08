"""Free-parameter selection — validation protocol section 13, D71.

Every free parameter is selected *per condition*, on data held out inside the
training split, never on test, with the grid and the chosen value recorded.
This module is the one place that happens, so there is one procedure rather
than several that are meant to agree. That is D30's argument for E2 and E3
sharing one lattice rule, and D51's for R2 and the spiking conditions sharing
one decoder, applied to selection: the harness had four parameters chosen four
ways, and three of the four were being chosen against the number they were
about to report.

**Why folds rather than a single held-out third.** `_select_ridge_alpha` used
one third of the training speakers, which on a ten-speaker corpus with a 30 per
cent test fraction is two speakers and six utterances. A single offset chosen
on six utterances is close to a coin toss, and the whole point of moving
selection off the test set is to stop a free parameter absorbing noise. Folds
use every training speaker for validation exactly once, at K times the fits;
the folds are speaker-disjoint for the same reason C4 requires the outer split
to be.

**The selection score is the score being reported.** An offset chosen by
validation accuracy and reported as test F-score would be selecting for one
thing and reporting another. Each caller passes the metric it will report.

Author:        Simon Davidson & Claude
Created:       2026-09-08
Last modified: 2026-09-08
"""
import numpy as np

# Selection is seeded from the run's own seed plus this, so a run's folds are
# reproducible from what the manifest already records, and are not the outer
# split's permutation with the same seed.
_FOLD_SEED_OFFSET = 17


def speaker_folds(train_uids, speaker_of, n_folds=3, seed=0):
    """Speaker-disjoint K-fold partition of the *training* utterances.

    Returns a list of `(fit_uids, val_uids)` pairs of frozensets. Speakers are
    shuffled once and dealt round-robin into `n_folds` groups, so the groups
    differ in size by at most one speaker however many there are; each group in
    turn is the validation side.

    Returns an empty list when the training set has fewer than two speakers, in
    which case there is nothing to hold out and the caller must fall back to
    the first candidate rather than pretend a selection was made.
    """
    train_uids = list(train_uids)
    speakers = sorted({speaker_of[u] for u in train_uids})
    if len(speakers) < 2 or n_folds < 2:
        return []
    k = min(int(n_folds), len(speakers))
    rng = np.random.default_rng(int(seed) + _FOLD_SEED_OFFSET)
    shuffled = [speakers[i] for i in rng.permutation(len(speakers))]

    folds = []
    for g in range(k):
        held = frozenset(shuffled[g::k])
        val = frozenset(u for u in train_uids if speaker_of[u] in held)
        fit = frozenset(u for u in train_uids if speaker_of[u] not in held)
        if val and fit:
            folds.append((fit, val))
    return folds


def fold_sizes(folds, speaker_of):
    """What each fold actually held out — recorded so a thin fold is visible."""
    return [{"n_fit_utterances": len(fit), "n_val_utterances": len(val),
             "n_fit_speakers": len({speaker_of[u] for u in fit}),
             "n_val_speakers": len({speaker_of[u] for u in val})}
            for fit, val in folds]


def select_on_folds(candidates, folds, evaluate, *, criterion="score",
                    maximise=True, key=str, choose=None, aggregate=np.mean):
    """Score every candidate on every fold and return the best.

    `evaluate(candidate, fit_uids, val_uids)` returns one number, or a dict of
    named metrics, or None / NaN when the candidate cannot be scored on that
    fold — too few voiced frames, an empty class, a degenerate fit. A candidate
    is dropped only if *every* fold returns nothing; otherwise it is aggregated
    over the folds that did return, and the count is recorded so a candidate
    scored on one fold cannot be mistaken for one scored on three.

    **Why a dict of metrics rather than one number.** T2 has two free
    parameters answering to different criteria: D59 selects the ridge penalty
    on validation RMSE precisely because a correlation is scale-free and
    survives the 468-octave predictions that motivated it, while the offset is
    selected on the reported headline, which is a correlation. Both metrics
    come out of the same fit, so both are recorded from one pass and the
    caller's `choose` does the nested argmax over the grid. Selecting the pair
    on a single criterion would mean choosing the offset for one thing and
    reporting another, which is the fault this module exists to remove.

    Returns `(chosen, grid)`. `chosen` is the candidate object, not its key.
    `grid` maps `key(candidate)` to `{"score", "scores", "per_fold",
    "n_folds_scored"}`, which is the record D71 requires.

    A single candidate is returned without fitting anything: there is no
    selection to make, and P2 — which holds each task's alignment at its clean
    best under D62 — passes exactly one. With no folds at all, a training set
    of one speaker, the first candidate is returned and the grid records that
    no selection happened, which is visible to a reader rather than silent.
    """
    candidates = list(candidates)
    if not candidates:
        raise ValueError("no candidates to select from")
    if len(candidates) == 1 or not folds:
        return candidates[0], {key(c): {"score": None, "scores": {},
                                        "per_fold": [], "n_folds_scored": 0}
                               for c in candidates}

    def as_dict(v):
        if v is None:
            return {}
        if isinstance(v, dict):
            return {k: float(x) for k, x in v.items()
                    if x is not None and np.isfinite(x)}
        return {"score": float(v)} if np.isfinite(v) else {}

    grid = {}
    for c in candidates:
        per_fold = [as_dict(evaluate(c, fit, val)) for fit, val in folds]
        names = sorted({k for d in per_fold for k in d})
        scores = {}
        for name in names:
            vals = [d[name] for d in per_fold if name in d]
            if vals:
                scores[name] = float(aggregate(vals))
        grid[key(c)] = {
            "score": scores.get(criterion),
            "scores": scores,
            "per_fold": [d or None for d in per_fold],
            "n_folds_scored": sum(1 for d in per_fold if d),
        }

    if choose is not None:
        best_key = choose(grid)
    else:
        usable = {k: v["scores"][criterion] for k, v in grid.items()
                  if criterion in v["scores"]}
        if not usable:
            produced = sorted({m for v in grid.values() for m in v["scores"]})
            if produced:
                raise KeyError(
                    f"criterion {criterion!r} was never returned by evaluate; "
                    f"metrics seen: {produced}")
            return candidates[0], grid
        best_key = (max(usable, key=usable.get) if maximise
                    else min(usable, key=usable.get))
    chosen = next(c for c in candidates if key(c) == best_key)
    return chosen, grid


def profile_scores(grid, metric=None):
    """The bare `{key: score}` view of a selection grid, for the C5 check."""
    if metric is None:
        return {k: v["score"] for k, v in grid.items()}
    return {k: v["scores"].get(metric) for k, v in grid.items()}


def interior_maximum(profile, chosen, radius=2):
    """Control C5 as D70 restates it: an interior maximum, not a drop at +/-1.

    D70 replaced "confirm accuracy drops at offset +/-1" because as written the
    control presumed zero was the right alignment and would have been recorded
    as failed when the presumption, rather than the alignment, was what failed.
    The restatement is a property of the selected offset whatever it turns out
    to be: sweep at least `radius` frames either side of it and confirm the
    maximum is there and not on the edge of the swept range.

    `profile` maps `str(offset)` to a score, `None` for offsets that could not
    be scored. Every neighbour within `radius` must be present and strictly
    lower. A plateau fails: a control that cannot distinguish the selected
    offset from its neighbour has not demonstrated that the alignment carries
    information, which is the only thing it is for.

    Returns the verdict and the evidence for it, never a bare boolean — a
    failed control is recorded and reported, not repaired by re-selecting.
    """
    chosen = int(chosen)
    here = profile.get(str(chosen))
    missing, not_lower, neighbours = [], [], {}
    for d in range(-radius, radius + 1):
        if d == 0:
            continue
        k = str(chosen + d)
        v = profile.get(k)
        neighbours[k] = v
        if v is None:
            missing.append(chosen + d)
        elif here is None or not (v < here):
            not_lower.append(chosen + d)
    return {
        "selected_offset": chosen,
        "radius": radius,
        "score_at_selected": here,
        "neighbours": neighbours,
        "missing_offsets": missing,
        "offsets_not_lower": not_lower,
        "interior_maximum": bool(here is not None and not missing
                                 and not not_lower),
    }


def predicted_offset(lag_seconds, hop):
    """The alignment offset the declared lags predict, in whole frames.

    A feature at frame `k` describes acoustic content `lag_seconds` earlier, so
    the label that matches it sits `lag_seconds / hop` frames back and the
    offset is negative. Reported beside the selected offset so the sweep is a
    check on the front end's declared group delay and the featurisation kernel
    — two quantities computed independently of any probe — rather than a fit
    with nothing to compare against.
    """
    return int(-np.round(float(lag_seconds) / float(hop)))
