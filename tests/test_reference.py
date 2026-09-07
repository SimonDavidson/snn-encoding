"""Tests for R2, the non-spiking upper bound of proposal 5.9.

Implementation-session tests, like `test_harness.py` and unlike
`test_known_answers.py`. R2 has no SPEC section either; what 5.9 fixes is forty
bands, 25 ms, 10 ms hop and "the same decoder architecture as every spiking
condition", and the last of those is the one worth testing, because it is the
one that would silently stop being true.

Runs on numpy and scipy alone.

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-07
"""
import numpy as np
import pytest

from spikeenc.corpus import PHONES, synthetic_corpus
from spikeenc.features import featurise
from spikeenc.harness import run_t1_reference
from spikeenc.reference import (feature_bandwidth_bps, frame_signal,
                                mel_features, mel_filters)
from spikeenc.spiketrain import SpikeTrain
from spikeenc.tasks import LabelSet, frame_labels


@pytest.fixture(scope="module")
def tiny():
    return synthetic_corpus(n_speakers=4, utterances_per_speaker=1,
                            phones_per_utterance=5, seed=3)


# --- the filterbank ---------------------------------------------------------

def test_mel_filters_tile_the_range_without_gaps():
    """Adjacent triangles overlap at half amplitude, so the summed response is
    flat away from the edges. A gap would silently discard a frequency band."""
    f = mel_filters(40, 512, 16000, f_min=50.0, f_max=8000.0)
    assert f.shape == (40, 257)
    assert np.all(f >= 0.0)
    total = f.sum(axis=0)
    interior = total[(np.fft.rfftfreq(512, 1 / 16000) > 200)
                     & (np.fft.rfftfreq(512, 1 / 16000) < 6000)]
    assert np.all(interior > 0.5)


def test_mel_filters_are_ordered_low_to_high():
    f = mel_filters(20, 512, 16000)
    peaks = np.argmax(f, axis=1)
    assert np.all(np.diff(peaks) > 0)


def test_mel_filters_reject_a_daft_band_count():
    with pytest.raises(ValueError, match="at least 1"):
        mel_filters(0, 512, 16000)


# --- framing, which is where the alignment decision lives -------------------

def test_causal_window_ends_at_the_frame_instant():
    """Frame k must summarise only audio at or before t = k*hop, matching the
    strictly causal kernel of equation (32). If it looked ahead, R2 would beat
    every spiking condition partly by seeing the future."""
    fs, hop, frame = 1000, 0.010, 0.025
    x = np.arange(200, dtype=np.float64)
    f = frame_signal(x, fs, n_frames=5, frame=frame, hop=hop,
                     alignment="causal")
    assert f.shape == (5, 25)
    for k in range(5):
        assert f[k, -1] == float(k * 10)          # last sample is t = k*hop
        assert np.all(f[k][f[k] > 0] <= k * 10)   # nothing later, ever


def test_centred_window_straddles_the_frame_instant():
    fs, hop, frame = 1000, 0.010, 0.025
    x = np.arange(200, dtype=np.float64)
    f = frame_signal(x, fs, n_frames=5, frame=frame, hop=hop,
                     alignment="centred")
    k = 4
    assert f[k, 12] == float(k * 10)              # centre sample is t = k*hop
    assert f[k, -1] > k * 10                      # and it does see ahead


def test_framing_zero_pads_rather_than_wrapping():
    x = np.ones(50)
    f = frame_signal(x, 1000, n_frames=3, frame=0.025, hop=0.010,
                     alignment="causal")
    assert f[0, 0] == 0.0            # frame 0's window starts before the signal
    assert f[0, -1] == 1.0


def test_framing_rejects_an_unknown_alignment():
    with pytest.raises(ValueError, match="unknown alignment"):
        frame_signal(np.zeros(100), 1000, 3, alignment="sideways")


# --- the features -----------------------------------------------------------

