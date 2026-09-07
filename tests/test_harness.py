"""Tests for the probe harness — implementation-session tests, not Layer 1.

`tests/test_known_answers.py` is written by the design session from the
defining equations and must not be edited here. This file is a different thing:
the harness has no SPEC contract to be checked against, because SPEC section 8
declares the pipeline deliberately unspecified, so what is testable is that the
machinery does what it claims and that the Layer 2 controls *bite*.

That last point is the reason most of these exist. A control which cannot fail
is worse than no control, because it is read as evidence. Each of C3, C4 and C5
is therefore tested twice: once that it passes on a correct pipeline, and once
that it fails on a pipeline deliberately broken in the way that control exists
to catch.

Runs on numpy and scipy alone, because CI installs `.[dev]` and nothing more.

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-07
"""
import numpy as np
import pytest

from spikeenc.corpus import PHONES, synthetic_corpus
from spikeenc.features import featurise
from spikeenc.harness import (build_dataset, calibrate_rate_param,
                              encode_corpus, run_t1)
from spikeenc.metrics import decoded_information
from spikeenc.probes import LinearProbe
from spikeenc.splits import LeakageError, Split, speaker_disjoint_split
from spikeenc.tasks import (UNLABELLED, LabelSet, frame_labels, frame_times,
                            majority_floor, shift_labels, stack_context)

FRONT_END = {"envelope": "hilbert", "compression": "power"}


@pytest.fixture(scope="module")
def tiny():
    """Small enough for CI, large enough to split three ways on speaker."""
    return synthetic_corpus(n_speakers=4, utterances_per_speaker=1,
                            phones_per_utterance=5, seed=3)


# --- the corpus -------------------------------------------------------------

def test_corpus_is_deterministic_in_its_seed():
    a = synthetic_corpus(n_speakers=2, utterances_per_speaker=1, seed=11)
    b = synthetic_corpus(n_speakers=2, utterances_per_speaker=1, seed=11)
    c = synthetic_corpus(n_speakers=2, utterances_per_speaker=1, seed=12)
    for ua, ub in zip(a.utterances, b.utterances):
        assert np.array_equal(ua.audio, ub.audio)
        assert ua.segments == ub.segments
    assert not np.array_equal(a.utterances[0].audio, c.utterances[0].audio)


def test_segments_tile_the_utterance_without_gap_or_overlap(tiny):
    for u in tiny:
        assert u.segments[0].start == 0.0
        for prev, nxt in zip(u.segments, u.segments[1:]):
            assert prev.end == nxt.start
        assert u.segments[-1].end == pytest.approx(u.duration, abs=1e-9)


def test_no_phone_repeats_across_a_boundary(tiny):
    """A boundary between two instances of one phone is in the label sequence
    and not in the audio; T3 would be scored against events that are not there."""
    for u in tiny:
        labels = [s.label for s in u.segments]
        assert all(a != b for a, b in zip(labels, labels[1:]))


def test_every_frame_instant_carries_a_label(tiny):
    labelset = LabelSet(PHONES)
    for u in tiny:
        y = frame_labels(u, 0.010, labelset)
        assert np.all(y != UNLABELLED)


# --- the frame grid, which is where C5 lives --------------------------------

@pytest.mark.parametrize("hop", [0.005, 0.010, 0.020])
def test_label_grid_matches_the_featurisation_grid(tiny, hop):
    """SPEC section 5 fixes both counts. If they ever disagree, every reported
    accuracy is computed against labels shifted by an unknown amount."""
    labelset = LabelSet(PHONES)
    from spikeenc.spiketrain import SpikeTrain
    for u in tiny:
        empty = SpikeTrain.empty(4, u.duration)
        n_feature_frames = featurise(empty, hop=hop).shape[0]
        assert len(frame_labels(u, hop, labelset)) == n_feature_frames
        assert len(frame_times(u.duration, hop)) == n_feature_frames


def test_frame_labels_raises_on_a_frame_count_disagreement(tiny):
    labelset = LabelSet(PHONES)
    u = tiny.utterances[0]
    with pytest.raises(ValueError, match="frame count disagreement"):
        frame_labels(u, 0.010, labelset, n_frames=3)


def test_shift_labels_marks_the_exposed_end_unlabelled():
    y = np.array([0, 1, 2, 3, 4])
    assert np.array_equal(shift_labels(y, 1), [1, 2, 3, 4, UNLABELLED])
    assert np.array_equal(shift_labels(y, -1), [UNLABELLED, 0, 1, 2, 3])
    assert np.array_equal(shift_labels(y, 0), y)
    assert np.all(shift_labels(y, 99) == UNLABELLED)


def test_stack_context_shape_and_centre():
    x = np.arange(20.0).reshape(5, 4)
    assert np.array_equal(stack_context(x, 0), x)
    s = stack_context(x, 1)
    assert s.shape == (5, 12)
    # The centre block is the unshifted frame.
    assert np.array_equal(s[:, 4:8], x)
    assert np.array_equal(s[0, :4], np.zeros(4))       # zero-padded edge


def test_majority_floor_ignores_unlabelled():
    y = np.array([0, 0, 0, 1, UNLABELLED, UNLABELLED])
    assert majority_floor(y) == pytest.approx(0.75)


# --- C4, split disjointness -------------------------------------------------

def test_split_is_speaker_disjoint_and_deterministic(tiny):
    a = speaker_disjoint_split(tiny, test_fraction=0.5, seed=0)
    b = speaker_disjoint_split(tiny, test_fraction=0.5, seed=0)
    assert a.train == b.train and a.test == b.test
    assert not (set(a.train_speakers) & set(a.test_speakers))
    assert set(a.train) | set(a.test) == {u.uid for u in tiny}
    assert a.assert_disjoint() is True


