"""Probe tasks — turning an utterance's annotation into per-frame targets.

T1 (phone classification, 4.1) and T3 (boundary detection, 4.3) are wired up
here; T3's peak picking and metrics live in `boundaries.py`. T2 is not, and
needs a decision this session did not reach: 4.2 wants a reference contour from
a standard pitch tracker with a second tracker run against it to quantify
disagreement, and neither tracker exists here.

**The frame grid is not a choice made here.** SPEC section 5 fixes it: frame
`k` samples at `t = k * hop`, and there are `floor(duration / hop) + 1` frames.
Labels are read at exactly those instants, so features and targets are on one
grid by construction rather than by a resampling step that could be off by one.
Control C5 exists because that is the most likely silent bug in the pipeline,
and it is checked on every run rather than argued about here.

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-07
"""
import numpy as np

#: Marker for a frame with no label — outside every segment, or shifted off the
#: end of the utterance by control C5. Excluded from fitting and from scoring.
UNLABELLED = -1


class LabelSet:
    """A fixed ordering of the label inventory, shared by every condition.

    Fixed because the confusion matrix of equation (38) is indexed by it, and
    a decoded-information figure computed against a different ordering per
    encoder would be comparing different quantities.
    """

    def __init__(self, labels):
        self.labels = tuple(labels)
        self._index = {lab: i for i, lab in enumerate(self.labels)}
        if len(self._index) != len(self.labels):
            raise ValueError("label inventory contains duplicates")

    def __len__(self):
        return len(self.labels)

    def index(self, label):
        return self._index.get(label, UNLABELLED)

    @property
    def chance(self) -> float:
        """Uniform-guess accuracy — the weaker of the two C2 floors."""
        return 1.0 / len(self.labels)


def frame_times(duration, hop):
    """The SPEC section 5 frame grid, so nothing has to restate it."""
    n_frames = int(np.floor(duration / hop)) + 1
    return np.arange(n_frames) * hop


def frame_labels(utterance, hop, labelset, n_frames=None):
    """T1 targets: the label of the segment containing each frame instant.

    `n_frames` defaults to the SPEC section 5 count and should be passed when
    the featurisation is already computed, so that a disagreement between the
    two counts surfaces here as an error rather than downstream as a silent
    truncation.
    """
    t = frame_times(utterance.duration, hop)
    if n_frames is not None and n_frames != len(t):
        raise ValueError(
            f"frame count disagreement for {utterance.uid}: features have "
            f"{n_frames} frames, the SPEC section 5 grid gives {len(t)}")
    return np.array([labelset.index(utterance.label_at(ti)) for ti in t],
                    dtype=np.int64)


def majority_floor(y) -> float:
    """C2: the fraction of frames taken by the commonest label.

    Reported for every classification task, because a probe that does not
    substantially beat it is not working. This is the floor that matters;
    chance is the weaker one, and on a corpus with unequal label priors it can
    be far below what a constant prediction achieves.
    """
    y = np.asarray(y)
    y = y[y != UNLABELLED]
    if y.size == 0:
        return float("nan")
    return float(np.bincount(y).max() / y.size)


def shift_labels(y, k):
    """C5: offset the targets by `k` frames against the features.

    Frames shifted in from beyond the utterance are marked UNLABELLED rather
    than wrapped or edge-padded, so the control measures the cost of
    misalignment and not the cost of inventing labels at the ends.

    `k = +1` pairs frame `i`'s features with frame `i+1`'s label.
    """
    y = np.asarray(y)
    out = np.full_like(y, UNLABELLED)
    if k == 0:
        return y.copy()
    if k > 0:
        if k < len(y):
            out[:-k] = y[k:]
    else:
        if -k < len(y):
            out[-k:] = y[:k]
    return out


