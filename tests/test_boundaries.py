"""Tests for T3's peak picking, matching and segmentation metrics.

Implementation-session tests. Proposal 4.3 fixes the metrics and the tolerance
and nothing between a frame-wise score and a list of instants, so most of what
is testable here is that the choices filling that gap behave as their docstrings
claim — in particular that they are symmetric in time, since T3 is a task about
timing and an asymmetric rule would bias it in a direction no reported number
would reveal.

The R-value is checked against the two points its definition pins exactly:
perfect segmentation gives 1, and pure over-segmentation is penalised.

Runs on numpy and scipy alone.

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-07
"""
import numpy as np
import pytest

from spikeenc.boundaries import (DEFAULT_TOLERANCE, frame_auc,
                                 match_boundaries, pick_peaks, r_value,
                                 score_boundaries, uniform_baseline)
from spikeenc.corpus import Segment, Utterance, synthetic_corpus
from spikeenc.tasks import boundary_labels


# --- peak picking -----------------------------------------------------------

def test_pick_peaks_finds_local_maxima_above_threshold():
    score = np.array([0.0, 0.9, 0.0, 0.1, 0.0, 0.8, 0.0])
    peaks = pick_peaks(score, hop=0.010, threshold=0.5, min_separation=0.0)
    assert np.allclose(peaks, [0.010, 0.050])


def test_pick_peaks_suppresses_strongest_first_not_left_to_right():
    """A weak peak must not suppress a stronger one that follows it. A
    left-to-right rule would, making the output depend on the direction of
    time in a task whose whole subject is timing."""
    score = np.array([0.0, 0.6, 0.0, 0.95, 0.0])
    peaks = pick_peaks(score, hop=0.010, threshold=0.5, min_separation=0.030)
    assert np.allclose(peaks, [0.030])          # the 0.95, not the 0.6


def test_pick_peaks_returns_empty_when_nothing_clears_the_threshold():
    assert pick_peaks(np.array([0.1, 0.2, 0.1]), 0.010, 0.9).size == 0
    assert pick_peaks(np.array([]), 0.010, 0.1).size == 0


def test_pick_peaks_respects_minimum_separation():
    score = np.array([0.0, 0.9, 0.0, 0.8, 0.0, 0.7, 0.0])
    close = pick_peaks(score, 0.010, 0.5, min_separation=0.050)
    assert len(close) == 1
    far = pick_peaks(score, 0.010, 0.5, min_separation=0.010)
    assert len(far) == 3


# --- matching ---------------------------------------------------------------

def test_matching_is_one_to_one():
    """Two detections straddling one boundary must give one hit and one false
    positive — otherwise over-segmentation would be free."""
    hits, pairs = match_boundaries([0.095, 0.105], [0.100], tolerance=0.020)
    assert hits == 1
    assert len(pairs) == 1


def test_matching_takes_the_nearest_pair_first():
    """An index-order rule would let a poor early match consume a reference
    that a later exact match wanted."""
    hits, pairs = match_boundaries([0.115, 0.100], [0.100], tolerance=0.020)
    assert hits == 1
    assert pairs[0][0] == 1                     # the exact one, not the first


def test_matching_respects_the_tolerance():
    assert match_boundaries([0.100], [0.121], tolerance=0.020)[0] == 0
    assert match_boundaries([0.100], [0.119], tolerance=0.020)[0] == 1


def test_matching_handles_empty_sides():
    assert match_boundaries([], [0.1])[0] == 0
    assert match_boundaries([0.1], [])[0] == 0


# --- the metrics ------------------------------------------------------------

def test_r_value_is_one_for_perfect_segmentation():
    assert r_value(1.0, 0.0) == pytest.approx(1.0)


def test_r_value_penalises_over_segmentation_that_f_score_tolerates():
    """The reason 4.3 asks for it. Doubling the detections to buy recall keeps
    F-score respectable and must not keep the R-value respectable."""
    ref = [np.array([0.1, 0.3, 0.5])]
    honest = [np.array([0.1, 0.3, 0.5])]
    greedy = [np.array([0.1, 0.15, 0.3, 0.35, 0.5, 0.55])]
    a = score_boundaries(honest, ref)
    b = score_boundaries(greedy, ref)
    assert a["recall"] == b["recall"] == 1.0
    assert b["f_score"] > 0.6                   # F-score barely notices
    assert b["r_value"] < a["r_value"] - 0.3    # the R-value does


