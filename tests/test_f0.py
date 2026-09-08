"""Tests for T2 — the ridge probe, the semitone scale, and the two correlations.

Implementation-session tests. The one that earns its place is
`test_pooled_correlation_is_won_by_voice_height_alone`: it builds a predictor
that emits one constant per utterance and knows nothing about any contour, and
shows it scores a high *pooled* correlation and none per utterance. That is the
whole argument for the headline choice, and a test is a better place for it than
a docstring because it fails if the code ever stops making the distinction.

Runs on numpy and scipy alone.

Author:        Simon Davidson & Claude
Created:       2026-09-08
Last modified: 2026-09-08
"""
import numpy as np
import pytest

from spikeenc.corpus import Utterance, synthetic_corpus
from spikeenc.harness import _per_utterance_pearson, _shift_indices
from spikeenc.probes import RidgeProbe
from spikeenc.tasks import SEMITONE_REF_HZ, f0_targets, semitones


# --- the semitone scale -----------------------------------------------------

def test_semitones_double_frequency_is_twelve():
    assert semitones(200.0, ref=100.0) == pytest.approx(12.0)
    assert semitones(100.0, ref=100.0) == pytest.approx(0.0)
    assert semitones(50.0, ref=100.0) == pytest.approx(-12.0)


def test_semitones_of_silence_is_nan_not_minus_infinity():
    """Unvoiced frames carry f0 = 0. log2(0) is -inf, which would poison a mean
    or an RMSE silently; NaN is excluded explicitly instead."""
    assert np.isnan(semitones(0.0))


def test_semitone_reference_shifts_but_does_not_scale():
    """A different reference is a constant offset, so it changes no correlation
    and no RMSE — which is why any constant works provided it is recorded."""
    f = np.array([100.0, 150.0, 220.0])
    a, b = semitones(f, ref=100.0), semitones(f, ref=440.0)
    assert np.allclose(np.diff(a), np.diff(b))


# --- the targets ------------------------------------------------------------

def test_f0_targets_refuse_a_hop_mismatch():
    """Resampling here would introduce the very misalignment C5 exists to
    catch, in the code meant to prevent it."""
    c = synthetic_corpus(n_speakers=2, utterances_per_speaker=1, seed=1)
    with pytest.raises(ValueError, match="does not match"):
        f0_targets(c.utterances[0], 0.020)


def test_f0_targets_refuse_an_utterance_with_no_reference():
    u = Utterance(uid="u", speaker="S", audio=np.zeros(1000), sample_rate=1000)
    with pytest.raises(ValueError, match="no f0 reference"):
        f0_targets(u, 0.010)


def test_f0_targets_are_nan_exactly_where_unvoiced():
    c = synthetic_corpus(n_speakers=2, utterances_per_speaker=1, seed=1)
    for u in c:
        s, v = f0_targets(u, 0.010)
        assert np.all(np.isnan(s[~v]))
        assert not np.any(np.isnan(s[v]))


def test_f0_targets_sit_on_the_spec_frame_grid():
    from spikeenc.features import featurise
    from spikeenc.spiketrain import SpikeTrain
    c = synthetic_corpus(n_speakers=2, utterances_per_speaker=1, seed=1)
    for u in c:
        s, _ = f0_targets(u, 0.010)
        assert len(s) == featurise(SpikeTrain.empty(4, u.duration),
                                   hop=0.010).shape[0]


# --- the ridge probe --------------------------------------------------------

def test_ridge_recovers_a_linear_target():
    rng = np.random.default_rng(3)
    x = rng.standard_normal((400, 6))
    w = np.array([2.0, -1.0, 0.5, 0.0, 3.0, -2.0])
    y = x @ w + 0.01 * rng.standard_normal(400)
    probe = RidgeProbe(alpha=1e-8, standardise=False).fit(x, y)
    assert np.allclose(probe.w, w, atol=0.02)