def test_c4_bites_when_a_speaker_is_on_both_sides():
    """The control exists to catch exactly this, so it is tested against it."""
    with pytest.raises(LeakageError, match="speaker"):
        Split(train=("a",), test=("b",), train_speakers=("S00",),
              test_speakers=("S00",), seed=0)


def test_c4_bites_when_an_utterance_is_on_both_sides():
    with pytest.raises(LeakageError, match="utterance"):
        Split(train=("a", "b"), test=("b",), train_speakers=("S00",),
              test_speakers=("S01",), seed=0)


def test_split_needs_two_speakers():
    one = synthetic_corpus(n_speakers=1, utterances_per_speaker=2, seed=0)
    with pytest.raises(ValueError, match="at least two speakers"):
        speaker_disjoint_split(one)


# --- the probe --------------------------------------------------------------

def test_probe_recovers_a_separable_problem_and_is_deterministic():
    rng = np.random.default_rng(4)
    x = rng.standard_normal((300, 6))
    y = (x[:, 0] > 0).astype(int) + 2 * (x[:, 1] > 0).astype(int)
    a = LinearProbe(4).fit(x, y)
    b = LinearProbe(4).fit(x, y)
    assert np.array_equal(a.predict(x), b.predict(x))
    assert a.converged_
    assert a.score(x, y) > 0.85


def test_probe_drops_unlabelled_frames():
    rng = np.random.default_rng(5)
    x = rng.standard_normal((100, 3))
    y = np.full(100, UNLABELLED)
    y[:60] = rng.integers(0, 2, 60)
    probe = LinearProbe(2).fit(x, y)
    assert probe.score(x, y) == probe.score(x[:60], y[:60])


def test_probe_confusion_feeds_equation_38():
    """A perfect probe on K equiprobable classes carries log2(K) bits."""
    x = np.eye(8)
    y = np.arange(8)
    probe = LinearProbe(8, alpha=1e-8).fit(x, y)
    conf = probe.confusion(x, y)
    assert conf.sum() == 8
    assert np.array_equal(conf, np.eye(8, dtype=conf.dtype))
    assert decoded_information(conf) == pytest.approx(3.0)


def test_probe_raises_without_labelled_frames():
    with pytest.raises(ValueError, match="no labelled frames"):
        LinearProbe(3).fit(np.zeros((4, 2)), np.full(4, UNLABELLED))


# --- calibration ------------------------------------------------------------

def test_calibration_hits_its_target_event_rate(tiny):
    target = 3000.0
    value, achieved, _ = calibrate_rate_param(
        tiny, "E1", target, n_channels=8, front_end=FRONT_END,
        bracket=(1e-4, 1e2), tol=0.05)
    assert achieved == pytest.approx(target, rel=0.05)
    assert value > 0.0


def test_calibration_reports_an_unreachable_target(tiny):
    with pytest.raises(ValueError, match="outside the reachable range"):
        calibrate_rate_param(tiny, "E1", 1e12, n_channels=8,
                             front_end=FRONT_END, bracket=(1e-4, 1e2))


# --- the run, and whether its controls bite ---------------------------------

@pytest.fixture(scope="module")
def encoded(tiny):
    value, _, _ = calibrate_rate_param(tiny, "E1", 3000.0, n_channels=8,
                                       front_end=FRONT_END,
                                       bracket=(1e-4, 1e2), tol=0.1)
    return encode_corpus(tiny, "E1", [value], 8, FRONT_END)[float(value)]


def test_run_t1_beats_its_floor_and_reports_every_control(tiny, encoded):
    r = run_t1(tiny, encoded, test_fraction=0.5, seed=0)
    assert r["accuracy"] > r["chance"]
    for key in ("majority_floor", "chance", "shuffled_label_accuracy",
                "misaligned_accuracy", "budget_cross_check", "split",
                "lambda_events_per_s", "decoded_information_bits",
                "probe_settings"):
        assert key in r, f"{key} missing — a control that is not reported "
    assert r["budget_cross_check"]["agree"]
    assert r["probe_converged"]


def test_c3_shuffled_labels_return_to_the_floor(tiny, encoded):
    """The primary leakage detector. A probe fitted on permuted training labels
    must not generalise; if it does, something is shared across the split."""
    r = run_t1(tiny, encoded, test_fraction=0.5, seed=0)
    assert r["shuffled_label_accuracy"] < r["accuracy"]
    assert r["shuffled_label_accuracy"] <= r["majority_floor"] + 0.10


def test_c5_bites_on_a_dataset_where_alignment_is_everything():
    """C5 is worth nothing unless a misalignment actually costs accuracy, so
    the control is exercised on data built so that it must: the label is a
    function of the frame, and neighbouring frames are independent."""
    rng = np.random.default_rng(17)
    n, k = 400, 4
    y = rng.integers(0, k, n)
    x = np.eye(k)[y] + 0.05 * rng.standard_normal((n, k))

    aligned = LinearProbe(k).fit(x[:300], y[:300]).score(x[300:], y[300:])
    shifted = shift_labels(y, 1)
    misaligned = LinearProbe(k).fit(x[:300], shifted[:300]).score(
        x[300:], shifted[300:])
    assert aligned > 0.95
    assert misaligned < 0.5


def test_build_dataset_pairs_each_frame_with_its_own_utterance(tiny, encoded):
    labelset = LabelSet(PHONES)
    x, y, uid = build_dataset(encoded, tiny, labelset, 0.005, 0.010, 0)
    assert x.shape[0] == y.shape[0] == uid.shape[0]
    assert x.shape[1] == 2 * 8            # ON channels then OFF, SPEC section 5
    for u in tiny:
        n_own = int(np.sum(uid == u.uid))
        assert n_own == len(frame_labels(u, 0.010, labelset))
