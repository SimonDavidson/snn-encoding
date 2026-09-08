"""Tests for free-parameter selection — validation protocol section 13, D71.

Implementation-session tests. Two kinds live here.

The first are unit tests of the mechanism: that the folds are speaker-disjoint
and use every training speaker exactly once, that the grid is recorded, that
the C5 restatement of D70 fails on an edge and on a plateau as well as passing
on a peak.

The second is the one that matters, and it is a property rather than a value:
**the selected parameter must not change when the test set changes.** That is
the whole content of D71, it is mechanically checkable, and it is what the
harness failed for three tasks until 2026-09-08 while every other test passed.
A test asserting a particular offset would have gone on passing throughout,
because the offsets the old code chose were not obviously wrong — they were
merely chosen against the number being reported.

Runs on numpy and scipy alone, because CI installs `.[dev]` and nothing more.

Author:        Simon Davidson & Claude
Created:       2026-09-08
Last modified: 2026-09-08
"""
import dataclasses

import numpy as np
import pytest

from spikeenc.corpus import synthetic_corpus
from spikeenc.harness import (build_dataset, encode_corpus, run_t2, run_t3,
                              score_t1)
from spikeenc.selection import (fold_sizes, interior_maximum,
                                predicted_offset, profile_scores,
                                select_on_folds, speaker_folds)
from spikeenc.splits import speaker_disjoint_split
from spikeenc.tasks import LabelSet

FRONT_END = {"envelope": "hilbert", "compression": "power"}
SPEAKERS = {f"u{i}": f"s{i // 2}" for i in range(12)}      # 6 speakers, 2 each


@pytest.fixture(scope="module")
def corpus():
    return synthetic_corpus(n_speakers=4, utterances_per_speaker=1,
                            phones_per_utterance=5, seed=3)


@pytest.fixture(scope="module")
def trains(corpus):
    return encode_corpus(corpus, "E1", [0.05], 8, FRONT_END)[0.05]


# --- the folds --------------------------------------------------------------

def test_folds_are_speaker_disjoint_and_cover_every_speaker_once():
    folds = speaker_folds(list(SPEAKERS), SPEAKERS, n_folds=3, seed=0)
    assert len(folds) == 3
    validated = []
    for fit, val in folds:
        fit_spk = {SPEAKERS[u] for u in fit}
        val_spk = {SPEAKERS[u] for u in val}
        assert not (fit_spk & val_spk), "a speaker on both sides of a fold"
        assert fit | val == set(SPEAKERS)
        validated += sorted(val_spk)
    assert sorted(validated) == sorted(set(SPEAKERS.values()))


def test_fold_count_is_capped_at_the_number_of_speakers():
    """Asking for more folds than speakers gives leave-one-speaker-out, not
    empty folds: `min(n_folds, n_speakers)` rather than a silent failure."""
    folds = speaker_folds(list(SPEAKERS), SPEAKERS, n_folds=99, seed=0)
    assert len(folds) == 6
    assert all(len({SPEAKERS[u] for u in val}) == 1 for _, val in folds)


def test_one_speaker_yields_no_folds_rather_than_a_leaking_one():
    single = {"a": "s0", "b": "s0"}
    assert speaker_folds(list(single), single, n_folds=3, seed=0) == []


def test_fold_sizes_are_recorded():
    folds = speaker_folds(list(SPEAKERS), SPEAKERS, n_folds=3, seed=0)
    sizes = fold_sizes(folds, SPEAKERS)
    assert [s["n_val_speakers"] for s in sizes] == [2, 2, 2]
    assert all(s["n_fit_speakers"] == 4 for s in sizes)


# --- the selector -----------------------------------------------------------

def test_selection_records_the_whole_grid_and_picks_the_best():
    folds = speaker_folds(list(SPEAKERS), SPEAKERS, n_folds=3, seed=0)
    chosen, grid = select_on_folds([1, 2, 3], folds,
                                   lambda c, f, v: -abs(c - 2))
    assert chosen == 2
    assert set(grid) == {"1", "2", "3"}
    assert all(g["n_folds_scored"] == 3 for g in grid.values())
    assert profile_scores(grid) == {"1": -1.0, "2": 0.0, "3": -1.0}


def test_selection_can_minimise_and_can_name_its_criterion():
    folds = speaker_folds(list(SPEAKERS), SPEAKERS, n_folds=3, seed=0)
    chosen, _ = select_on_folds(
        [1, 2, 3], folds, lambda c, f, v: {"rmse": abs(c - 3), "r": -c},
        criterion="rmse", maximise=False)
    assert chosen == 3


def test_a_single_candidate_is_returned_without_fitting_anything():
    """P2 holds the alignment at its clean best (D62) and passes one candidate.
    Evaluating it on every fold would be three fits to choose between one."""
    folds = speaker_folds(list(SPEAKERS), SPEAKERS, n_folds=3, seed=0)

    def explode(c, f, v):
        raise AssertionError("evaluate must not be called for one candidate")

    chosen, grid = select_on_folds([7], folds, explode)
    assert chosen == 7
    assert grid["7"]["n_folds_scored"] == 0


def test_a_criterion_that_is_never_returned_raises():
    """Silently falling back to the first candidate would look like a
    selection and be an alphabetical accident."""
    folds = speaker_folds(list(SPEAKERS), SPEAKERS, n_folds=3, seed=0)
    with pytest.raises(KeyError, match="never returned"):
        select_on_folds([1, 2], folds, lambda c, f, v: {"r": c},
                        criterion="rmse")


