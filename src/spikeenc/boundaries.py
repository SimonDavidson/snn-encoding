"""T3 — boundary detection: peak picking, matching, and the segmentation metrics.

Proposal 4.3 fixes the task ("locate the instants at which one phone gives way
to the next"), the tolerance (twenty milliseconds, conventionally) and the
metrics (precision, recall, F-score, with the R-value alongside). It fixes
nothing between a frame-wise probe output and a list of instants, and that gap
is where most of the achievable score lives. Every choice made in it is a
parameter here, with a declared default, and is raised in QUESTIONS.md rather
than buried.

**The R-value is Räsänen, Laine and Altosaar, Interspeech 2009**, "An improved
speech segmentation quality measure: the R-value". It exists because hit rate
alone rewards over-segmentation: a detector that fires on every frame achieves
perfect recall, and F-score is only weakly protective. Writing:

    HR = recall,   OS = N_detected / N_reference - 1
    r1 = sqrt((1 - HR)^2 + OS^2)
    r2 = (-OS + HR - 1) / sqrt(2)
    R  = 1 - (|r1| + |r2|) / 2

`r1` is the distance from the ideal point (HR = 1, OS = 0) and `r2` the
distance from the line of pure over-segmentation, so a detector that buys recall
by inserting boundaries is penalised on `r2` however good its hit rate. Perfect
segmentation gives exactly 1.

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-07
"""
import numpy as np

#: Proposal 4.3's conventional matching tolerance, in seconds.
DEFAULT_TOLERANCE = 0.020


def pick_peaks(score, hop, threshold, min_separation=0.020):
    """Frame-wise boundary score to a list of instants, in seconds.

    A frame is a candidate when its score exceeds `threshold` and is at least
    as large as both neighbours; candidates are then taken in descending score
    order and kept only if no stronger candidate already sits within
    `min_separation`.

    Strongest-first suppression rather than a left-to-right scan, because a
    left-to-right rule makes the output depend on the direction of time: a weak
    detection would suppress a strong one 10 ms later purely by arriving first.
    Nothing in 4.3 requires either, and the asymmetric one would bias T3 in a
    task whose whole subject is timing.
    """
    score = np.asarray(score, dtype=np.float64)
    if score.size == 0:
        return np.empty(0, dtype=np.float64)

    padded = np.concatenate([[-np.inf], score, [-np.inf]])
    is_peak = (padded[1:-1] >= padded[:-2]) & (padded[1:-1] >= padded[2:])
    candidates = np.flatnonzero(is_peak & (score > threshold))
    if candidates.size == 0:
        return np.empty(0, dtype=np.float64)

    kept = []
    for i in candidates[np.argsort(-score[candidates], kind="stable")]:
        t = i * hop
        if all(abs(t - k) >= min_separation for k in kept):
            kept.append(t)
    return np.sort(np.array(kept, dtype=np.float64))


