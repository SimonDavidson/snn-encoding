"""Featurisation — SPEC.md section 5, proposal equation (32).

The interface between an encoder and a probe. Proposal section 6.1 is explicit
that this conversion must be identical across encoders or it silently becomes
part of what is being compared, so there is one implementation and no
per-encoder special casing.

Author:        Simon Davidson & Claude
Created:       2026-09-04
Last modified: 2026-09-04
"""
import numpy as np


def featurise(train, tau=0.005, hop=0.010, split_polarity=True):
    """Exponential kernel sampled at a fixed frame rate, equation (32):

        phi_c(t) = sum_k kappa(t - t_k),   kappa(u) = exp(-u/tau) for u >= 0

    Frame `k` samples at `t = k*hop`, and there are `floor(duration/hop) + 1`
    frames. Returns `(n_frames, n_channels)`, or `(n_frames, 2*n_channels)`
    when `split_polarity` is True, ON channels first then OFF.

    ON and OFF are accumulated separately rather than summed because cancelling
    them would discard the distinction a bipolar encoder went to the trouble of
    making (proposal section 6.1). Encoders declaring a single polarity leave
    the OFF half at zero, which is correct rather than wasteful: the probe sees
    the same feature width for every encoder at a given channel count.

    **Order invariance** is required by SPEC section 5 and is the point of
    `test_G8`. Summation over a set is order-invariant in exact arithmetic but
    not in floating point, so events are sorted into a canonical order before
    anything is accumulated. The result is then bit-identical under any
    permutation of the input arrays, which is stronger than the rtol=1e-10 the
    test allows, and it costs one lexsort.

    The accumulation is recursive rather than a direct double sum:

        phi[k] = phi[k-1] * exp(-hop/tau) + (events in (t[k-1], t[k]])

    which is O(n_events + n_frames) instead of O(n_events * n_frames). The
    alternative closed form, `exp(-t_k/tau) * cumsum(exp(t_j/tau))`, is not
    usable: `exp(t/tau)` overflows a double at t/tau ~ 710, which for the
    default tau is 3.6 seconds of audio.
    """
    if tau <= 0.0:
        raise ValueError(f"tau must be positive, got {tau}")
    if hop <= 0.0:
        raise ValueError(f"hop must be positive, got {hop}")

    # SPEC section 5 states the frame count as floor(duration/hop) + 1. Applied
    # literally, including its sensitivity to the representation of `hop`:
    # duration/hop can land a hair under an integer and lose the last frame.
    # Left as the spec states it rather than silently rounded, since the frame
    # grid is contract and a Layer 3 reimplementation works from that sentence.
    n_frames = int(np.floor(train.duration / hop)) + 1
    n_groups = 2 * train.n_channels if split_polarity else train.n_channels
    out = np.zeros((n_frames, n_groups), dtype=np.float64)
    if len(train) == 0 or n_frames == 0:
        return out

    if split_polarity:
        group = (train.channel.astype(np.int64)
                 + np.where(train.polarity < 0, train.n_channels, 0))
    else:
        group = train.channel.astype(np.int64)

    # Canonical order: by group, then by time. Fixes the summation order so the
    # output does not depend on the order of the input arrays.
    order = np.lexsort((train.time, group))
    group, times = group[order], train.time[order]

    frame_t = np.arange(n_frames) * hop
    decay = np.exp(-hop / tau)
    starts = np.searchsorted(group, np.arange(n_groups), side="left")
    ends = np.searchsorted(group, np.arange(n_groups), side="right")

    for g in range(n_groups):
        tg = times[starts[g]:ends[g]]
        if tg.size == 0:
            continue
        # Events at exactly t = k*hop contribute exp(0) = 1 to frame k, since
        # kappa is defined on u >= 0 -- hence side="right".
        upto = np.searchsorted(tg, frame_t, side="right")
        acc, prev = 0.0, 0
        for k in range(n_frames):
            acc *= decay
            j = upto[k]
            if j > prev:
                acc += float(np.sum(np.exp(-(frame_t[k] - tg[prev:j]) / tau)))
                prev = j
            out[k, g] = acc
    return out