# --- C5 as D70 restates it --------------------------------------------------

def test_interior_maximum_passes_on_a_peak():
    p = {"-3": 0.1, "-2": 0.3, "-1": 0.6, "0": 0.9, "1": 0.5, "2": 0.2}
    assert interior_maximum(p, 0)["interior_maximum"]


def test_interior_maximum_fails_at_the_edge_of_the_swept_range():
    """The failure D70 was written for: the old control confirmed a drop at
    plus or minus one, which an offset sitting on the edge of the grid can
    satisfy while the true optimum is outside it entirely."""
    p = {"-2": 0.9, "-1": 0.6, "0": 0.3}
    v = interior_maximum(p, -2)
    assert not v["interior_maximum"]
    assert v["missing_offsets"] == [-4, -3]


def test_interior_maximum_fails_on_a_plateau():
    """A control that cannot separate the selected offset from its neighbour
    has not shown the alignment carries information, which is its only job."""
    p = {"-2": 0.5, "-1": 0.9, "0": 0.9, "1": 0.5, "2": 0.3}
    assert not interior_maximum(p, 0)["interior_maximum"]
    assert interior_maximum(p, 0)["offsets_not_lower"] == [-1]


def test_predicted_offset_is_negative_for_a_lagging_front_end():
    """A feature at frame k describes audio `lag` earlier, so the label that
    matches it sits back in time and the offset is negative."""
    assert predicted_offset(0.0096, 0.010) == -1
    assert predicted_offset(0.0246, 0.010) == -2
    assert predicted_offset(0.0, 0.010) == 0


# --- the property that is D71 -----------------------------------------------

def _perturb_test_labels(y, uid, corpus, split, seed=5):
    """Permute the labels of the test utterances and leave training alone."""
    rng = np.random.default_rng(seed)
    out = y.copy()
    rows = np.flatnonzero(np.isin(uid, np.asarray(split.test, dtype=object)))
    out[rows] = y[rng.permutation(rows)]
    return out


def test_t1_selects_the_same_offset_when_the_test_labels_are_destroyed(
        corpus, trains):
    """D71 as a property. The offset is chosen inside the training split, so
    replacing the test labels with noise must move the reported accuracy and
    must not move the selection. Before D71 this failed: the offset was the
    argmax of the test score and followed the noise."""
    labelset = LabelSet(corpus.labels)
    x, y, uid = build_dataset(trains, corpus, labelset, 0.005, 0.010, 0)
    split = speaker_disjoint_split(corpus, test_fraction=0.5, seed=0)
    kwargs = dict(labelset=labelset, test_fraction=0.5, seed=0,
                  offsets=(-2, -1, 0, 1), n_folds=2)

    clean = score_t1(corpus, x, y, uid, **kwargs)
    noisy = score_t1(corpus, x, _perturb_test_labels(y, uid, corpus, split),
                     uid, **kwargs)

    assert clean["best_offset"] == noisy["best_offset"]
    assert clean["accuracy"] != noisy["accuracy"], (
        "the perturbation did not reach the reported number, so the test "
        "proves nothing")


def _corpus_with_scrambled_test_f0(corpus, seed=0, test_fraction=0.5):
    """The same corpus with the f0 contour of every test utterance reversed."""
    split = speaker_disjoint_split(corpus, test_fraction=test_fraction,
                                   seed=seed)
    out = []
    for u in corpus:
        if u.uid in set(split.test):
            u = dataclasses.replace(u, f0=u.f0[::-1].copy())
        out.append(u)
    return dataclasses.replace(corpus, utterances=tuple(out))


def test_t2_selects_the_same_offset_when_the_test_contour_is_reversed(
        corpus, trains):
    """The same property for T2, whose selection is two parameters deep: the
    ridge penalty on validation RMSE and then the offset on the correlation."""
    kwargs = dict(test_fraction=0.5, seed=0, offsets=(-2, -1, 0),
                  n_folds=2, ridge_alphas=[1.0, 1000.0], context=1)
    clean = run_t2(corpus, trains, **kwargs)
    noisy = run_t2(_corpus_with_scrambled_test_f0(corpus), trains, **kwargs)

    assert clean["best_offset"] == noisy["best_offset"]
    assert clean["ridge_alpha_chosen"] == noisy["ridge_alpha_chosen"]
    assert (clean["pearson_per_utterance"]
            != noisy["pearson_per_utterance"])


def test_t3_threshold_and_offset_are_both_chosen_off_the_test_set(corpus,
                                                                 trains):
    """T3 has two free parameters and had one of them right. The threshold was
    always chosen on the fitting side; the offset was not."""
    kwargs = dict(test_fraction=0.5, seed=0, offsets=(-2, -1, 0), n_folds=2,
                  n_thresholds=9, context=1)
    r = run_t3(corpus, trains, **kwargs)
    assert r["selection"]["chosen"]["offset"] == r["best_offset"]
    assert "fitting side" in r["settings"]["threshold_selected_on"]
    # The grid that did the selecting is recorded, per D71.
    assert set(r["selection"]["grid"]) == {"-2", "-1", "0"}
    assert r["selection"]["n_folds"] == 2
