"""Tests for segment-level scoring and P1's count-only featurisation.

Implementation-session tests. The one that earns its place is
`test_label_shift_and_segment_attribution_agree`: `run_p1` shifts the frame
probe's labels by an offset and separately attributes each frame's vote to a
segment using the same offset, and if those two conventions ever disagreed the
result would be a plausible number produced by scoring predictions against the
wrong segment. That is the silent off-by-one C5 exists for, one level up.

Runs on numpy and scipy alone.

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-07
"""
import numpy as np
import pytest

from spikeenc.corpus import PHONES, Segment, Utterance, synthetic_corpus
from spikeenc.harness import encode_corpus
from spikeenc.segments import (frame_segment_index, segment_counts,
                               segment_table, segment_votes,
                               temporal_information_index)
from spikeenc.tasks import UNLABELLED, LabelSet, frame_labels, shift_labels


@pytest.fixture(scope="module")
def tiny():
    return synthetic_corpus(n_speakers=3, utterances_per_speaker=1,
                            phones_per_utterance=4, seed=5)


@pytest.fixture(scope="module")
def trains(tiny):
    fe = {"envelope": "hilbert", "compression": "power"}
    return encode_corpus(tiny, "E1", [0.1], 8, fe)[0.1]


# --- the segment table ------------------------------------------------------

def test_segment_table_is_one_row_per_segment_in_corpus_order(tiny):
    labelset = LabelSet(PHONES)
    label, uid, speaker, start, end = segment_table(tiny, labelset)
    expected = [(u.uid, s) for u in tiny for s in u.segments]
    assert len(label) == len(expected)
    for i, (u_id, seg) in enumerate(expected):
        assert uid[i] == u_id
        assert start[i] == seg.start
        assert end[i] == seg.end
        assert label[i] == labelset.index(seg.label)


# --- the count featurisation ------------------------------------------------

def test_counts_account_for_every_event(tiny, trains):
    """Segments tile the utterance, so no event may be lost between them.
    A count featurisation that quietly drops events would understate the count
    condition and inflate the index of equation (40)."""
    counts = segment_counts(trains, tiny)
    total_events = sum(len(t) for t in trains.values())
    assert counts.sum() == pytest.approx(total_events)


def test_counts_have_the_same_width_as_the_temporal_features(tiny, trains):
    """2 * n_channels, ON then OFF, matching featurise — so P1 is not also
    comparing feature dimensionalities."""
    assert segment_counts(trains, tiny).shape[1] == 2 * 8


def test_rates_are_counts_over_duration(tiny, trains):
    labelset = LabelSet(PHONES)
    _, _, _, start, end = segment_table(tiny, labelset)
    counts = segment_counts(trains, tiny, normalise=False)
    rates = segment_counts(trains, tiny, normalise=True)
    for i, (a, b) in enumerate(zip(start, end)):
        assert rates[i] == pytest.approx(counts[i] / (b - a))


def test_count_window_offset_actually_moves_the_window(tiny, trains):
    """The segment-level analogue of C5 must be able to bite."""
    base = segment_counts(trains, tiny, offset=0.0)
    moved = segment_counts(trains, tiny, offset=0.050)
    assert not np.array_equal(base, moved)


# --- frame-to-segment attribution -------------------------------------------

def _three_segment_utterance():
    return Utterance(uid="u", speaker="S", audio=np.zeros(3000),
                     sample_rate=1000,
                     segments=(Segment(0.0, 1.0, "a"),
                               Segment(1.0, 2.0, "b"),
                               Segment(2.0, 3.0, "c")))


def test_frame_segment_index_assigns_by_the_frame_instant():
    u = _three_segment_utterance()
    idx = frame_segment_index(u, hop=0.5)
    # instants 0.0 0.5 1.0 1.5 2.0 2.5 3.0 -> segments 0 0 1 1 2 2 (3.0 is out)
    assert list(idx) == [0, 0, 1, 1, 2, 2, UNLABELLED]


def test_frame_segment_index_offset_shifts_the_instant():
    u = _three_segment_utterance()
    idx = frame_segment_index(u, hop=0.5, offset_frames=2)   # +1.0 s
    assert list(idx) == [1, 1, 2, 2, UNLABELLED, UNLABELLED, UNLABELLED]


