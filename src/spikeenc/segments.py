"""Segment-level scoring, and the count-only featurisation of P1.

Preliminary experiment P1 (proposal 7.1) asks how much of each task is solvable
from event counts alone, with all timing discarded, and defines the temporal
information index

    TII_T = (A_temporal - A_count) / (A_ceiling - A_count)          (40)

with the ceiling taken from R2. A task whose index is near zero "is not testing
temporal coding at all - it is a spectral profile task wearing a spiking
costume", and is reformulated or dropped.

**Why this is segment-level and not frame-level.** 7.1 says to featurise "each
utterance or segment as the vector of per-channel event counts `n_c`,
discarding event times entirely". The subscript is the whole specification:
`n_c` is indexed by channel and by nothing else, so the representation has no
time axis at all. That cannot be done on a frame grid, because the grid is
itself timing - a per-frame count still says *when*, to within one hop. Section
4.1 already offers segment-level T1 as a first-class form of the task
("segment-level classification, in which each labelled segment is classified as
a whole"), so this is the reading the documents support rather than a
convenience.

**How the temporal and ceiling conditions produce a segment verdict.** 7.1 says
to "run the same probes", and the same probes are frame-level. So the frame
probe is fitted and evaluated exactly as it is everywhere else, and its
per-frame predictions over a segment are combined by majority vote. That is a
decision rule applied to an unchanged model, not a different featurisation -
which matters, because inventing a segment-level pooling of equation (32) would
put a free choice inside the numerator of equation (40).

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-07
"""
import numpy as np

from .tasks import UNLABELLED, frame_times


def segment_table(corpus, labelset):
    """Every labelled segment in the corpus, as parallel arrays.

    Returns `(label, uid, speaker, start, end)`. One row per segment, in corpus
    order, which is the order `segment_counts` and `segment_votes` also use.
    """
    label, uid, speaker, start, end = [], [], [], [], []
    for utt in corpus:
        for seg in utt.segments:
            label.append(labelset.index(seg.label))
            uid.append(utt.uid)
            speaker.append(utt.speaker)
            start.append(seg.start)
            end.append(seg.end)
    return (np.array(label, dtype=np.int64), np.array(uid, dtype=object),
            np.array(speaker, dtype=object), np.array(start),
            np.array(end))


def segment_counts(trains, corpus, offset=0.0, normalise=False):
    """P1's features: per-channel event counts within each segment.

    Shape `(n_segments, 2 * n_channels)`, ON channels first then OFF — the same
    layout `features.featurise` uses, so a probe sees the same feature width for
    the count condition as for the temporal one and the comparison is not also
    a comparison of dimensionality.

    `normalise=True` divides by the segment's duration, giving a rate per
    channel instead of a count. The distinction is not cosmetic: a raw count is
    the product of a rate and a duration, and segment duration is itself
    informative about phone identity on real speech, so a count-only probe can
    score partly by reading duration — which is timing, and is exactly what P1
    is supposed to have discarded. Both are computed and reported (Q26).

    `offset` shifts the counting window in seconds, for the segment-level
    analogue of control C5.
    """
    n_ch = next(iter(trains.values())).n_channels
    rows = []
    for utt in corpus:
        train = trains[utt.uid]
        group = (train.channel.astype(np.int64)
                 + np.where(train.polarity < 0, n_ch, 0))
        t = train.time
        for seg in utt.segments:
            lo, hi = seg.start + offset, seg.end + offset
            inside = (t >= lo) & (t < hi)
            counts = np.bincount(group[inside], minlength=2 * n_ch)
            if normalise:
                duration = max(hi - lo, 1e-12)
                counts = counts / duration
            rows.append(counts.astype(np.float64))
    return np.vstack(rows) if rows else np.zeros((0, 2 * n_ch))


def frame_segment_index(utterance, hop, n_frames=None, offset_frames=0):
    """Which segment each frame instant falls in, or UNLABELLED outside all.

    `offset_frames` shifts the instant frame k is attributed to, from `k*hop`
    to `(k + offset_frames)*hop`. It must match the offset the frame probe's
    labels were shifted by, or the vote would assign a prediction trained
    against one segment to a different one — and the C5 measurements make it
    certain that the offset used will not always be zero.

    Note this is the same convention as `tasks.shift_labels`, where
    `shift_labels(y, o)[k]` is the label at `(k + o)*hop`.

    Indices are local to the utterance; `segment_votes` walks them in corpus
    order to line them up with `segment_table`.
    """
    t = frame_times(utterance.duration, hop) + offset_frames * hop
    if n_frames is not None and n_frames != len(t):
        raise ValueError(
            f"frame count disagreement for {utterance.uid}: {n_frames} frames "
            f"against the SPEC section 5 grid's {len(t)}")
    out = np.full(len(t), UNLABELLED, dtype=np.int64)
    for i, seg in enumerate(utterance.segments):
        out[(t >= seg.start) & (t < seg.end)] = i
    return out


def segment_votes(frame_pred, frame_uid, corpus, hop, n_classes,
                  n_segments=None, offset_frames=0):
    """Majority vote of a frame probe's predictions within each segment.

    `frame_pred` and `frame_uid` are the corpus-wide frame arrays in corpus
    order. Returns a prediction per segment, or UNLABELLED for a segment
    containing no predicted frame — which happens only for a segment shorter
    than one hop, and is excluded from scoring rather than guessed.

    Ties go to the lowest class index, which `np.argmax` on the tally gives for
    free. A tie is rare and its resolution is arbitrary either way; recording
    the rule matters more than which rule it is.
    """
    votes = []
    for utt in corpus:
        mask = frame_uid == utt.uid
        idx = frame_segment_index(utt, hop, n_frames=int(np.sum(mask)),
                                  offset_frames=offset_frames)
        pred = frame_pred[mask]
        for i in range(len(utt.segments)):
            in_seg = pred[idx == i]
            if in_seg.size == 0:
                votes.append(UNLABELLED)
            else:
                votes.append(int(np.argmax(np.bincount(in_seg,
                                                       minlength=n_classes))))
    out = np.array(votes, dtype=np.int64)
    if n_segments is not None and len(out) != n_segments:
        raise ValueError(f"produced {len(out)} segment votes against "
                         f"{n_segments} segments in the table")
    return out


def temporal_information_index(a_temporal, a_count, a_ceiling):
    """Equation (40). Returns None where the denominator is not usable.

    The index is undefined when the ceiling does not exceed the count-only
    accuracy, and near-undefined when it barely does — a denominator of a few
    points turns ordinary seed noise in the numerator into an index of
    arbitrary magnitude. Rather than return a large number that reads as a
    strong result, this returns None and lets the caller report why.

    **The 0.02 threshold is a floor, not a sufficiency test.** A denominator of
    0.03 still produces an index an order of magnitude larger than the 0 to 1
    range 7.1 discusses it in, and on a test set of 72 segments 0.02 is about
    one and a half segments. Callers must report the denominator beside the
    index; `run_p1` does. A principled threshold would depend on the test-set
    size, which this function deliberately does not know — pushing that
    judgement to the caller is better than hard-coding a corpus assumption
    here.
    """
    denominator = a_ceiling - a_count
    if denominator <= 0.02:
        return None
    return (a_temporal - a_count) / denominator
