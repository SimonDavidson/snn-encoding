"""Tests for P2's corruption machinery.

Implementation-session tests. The one that earns its place is
`test_segment_randomisation_preserves_what_whole_utterance_randomisation_does_not`:
proposal 7.2 and SPEC section 7 define the fourth operator differently, and the
difference is exactly whether per-segment rate survives. Asserting it here makes
the discrepancy a measurement rather than a reading of two documents (Q35).

Author:        Simon Davidson & Claude
Created:       2026-09-08
Last modified: 2026-09-08
"""
import numpy as np
import pytest

from spikeenc.corrupt import randomise_times
from spikeenc.corpus import synthetic_corpus
from spikeenc.harness import encode_corpus
from spikeenc.p2 import (apply_corruption, corruption_grid, headroom_lost,
                         randomise_times_in_segments)

FRONT_END = {"envelope": "hilbert", "compression": "power"}


@pytest.fixture(scope="module")
def corpus():
    return synthetic_corpus(n_speakers=3, utterances_per_speaker=1,
                            phones_per_utterance=5, seed=7)


@pytest.fixture(scope="module")
def trains(corpus):
    return encode_corpus(corpus, "E1", [0.05], 8, FRONT_END)[0.05]


def _counts_per_segment(train, utterance):
    out = []
    for seg in utterance.segments:
        inside = (train.time >= seg.start) & (train.time < seg.end)
        out.append(np.bincount(train.channel[inside],
                               minlength=train.n_channels))
    return np.array(out)


def test_segment_randomisation_preserves_what_whole_utterance_does_not(
        corpus, trains):
    """7.2 says the operator leaves rate intact; SPEC's version does not."""
    u = corpus.utterances[0]
    train = trains[u.uid]
    rng = np.random.default_rng(0)

    per_segment = randomise_times_in_segments(train, u, rng)
    whole = randomise_times(train, rng)

    before = _counts_per_segment(train, u)
    assert np.array_equal(_counts_per_segment(per_segment, u), before)
    assert not np.array_equal(_counts_per_segment(whole, u), before)


def test_both_randomisations_preserve_per_channel_counts(corpus, trains):
    u = corpus.utterances[0]
    train = trains[u.uid]
    rng = np.random.default_rng(1)
    for corrupted in (randomise_times_in_segments(train, u, rng),
                      randomise_times(train, rng)):
        assert np.array_equal(corrupted.counts_per_channel(),
                              train.counts_per_channel())


def test_segment_randomisation_destroys_timing_inside_a_segment(corpus, trains):
    u = corpus.utterances[0]
    train = trains[u.uid]
    out = randomise_times_in_segments(train, u, np.random.default_rng(2))
    assert not np.allclose(np.sort(out.time), np.sort(train.time))
    assert len(out) == len(train)


def test_segment_randomisation_keeps_events_inside_their_segment(corpus, trains):
    u = corpus.utterances[0]
    out = randomise_times_in_segments(trains[u.uid], u,
                                      np.random.default_rng(3))
    for t in out.time:
        assert any(s.start <= t < s.end for s in u.segments)


def test_corruption_records_itself_in_the_train_params(corpus, trains):
    u = corpus.utterances[0]
    out = randomise_times_in_segments(trains[u.uid], u,
                                      np.random.default_rng(4))
    ops = [c["op"] for c in out.params["corruptions"]]
    assert ops == ["randomise_times_in_segments"]


def test_grid_covers_every_operator_of_section_7_2():
    grid = corruption_grid()
    ops = {op for op, _ in grid}
    assert ops == {"clean", "jitter", "channel_shift", "delete",
                   "randomise_times", "randomise_times_in_segments"}
    # Channel shift must be swept both ways: the operator drops rather than
    # wraps, so it is not symmetric.
    deltas = [lv for op, lv in grid if op == "channel_shift"]
    assert min(deltas) < 0 < max(deltas)


def test_apply_corruption_leaves_the_clean_trains_untouched(corpus, trains):
    rng = np.random.default_rng(5)
    same = apply_corruption(trains, corpus, "clean", None, rng)
    assert same is trains
    jittered = apply_corruption(trains, corpus, "jitter", 0.002, rng)
    for u in corpus:
        assert not np.array_equal(jittered[u.uid].time, trains[u.uid].time)
        assert len(jittered[u.uid]) == len(trains[u.uid])


def test_apply_corruption_rejects_an_unknown_operator(corpus, trains):
    with pytest.raises(ValueError, match="unknown corruption operator"):
        apply_corruption(trains, corpus, "smudge", 1.0,
                         np.random.default_rng(6))


def test_headroom_lost_is_a_fraction_of_the_usable_range():
    # T1: clean 0.80, floor 0.20, corrupted 0.50 -> half the headroom gone.
    assert headroom_lost(0.80, 0.50, 0.20) == pytest.approx(0.5)
    # A task scoring at its floor when clean has no headroom to lose.
    assert headroom_lost(0.21, 0.10, 0.20) is None


def test_headroom_lost_can_exceed_one_and_go_negative():
    """A corruption can push a task below its floor, and can occasionally help.
    Neither is clipped, because clipping would hide it."""
    assert headroom_lost(0.80, 0.10, 0.20) > 1.0
    assert headroom_lost(0.80, 0.90, 0.20) < 0.0