def test_label_shift_and_segment_attribution_agree():
    """`shift_labels(y, o)[k]` is the label at `(k+o)*hop`; the segment index at
    `offset_frames=o` must be the segment holding that same instant. If these
    two drifted apart, run_p1 would score a probe's predictions against a
    different segment from the one it was trained against, and the result would
    look entirely reasonable."""
    u = _three_segment_utterance()
    labelset = LabelSet(("a", "b", "c"))
    y = frame_labels(u, 0.5, labelset)
    for o in (-2, -1, 0, 1, 2):
        shifted = shift_labels(y, o)
        idx = frame_segment_index(u, hop=0.5, offset_frames=o)
        for k in range(len(y)):
            if shifted[k] == UNLABELLED or idx[k] == UNLABELLED:
                continue
            # segment idx[k] must carry the label shifted[k]
            assert labelset.index(u.segments[idx[k]].label) == shifted[k]


# --- the vote ---------------------------------------------------------------

def test_segment_votes_take_the_majority():
    u = _three_segment_utterance()
    corpus = type("C", (), {"__iter__": lambda s: iter([u])})()
    uid = np.full(7, "u", dtype=object)
    # frames:      seg0 seg0 seg1 seg1 seg2 seg2 (out)
    pred = np.array([0,   0,   1,   2,   2,   2,   0])
    votes = segment_votes(pred, uid, corpus, 0.5, n_classes=3)
    assert list(votes) == [0, 1, 2]      # seg1 ties 1 vs 2 -> lowest index


def test_segment_votes_mark_a_segment_with_no_frames():
    """A segment containing no frame instant is excluded, not guessed at.

    With hop 0.1 the instants are 0.0, 0.1, 0.2 ... so the middle segment
    [0.05, 0.09) holds none of them, while the first still holds t = 0.0.
    """
    u = Utterance(uid="u", speaker="S", audio=np.zeros(1000), sample_rate=1000,
                  segments=(Segment(0.0, 0.05, "a"), Segment(0.05, 0.09, "b"),
                            Segment(0.09, 1.0, "c")))
    corpus = type("C", (), {"__iter__": lambda s: iter([u])})()
    uid = np.full(11, "u", dtype=object)
    votes = segment_votes(np.ones(11, dtype=np.int64), uid, corpus, 0.1,
                          n_classes=3)
    assert votes[0] == 1                # t = 0.0 lands here
    assert votes[1] == UNLABELLED       # no frame instant inside [0.05, 0.09)
    assert votes[2] == 1


def test_segment_votes_check_the_table_length():
    u = _three_segment_utterance()
    corpus = type("C", (), {"__iter__": lambda s: iter([u])})()
    with pytest.raises(ValueError, match="segment votes"):
        segment_votes(np.zeros(7, dtype=np.int64),
                      np.full(7, "u", dtype=object), corpus, 0.5, 3,
                      n_segments=99)


# --- equation (40) ----------------------------------------------------------

def test_tii_is_equation_40():
    assert temporal_information_index(0.8, 0.5, 0.9) == pytest.approx(
        (0.8 - 0.5) / (0.9 - 0.5))


def test_tii_is_none_when_the_ceiling_does_not_clear_the_count():
    """A denominator of a few points turns seed noise into an index of
    arbitrary size, which would read as a strong result."""
    assert temporal_information_index(0.8, 0.90, 0.91) is None   # 0.01
    assert temporal_information_index(0.8, 0.95, 0.90) is None   # negative
    assert temporal_information_index(0.8, 0.50, 0.51) is None   # 0.01


def test_tii_guard_is_a_floor_and_not_a_sufficiency_test():
    """Just above the guard the index is still enormous — 0.02 rules out the
    undefined cases, it does not certify the rest. That is why the denominator
    is reported alongside every index rather than only the index."""
    just_above = temporal_information_index(0.8, 0.5, 0.5201)
    assert just_above is not None and just_above > 10.0


def test_tii_can_be_negative():
    """Negative means the temporal featurisation is worse than counts alone,
    which is a real outcome and must not be clipped away."""
    assert temporal_information_index(0.6, 0.7, 0.9) < 0
