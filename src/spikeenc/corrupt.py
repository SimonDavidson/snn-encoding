"""Corruption operators — SPEC.md section 7.

Used by preliminary experiment P2, which asks whether the three probe tasks
degrade under *different* operators (prediction P-07), and by `test_T5_4`,
which checks the encoder and the jitter operator together against the Gaussian
vector-strength law.

Every operator returns a new SpikeTrain in canonical order and never mutates
its input: P2 applies several operators to the same train, and an in-place
operator would make the result depend on the order they were applied in.

Author:        Simon Davidson & Claude
Created:       2026-09-04
Last modified: 2026-09-04
"""
import numpy as np

from .spiketrain import SpikeTrain


def _params(train, op, **detail):
    """Carry the encoder's provenance through and append this operator to it,
    so a corrupted train records what was done to it as well as what made it."""
    p = dict(train.params)
    p["corruptions"] = list(p.get("corruptions", [])) + [dict(op=op, **detail)]
    return p


def jitter(train, sigma, rng):
    """Perturb each event time by N(0, sigma^2). SPEC section 7.

    Count is preserved, times are clipped into [0, duration], and canonical
    order is restored -- jitter reorders events near in time, and a train out
    of canonical order violates SPEC section 2.

    Clipping is what SPEC specifies, and it is worth knowing that it biases the
    vector strength of `test_T5_4` very slightly: events within a few sigma of
    either end are pulled inward rather than perturbed symmetrically. At the
    tested sigma of 0.5-1.0 ms against a 2 s signal the affected fraction is
    ~0.1 per cent, far inside the test's 0.10 absolute tolerance.
    """
    if sigma < 0.0:
        raise ValueError(f"sigma must be non-negative, got {sigma}")
    t = train.time + rng.normal(0.0, sigma, size=len(train))
    np.clip(t, 0.0, train.duration, out=t)
    return SpikeTrain.from_events(
        channel=train.channel, time=t, polarity=train.polarity,
        n_channels=train.n_channels, duration=train.duration,
        params=_params(train, "jitter", sigma=float(sigma)))


def channel_shift(train, delta):
    """Add `delta` to every channel index, dropping events that fall outside
    [0, n_channels). SPEC section 7.

    Drops rather than wraps, deliberately: wrapping would move an event from
    the top of the filterbank to the bottom, which is not a small perturbation
    of a tonotopic axis but a large one, and P2 is asking about graceful
    degradation. `n_channels` is unchanged, so the train keeps its shape and
    the featurisation keeps its width.
    """
    shifted = train.channel.astype(np.int64) + int(delta)
    keep = (shifted >= 0) & (shifted < train.n_channels)
    return SpikeTrain.from_events(
        channel=shifted[keep], time=train.time[keep],
        polarity=train.polarity[keep], n_channels=train.n_channels,
        duration=train.duration,
        params=_params(train, "channel_shift", delta=int(delta)))


def delete(train, p, rng):
    """Retain each event independently with probability 1 - p. SPEC section 7.

    Independently per event, so the retained count is Binomial(N, 1-p) rather
    than exactly (1-p)N; `test_corrupt_delete_retains_expected_fraction` allows
    0.65 to 0.75 at p = 0.3, which for its N > 500 train is about 5 standard
    deviations of headroom either side.
    """
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p must be in [0, 1], got {p}")
    keep = rng.random(len(train)) >= p
    return SpikeTrain.from_events(
        channel=train.channel[keep], time=train.time[keep],
        polarity=train.polarity[keep], n_channels=train.n_channels,
        duration=train.duration, params=_params(train, "delete", p=float(p)))


def randomise_times(train, rng):
    """Resample every event time uniformly in [0, duration], preserving each
    channel's event count. SPEC section 7.

    The destroy-all-timing control for P1 and P2: it holds the count code
    exactly fixed -- per channel, not merely in total -- while removing every
    temporal relationship. The difference between a probe's accuracy here and
    on the intact train is what the temporal information index of equation (40)
    is measuring. Channel indices and polarities ride along untouched, which is
    what preserves the counts.
    """
    t = rng.uniform(0.0, train.duration, size=len(train))
    return SpikeTrain.from_events(
        channel=train.channel, time=t, polarity=train.polarity,
        n_channels=train.n_channels, duration=train.duration,
        params=_params(train, "randomise_times"))