def test_mel_features_share_the_spiking_frame_grid(tiny):
    """The whole comparison rests on R2 and the encoders being scored on the
    same frames against the same labels."""
    labelset = LabelSet(PHONES)
    for u in tiny:
        f = mel_features(u, n_mels=40, hop=0.010)
        n_spiking = featurise(SpikeTrain.empty(4, u.duration), hop=0.010).shape[0]
        assert f.shape == (n_spiking, 40)
        assert len(frame_labels(u, 0.010, labelset, n_frames=f.shape[0])) == n_spiking


def test_mel_features_are_finite_on_silence():
    """log(0) is -inf and would poison the probe. LOG_FLOOR is what stops it."""
    from spikeenc.corpus import Utterance
    silent = Utterance(uid="z", speaker="S", audio=np.zeros(8000),
                       sample_rate=16000)
    f = mel_features(silent)
    assert np.all(np.isfinite(f))


def test_mel_features_track_a_tone_to_the_right_band():
    """A pure tone lights the band containing it, and a higher tone lights a
    higher band. Cheap, and it is the check that would catch the mel scale
    being inverted or the filters being misindexed against the FFT bins."""
    from spikeenc.corpus import Utterance
    fs = 16000
    t = np.arange(fs) / fs

    peaks = {}
    for freq in (300.0, 3000.0):
        u = Utterance(uid="t", speaker="S", audio=np.sin(2 * np.pi * freq * t),
                      sample_rate=fs)
        f = mel_features(u, n_mels=40)
        peaks[freq] = int(np.argmax(f[50]))   # a frame well inside the tone
        # The peak band stands clear of the bank's lowest band.
        assert f[50, peaks[freq]] > f[50, 0] + 1.0

    assert peaks[3000.0] > peaks[300.0]


def test_mel_features_are_deterministic(tiny):
    u = tiny.utterances[0]
    assert np.array_equal(mel_features(u), mel_features(u))


def test_feature_bandwidth_is_the_dense_rate():
    """40 features x 32 bits x 100 frames/s."""
    assert feature_bandwidth_bps(40, 0.010, 32) == pytest.approx(128000.0)


# --- the run ----------------------------------------------------------------

def test_r2_runs_the_same_controls_as_a_spiking_condition(tiny):
    r = run_t1_reference(tiny, n_mels=20, test_fraction=0.5, seed=0)
    for key in ("accuracy", "majority_floor", "chance",
                "shuffled_label_accuracy", "misaligned_accuracy", "split",
                "decoded_information_bits", "probe_settings"):
        assert key in r, f"{key} missing — R2 must carry every control"
    assert r["accuracy"] > r["chance"]
    assert r["shuffled_label_accuracy"] <= r["majority_floor"] + 0.10
    assert r["reference"] == "R2"
    assert r["lambda_events_per_s"] == 0.0        # non-spiking, by definition


def test_r2_uses_the_identical_probe_settings_as_the_spiking_path(tiny):
    """C4 requires identical decoding. Both paths go through score_t1, so this
    holds by construction — the test is here to notice if that stops."""
    from spikeenc.harness import calibrate_rate_param, encode_corpus, run_t1
    fe = {"envelope": "hilbert", "compression": "power"}
    value, _, _ = calibrate_rate_param(tiny, "E1", 3000.0, n_channels=8,
                                       front_end=fe, bracket=(1e-4, 1e2),
                                       tol=0.1)
    trains = encode_corpus(tiny, "E1", [value], 8, fe)[float(value)]
    spiking = run_t1(tiny, trains, test_fraction=0.5, seed=0)
    r2 = run_t1_reference(tiny, n_mels=20, test_fraction=0.5, seed=0)
    assert r2["probe_settings"] == spiking["probe_settings"]
    assert r2["split"] == spiking["split"]
    assert r2["n_frames_train"] == spiking["n_frames_train"]
    assert r2["n_frames_test"] == spiking["n_frames_test"]


def test_r2_alignment_changes_the_answer(tiny):
    """If the two conventions scored identically the parameter would be inert
    and the Q24 concern misplaced. They do not."""
    causal = run_t1_reference(tiny, n_mels=20, alignment="causal",
                              test_fraction=0.5, seed=0)
    centred = run_t1_reference(tiny, n_mels=20, alignment="centred",
                               test_fraction=0.5, seed=0)
    assert causal["accuracy"] != centred["accuracy"]
