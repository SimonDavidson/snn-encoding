"""Preliminary experiment P2 — corruption and dissociation (proposal 7.2).

P2 asks whether the three probe tasks degrade under *different* corruptions, as
the spanning argument of 4.4 requires and prediction P-07 states. If the
degradation profiles turn out to be similar rather than distinct, "the battery
does not span the demand space and the central methodological claim of the
paper fails". It is a decision gate, and CLAUDE.md is explicit that the battery
is the design session's remit: this module runs the experiment and does not
interpret it.

**A conflict between the two specifications, found before running anything.**
Proposal 7.2's fourth operator is "count-preserving randomisation: event times
are resampled uniformly *within each segment* while preserving per-channel
counts, destroying timing while leaving rate intact". SPEC section 7 defines
`randomise_times` as resampling uniformly in `[0, duration]`. Those are not the
same operator. Randomising across the whole utterance destroys the segment-level
rate profile as well as fine timing, so "leaving rate intact" is false of it at
any resolution finer than the utterance — and for T1, whose whole signal is
which segment carries which spectral profile, it removes the thing the operator
is supposed to preserve.

`corrupt.randomise_times` is left exactly as SPEC defines it: it is covered by a
known-answer test and is not this session's to change.
`randomise_times_in_segments` below is the proposal's operator, added beside it,
and P2 runs both so the difference is a measurement rather than an argument
(Q35).

Author:        Simon Davidson & Claude
Created:       2026-09-08
Last modified: 2026-09-08
"""
import numpy as np

from .corrupt import _params, channel_shift, delete, jitter, randomise_times
from .spiketrain import SpikeTrain


def randomise_times_in_segments(train, utterance, rng):
    """Proposal 7.2's operator: resample times uniformly *within each segment*.

    Per-channel counts are preserved exactly, as in `corrupt.randomise_times`,
    and so additionally is the number of events each channel contributes to
    each segment — which is what makes "leaving rate intact" true. Fine timing
    inside a segment is destroyed completely.

    Events outside every segment keep their times; on a corpus whose segments
    tile the utterance there are none.
    """
    t = np.array(train.time, dtype=np.float64, copy=True)
    for seg in utterance.segments:
        inside = (t >= seg.start) & (t < seg.end)
        n = int(inside.sum())
        if n:
            t[inside] = rng.uniform(seg.start, seg.end, size=n)
    return SpikeTrain.from_events(
        channel=train.channel, time=t, polarity=train.polarity,
        n_channels=train.n_channels, duration=train.duration,
        params=_params(train, "randomise_times_in_segments",
                       n_segments=len(utterance.segments)))


def corruption_grid(jitter_sigmas=(0.0001, 0.0005, 0.002, 0.010, 0.050),
                    channel_deltas=(-4, -2, -1, 1, 2, 4),
                    delete_probabilities=(0.1, 0.3, 0.5),
                    include_randomisation=True):
    """The conditions of proposal 7.2, as `(operator, level)` pairs.

    Channel shift is swept over both signs because `channel_shift` drops events
    falling outside the bank rather than wrapping (SPEC section 7), so shifting
    up discards the highest channels and shifting down the lowest. The operator
    is not symmetric and a one-sided sweep would measure only half of it.
    """
    grid = [("clean", None)]
    grid += [("jitter", s) for s in jitter_sigmas]
    grid += [("channel_shift", d) for d in channel_deltas]
    grid += [("delete", p) for p in delete_probabilities]
    if include_randomisation:
        grid += [("randomise_times", None),
                 ("randomise_times_in_segments", None)]
    return grid


def apply_corruption(trains, corpus, operator, level, rng):
    """Apply one operator at one level to every train in a corpus."""
    if operator == "clean":
        return trains
    out = {}
    for utt in corpus:
        train = trains[utt.uid]
        if operator == "jitter":
            out[utt.uid] = jitter(train, level, rng)
        elif operator == "channel_shift":
            out[utt.uid] = channel_shift(train, int(level))
        elif operator == "delete":
            out[utt.uid] = delete(train, level, rng)
        elif operator == "randomise_times":
            out[utt.uid] = randomise_times(train, rng)
        elif operator == "randomise_times_in_segments":
            out[utt.uid] = randomise_times_in_segments(train, utt, rng)
        else:
            raise ValueError(f"unknown corruption operator {operator!r}")
    return out


def headroom_lost(clean, corrupted, floor):
    """Fraction of the task's usable range destroyed by a corruption.

    The three tasks have different scores on different scales with different
    floors — T1 a frame accuracy over a 0.21 majority baseline, T2 a
    correlation whose uninformative value is 0, T3 an F-score over a uniform
    baseline near 0.59. Comparing raw drops across them would compare the
    scales as much as the corruptions, and P2's entire question is whether the
    *profiles* differ between tasks.

    Normalising by each task's own headroom above its own floor is what makes
    the profiles commensurable (Q36). Returns None where the clean condition
    does not clear its floor, since a task with no headroom cannot lose a
    fraction of it.
    """
    headroom = clean - floor
    if headroom <= 0.02:
        return None
    return float((clean - corrupted) / headroom)