def boundary_labels(utterance, hop, tolerance_frames=1, n_frames=None):
    """T3 targets: 1 where a reference boundary is near the frame instant.

    A frame is positive when an interior segment boundary lies within
    `tolerance_frames` of `t = k*hop`. Some tolerance is unavoidable — a
    boundary almost never falls exactly on a frame instant, and a
    zero-tolerance target would be positive for a handful of frames in an
    utterance and negative for hundreds, which no probe would learn.

    This is *not* the scoring tolerance of proposal 4.3. That one is twenty
    milliseconds and governs whether a detection counts as a hit; this one
    governs what the probe is trained to call a boundary. They are independent
    and 4.3 mentions only the first (Q29).
    """
    t = frame_times(utterance.duration, hop)
    if n_frames is not None and n_frames != len(t):
        raise ValueError(
            f"frame count disagreement for {utterance.uid}: {n_frames} frames "
            f"against the SPEC section 5 grid's {len(t)}")
    y = np.zeros(len(t), dtype=np.int64)
    bounds = utterance.boundaries()
    if bounds.size:
        near = np.min(np.abs(t[:, None] - bounds[None, :]), axis=1)
        y[near <= tolerance_frames * hop + 1e-12] = 1
    return y


#: Reference for the semitone scale, in hertz. Any constant works — a shift in
#: reference is a constant offset in semitones and changes no correlation and
#: no RMSE — but it must be recorded, since a predicted semitone value is
#: meaningless without it.
SEMITONE_REF_HZ = 100.0


def semitones(f0, ref=SEMITONE_REF_HZ):
    """Hertz to semitones relative to `ref`. Proposal 4.2's scale."""
    f0 = np.asarray(f0, dtype=np.float64)
    return 12.0 * np.log2(np.where(f0 > 0.0, f0, np.nan) / ref)


def f0_targets(utterance, hop, ref=SEMITONE_REF_HZ, n_frames=None):
    """T2 targets: `(semitone_contour, voiced)` on the SPEC section 5 grid.

    The corpus supplies `f0` and `voiced` on a grid of spacing `utterance.f0_hop`.
    That must equal the featurisation `hop`, or targets and features are not on
    the same frames; a mismatch raises rather than being resampled, because a
    silent resampling here is precisely the misalignment control C5 exists to
    catch and it would be introduced by the very code meant to avoid it.

    Unvoiced frames carry NaN in the contour and False in `voiced`. They are
    excluded from fitting and from the correlation and RMSE, and are the
    positive/negative classes of the separate voicing probe.
    """
    if utterance.f0 is None or utterance.voiced is None:
        raise ValueError(f"{utterance.uid} carries no f0 reference")
    if abs(utterance.f0_hop - hop) > 1e-12:
        raise ValueError(
            f"{utterance.uid}: f0 grid hop {utterance.f0_hop} does not match "
            f"the featurisation hop {hop}; targets and features would sit on "
            "different frames")
    t = frame_times(utterance.duration, hop)
    if len(utterance.f0) != len(t):
        raise ValueError(
            f"{utterance.uid}: f0 grid has {len(utterance.f0)} points against "
            f"the SPEC section 5 grid's {len(t)}")
    if n_frames is not None and n_frames != len(t):
        raise ValueError(
            f"{utterance.uid}: features have {n_frames} frames against the "
            f"SPEC section 5 grid's {len(t)}")
    return semitones(utterance.f0, ref), np.asarray(utterance.voiced, bool)


def stack_context(x, context):
    """Concatenate each frame with `context` frames either side.

    Proposal 6.2 specifies the linear probe "applied per frame", which is
    `context = 0`. It is a parameter rather than a constant because a single
    10 ms frame is a much weaker probe than the context windows used by every
    TIMIT result in the C1 anchor band, and whether the anchor is reachable at
    all under the literal reading is open (Q22). Edges are zero-padded.
    """
    if context == 0:
        return x
    if context < 0:
        raise ValueError(f"context must be non-negative, got {context}")
    n, d = x.shape
    pad = np.zeros((context, d), dtype=x.dtype)
    padded = np.concatenate([pad, x, pad], axis=0)
    return np.concatenate([padded[i:i + n] for i in range(2 * context + 1)],
                          axis=1)