def match_boundaries(predicted, reference, tolerance=DEFAULT_TOLERANCE):
    """One-to-one matching of detections to reference boundaries.

    Returns `(n_hits, pairs)`. Pairs are formed nearest-first over all
    candidate pairs within `tolerance`, each detection and each reference used
    at most once — so a single detection cannot claim two boundaries, and two
    detections straddling one boundary yield one hit and one false positive,
    which is what over-segmentation should cost.

    Nearest-first rather than greedy in index order for the same reason
    `pick_peaks` suppresses strongest-first: an index-order rule would let an
    early poor match consume a reference that a later exact match wanted.
    """
    predicted = np.asarray(predicted, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    if predicted.size == 0 or reference.size == 0:
        return 0, []

    dist = np.abs(predicted[:, None] - reference[None, :])
    order = np.dstack(np.unravel_index(np.argsort(dist, axis=None),
                                       dist.shape))[0]
    used_p, used_r, pairs = set(), set(), []
    for p, r in order:
        if dist[p, r] > tolerance:
            break
        if p in used_p or r in used_r:
            continue
        used_p.add(int(p))
        used_r.add(int(r))
        pairs.append((int(p), int(r)))
    return len(pairs), pairs


def r_value(hit_rate, over_segmentation):
    """Räsänen, Laine and Altosaar (2009), as set out in the module docstring."""
    r1 = np.hypot(1.0 - hit_rate, over_segmentation)
    r2 = (-over_segmentation + hit_rate - 1.0) / np.sqrt(2.0)
    return float(1.0 - (abs(r1) + abs(r2)) / 2.0)


def score_boundaries(predicted, reference, tolerance=DEFAULT_TOLERANCE):
    """Precision, recall, F-score, over-segmentation and R-value.

    `predicted` and `reference` are sequences of per-utterance arrays of
    instants. Counts are pooled across utterances before the ratios are formed,
    rather than the ratios being averaged per utterance: a short utterance with
    two boundaries would otherwise weigh as heavily as a long one with twenty.
    """
    n_hit = n_pred = n_ref = 0
    for p, r in zip(predicted, reference):
        hits, _ = match_boundaries(p, r, tolerance)
        n_hit += hits
        n_pred += len(p)
        n_ref += len(r)

    precision = n_hit / n_pred if n_pred else 0.0
    recall = n_hit / n_ref if n_ref else 0.0
    f = (2 * precision * recall / (precision + recall)
         if precision + recall > 0 else 0.0)
    # Over-segmentation is defined on the count of detections, not on the hits,
    # which is the whole point: inserting boundaries that match nothing still
    # raises OS and still costs R-value.
    over = (n_pred / n_ref - 1.0) if n_ref else 0.0
    return {"precision": precision, "recall": recall, "f_score": f,
            "over_segmentation": over, "r_value": r_value(recall, over),
            "n_hit": n_hit, "n_predicted": n_pred, "n_reference": n_ref,
            "tolerance": tolerance}


def frame_auc(score, label):
    """Rank AUC of a frame-wise boundary score — P(positive > negative).

    Reported beside every T3 F-score because the two answer different
    questions and can disagree completely. F-score is the product of the
    probe, the threshold, the peak picker and the corpus's boundary
    statistics; AUC is the probe alone. A near-chance AUC with a respectable
    F-score means the F-score came from firing at roughly the right rate, which
    is exactly the failure mode the R-value was invented for — and without the
    AUC there is no way to tell that from a detector that works.

    Chance is 0.5 and does not depend on the positive rate, which a raw
    accuracy would.
    """
    score = np.asarray(score, dtype=np.float64)
    label = np.asarray(label)
    n_pos, n_neg = int((label == 1).sum()), int((label == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(score, kind="stable")
    ranks = np.empty(len(score), dtype=np.float64)
    ranks[order] = np.arange(1, len(score) + 1)
    # Ties would bias this; averaging tied ranks is the standard correction.
    _, inverse, counts = np.unique(score, return_inverse=True,
                                   return_counts=True)
    sums = np.bincount(inverse, weights=ranks)
    ranks = (sums / counts)[inverse]
    return float((ranks[label == 1].sum() - n_pos * (n_pos + 1) / 2.0)
                 / (n_pos * n_neg))


def uniform_baseline(durations, n_boundaries):
    """Evenly spaced boundaries at the reference rate — the C2 floor for T3.

    This is the trivial strategy the R-value exists to penalise, and it is the
    only floor that means anything for a detection task: a majority-class rate
    is meaningless when the question is where events are, not how many frames
    carry a label. Reporting F-score without it would let a detector that has
    learned the average phone rate and nothing else look like it works.
    """
    out = []
    for duration, n in zip(durations, n_boundaries):
        if n <= 0:
            out.append(np.empty(0, dtype=np.float64))
        else:
            step = duration / (n + 1)
            out.append(step * np.arange(1, n + 1))
    return out