def test_ridge_is_bit_identical_across_fits():
    """Closed form, so there is no optimiser and nothing for a seed to control."""
    rng = np.random.default_rng(4)
    x, y = rng.standard_normal((100, 5)), rng.standard_normal(100)
    a, b = RidgeProbe().fit(x, y), RidgeProbe().fit(x, y)
    assert np.array_equal(a.w, b.w) and a.intercept == b.intercept


def test_ridge_intercept_is_the_training_mean():
    """Not a penalised coefficient: shrinking it would pull predictions toward
    zero semitones, which is 100 Hz and not a neutral point."""
    rng = np.random.default_rng(5)
    x = rng.standard_normal((50, 3))
    y = rng.standard_normal(50) + 7.0
    assert RidgeProbe(alpha=1e6).fit(x, y).intercept == pytest.approx(y.mean())


def test_ridge_alpha_shrinks_the_weights():
    rng = np.random.default_rng(6)
    x = rng.standard_normal((80, 4))
    y = x @ np.ones(4) + 0.1 * rng.standard_normal(80)
    small = RidgeProbe(alpha=1e-6).fit(x, y)
    large = RidgeProbe(alpha=1e4).fit(x, y)
    assert np.linalg.norm(large.w) < np.linalg.norm(small.w)


def test_ridge_refuses_an_empty_fit():
    with pytest.raises(ValueError, match="no frames"):
        RidgeProbe().fit(np.zeros((0, 3)), np.zeros(0))


# --- the two correlations, and why the headline is the per-utterance one ----

def test_pooled_correlation_is_won_by_voice_height_alone():
    """The argument for the headline choice, as a test.

    Three utterances with very different mean f0 and a small contour movement
    inside each — the shape of real speech, and of the stand-in. The predictor
    below emits each utterance's *mean* and nothing else: it has no contour
    information whatever. Pooled, it scores near-perfectly. Per utterance, it
    cannot be scored at all, because it has no variance to correlate.
    """
    utt = np.repeat(["a", "b", "c"], 20)
    means = np.repeat([0.0, 12.0, 24.0], 20)          # an octave apart
    rng = np.random.default_rng(8)
    contour = means + rng.standard_normal(60) * 0.5   # small movement within
    voice_height_only = means.astype(float)

    pooled = np.corrcoef(voice_height_only, contour)[0, 1]
    per_utt, excluded, scored = _per_utterance_pearson(
        voice_height_only, contour, utt)

    assert pooled > 0.99          # looks like a near-perfect f0 tracker
    assert scored == 0            # and tracks nothing at all
    assert excluded == 3
    assert np.isnan(per_utt)


def test_per_utterance_pearson_matches_a_hand_computation():
    utt = np.repeat(["a", "b"], 10)
    rng = np.random.default_rng(9)
    pred, ref = rng.standard_normal(20), rng.standard_normal(20)
    got, excluded, scored = _per_utterance_pearson(pred, ref, utt)
    expected = np.mean([np.corrcoef(pred[:10], ref[:10])[0, 1],
                        np.corrcoef(pred[10:], ref[10:])[0, 1]])
    assert got == pytest.approx(expected)
    assert excluded == 0 and scored == 2


def test_per_utterance_pearson_excludes_short_utterances():
    utt = np.array(["a"] * 3 + ["b"] * 10)
    rng = np.random.default_rng(10)
    pred, ref = rng.standard_normal(13), rng.standard_normal(13)
    _, excluded, scored = _per_utterance_pearson(pred, ref, utt, min_frames=5)
    assert excluded == 1 and scored == 1


# --- the offset convention --------------------------------------------------

def test_shift_indices_match_the_shift_labels_convention():
    """`shift_labels(y, o)[k]` is the target at `k+o`; this must agree, or T2's
    C5 offsets would mean something different from T1's and T3's."""
    from spikeenc.tasks import UNLABELLED, shift_labels
    n = 6
    for offset in (-2, -1, 0, 1, 2):
        src, valid = _shift_indices(n, offset)
        y = np.arange(n)
        shifted = shift_labels(y, offset)
        for k in range(n):
            if shifted[k] == UNLABELLED:
                assert not valid[k]
            else:
                assert valid[k] and src[k] == shifted[k]