def test_score_boundaries_pools_counts_across_utterances():
    """Ratios formed after pooling, so a two-boundary utterance does not weigh
    as much as a twenty-boundary one."""
    s = score_boundaries([np.array([0.1]), np.array([0.2, 0.4])],
                         [np.array([0.1]), np.array([0.2, 0.9])])
    assert s["n_reference"] == 3 and s["n_predicted"] == 3
    assert s["n_hit"] == 2
    assert s["precision"] == pytest.approx(2 / 3)


def test_score_boundaries_of_nothing_is_zero_not_a_crash():
    s = score_boundaries([np.array([])], [np.array([0.1])])
    assert s["f_score"] == 0.0 and s["recall"] == 0.0


# --- the AUC, which is what makes an F-score interpretable ------------------

def test_frame_auc_extremes():
    assert frame_auc(np.array([0., 0., 1., 1.]), np.array([0, 0, 1, 1])) == 1.0
    assert frame_auc(np.array([1., 1., 0., 0.]), np.array([0, 0, 1, 1])) == 0.0


def test_frame_auc_of_a_constant_score_is_exactly_chance():
    """A probe that has learned nothing outputs a flat posterior. Untied ranks
    would give this 0.5 only by luck; the tie correction makes it exact."""
    assert frame_auc(np.full(100, 0.3), np.r_[np.zeros(80), np.ones(20)]) == 0.5


def test_frame_auc_is_insensitive_to_the_positive_rate():
    """Unlike accuracy, which a 17 per cent positive rate would flatter."""
    rng = np.random.default_rng(0)
    for n_pos in (5, 50, 95):
        label = np.r_[np.zeros(100 - n_pos), np.ones(n_pos)]
        score = rng.permutation(len(label)).astype(float)
        assert 0.3 < frame_auc(score, label) < 0.7


def test_frame_auc_is_nan_without_both_classes():
    assert np.isnan(frame_auc(np.array([1., 2.]), np.array([1, 1])))


# --- the C2 floor -----------------------------------------------------------

def test_uniform_baseline_places_the_reference_number_of_boundaries():
    out = uniform_baseline([1.0, 2.0], [3, 1])
    assert len(out[0]) == 3 and len(out[1]) == 1
    assert np.allclose(out[0], [0.25, 0.5, 0.75])


def test_uniform_baseline_is_a_real_floor_on_this_corpus():
    """Recorded because it is the finding, not an incidental check: on the
    stand-in, evenly spaced boundaries at the reference rate score well, so any
    learned detector has to clear a high bar it may not be able to reach."""
    corpus = synthetic_corpus(n_speakers=3, utterances_per_speaker=1, seed=2)
    ref = [u.boundaries() for u in corpus]
    base = uniform_baseline([u.duration for u in corpus],
                            [len(b) for b in ref])
    s = score_boundaries(base, ref, DEFAULT_TOLERANCE)
    assert s["over_segmentation"] == pytest.approx(0.0)
    assert s["f_score"] > 0.25


# --- the training target ----------------------------------------------------

def test_boundary_labels_need_a_tolerance_to_be_learnable():
    """With zero tolerance almost no frame is positive, because a boundary
    essentially never falls exactly on a frame instant."""
    u = Utterance(uid="u", speaker="S", audio=np.zeros(1000), sample_rate=1000,
                  segments=(Segment(0.0, 0.035, "a"), Segment(0.035, 1.0, "b")))
    assert boundary_labels(u, 0.010, tolerance_frames=0).sum() == 0
    assert boundary_labels(u, 0.010, tolerance_frames=1).sum() == 2


def test_boundary_labels_ignore_the_utterance_start():
    """t = 0 is the start of the first segment, not a boundary between two."""
    u = Utterance(uid="u", speaker="S", audio=np.zeros(1000), sample_rate=1000,
                  segments=(Segment(0.0, 0.5, "a"), Segment(0.5, 1.0, "b")))
    y = boundary_labels(u, 0.010, tolerance_frames=1)
    assert y[0] == 0
    assert y[50] == 1
