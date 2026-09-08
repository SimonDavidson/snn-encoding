"""Tests for the TIMIT reader — written before TIMIT arrives, deliberately.

Implementation-session tests. The corpus is LDC-licensed, the licence question
is open O2, and this machine has no `soundfile`, no `sph2pipe`, no `sox` and no
`ffmpeg`. What can still be established today is that the reader parses the
format it will be handed, and that it fails by name rather than by silence
when handed the one it cannot.

The SPHERE files here are written by `sphere.write_sphere`, which is only
worth something because both halves were written from the format description
rather than from each other: the writer emits a header built from the SPHERE
field list, and the parser reads it back without knowing what wrote it. That
does not prove either matches TIMIT. It does prove the byte order, the sample
scaling, the declared-size offset and the multi-channel deinterleave are
self-consistent, which is where a reader of a binary container goes wrong.

Runs on numpy and scipy alone, because CI installs `.[dev]` and nothing more.

Author:        Simon Davidson & Claude
Created:       2026-09-08
Last modified: 2026-09-08
"""
import numpy as np
import pytest

from spikeenc.corpus import (SA_SENTENCES, TIMIT_39, TIMIT_61_TO_39,
                             fold_to_39, read_phn, timit_corpus)
from spikeenc.sphere import (UnsupportedEncoding, read_audio, read_sphere,
                             read_sphere_header, write_sphere)

# One utterance's worth of TIMIT-shaped annotation, at 16 kHz. Closures and
# the leading/trailing h# are what make the 39-symbol collapse do anything.
PHN = [(0, 1600, "h#"), (1600, 2400, "pcl"), (2400, 3200, "p"),
       (3200, 4800, "ix"), (4800, 5600, "q"), (5600, 7200, "ao"),
       (7200, 8000, "tcl"), (8000, 8800, "t"), (8800, 9600, "h#")]


def _tone(n, fs=16000, f=440.0, amp=0.5):
    return amp * np.sin(2 * np.pi * f * np.arange(n) / fs)


def _make_tree(root, speakers=("FCJF0", "MDAB0"), sentences=("SA1", "SI648"),
               subset="TRAIN", ext=".WAV"):
    """A miniature TIMIT: root/TRAIN/DR1/<speaker>/<sentence>.{WAV,PHN}."""
    for speaker in speakers:
        d = root / subset / "DR1" / speaker
        d.mkdir(parents=True, exist_ok=True)
        for sentence in sentences:
            write_sphere(d / f"{sentence}{ext}", _tone(9600), 16000)
            (d / f"{sentence}.PHN").write_text(
                "".join(f"{a} {b} {lab}\n" for a, b, lab in PHN))
    return root


# --- the container ----------------------------------------------------------

def test_sphere_round_trips_through_the_declared_header_size(tmp_path):
    x = _tone(4000)
    p = write_sphere(tmp_path / "a.WAV", x, 16000)
    y, rate = read_sphere(p)
    assert rate == 16000
    assert y.shape == x.shape
    assert np.max(np.abs(y - x)) < 2 ** -14


def test_a_larger_header_does_not_shift_the_audio(tmp_path):
    """The payload starts at the size the header declares, not at wherever the
    parser stopped reading. A file padded to 2048 read as if padded to 1024
    gives audio that is entirely plausible and entirely wrong."""
    x = _tone(4000)
    p = write_sphere(tmp_path / "b.WAV", x, 16000, header_size=2048)
    y, _ = read_sphere(p)
    assert np.max(np.abs(y - x)) < 2 ** -14


def test_big_endian_samples_are_honoured(tmp_path):
    """`sample_byte_format 10` is big-endian. Ignoring it does not fail; it
    produces a waveform whose every sample is byte-swapped noise."""
    x = _tone(2000)
    p = write_sphere(tmp_path / "c.WAV", x, 16000)
    raw = (tmp_path / "c.WAV").read_bytes()
    header, data = raw[:1024], raw[1024:]
    header = header.replace(b"sample_byte_format -s2 01",
                            b"sample_byte_format -s2 10")
    swapped = np.frombuffer(data, dtype="<i2").astype(">i2").tobytes()
    (tmp_path / "d.WAV").write_bytes(header.ljust(1024, b" ") + swapped)
    y, _ = read_sphere(tmp_path / "d.WAV")
    assert np.max(np.abs(y - x)) < 2 ** -14


def test_multichannel_is_deinterleaved(tmp_path):
    s = np.vstack([_tone(2000), -_tone(2000)])
    p = write_sphere(tmp_path / "e.WAV", s, 8000)
    y, rate = read_sphere(p)
    assert rate == 8000 and y.shape == (2, 2000)
    assert np.max(np.abs(y - s)) < 2 ** -14


def test_shorten_compressed_sphere_raises_with_the_tool_named(tmp_path):
    """The failure this reader exists to make loud. `sph2pipe` and `sox` are
    both absent from this machine, so the message has to say what would work
    rather than leave a caller to guess from a stack trace."""
    p = write_sphere(tmp_path / "f.WAV", _tone(800), 16000)
    raw = p.read_bytes()
    raw = raw.replace(b"sample_coding -s3 pcm",
                      b"sample_coding -s26 pcm,embedded-shorten-v2.00")
    p.write_bytes(raw[:1024].ljust(1024, b" ") + raw[1024:])
    with pytest.raises(UnsupportedEncoding, match="sph2pipe"):
        read_sphere(p)


def test_read_audio_dispatches_on_magic_and_not_on_extension(tmp_path):
    """TIMIT's SPHERE files are named `.WAV`. A loader trusting the name hands
    a 1024-byte ASCII header to a RIFF parser."""
    from scipy.io import wavfile
    sphere = write_sphere(tmp_path / "g.WAV", _tone(1000), 16000)
    riff = tmp_path / "h.WAV"
    wavfile.write(riff, 16000, (_tone(1000) * 32767).astype(np.int16))

    a, _ = read_audio(sphere)
    b, _ = read_audio(riff)
    assert np.max(np.abs(a - b)) < 2 ** -13


def test_a_file_that_is_neither_container_says_so(tmp_path):
    p = tmp_path / "i.WAV"
    p.write_bytes(b"fLaC" + b"\x00" * 100)
    with pytest.raises(ValueError, match="not RIFF WAV and not NIST SPHERE"):
        read_audio(p)


def test_header_without_end_head_raises(tmp_path):
    p = tmp_path / "j.WAV"
    p.write_bytes(b"NIST_1A\n    128\nsample_rate -i 16000\n".ljust(128, b" "))
    with pytest.raises(ValueError, match="end_head"):
        with open(p, "rb") as fh:
            read_sphere_header(fh)


# --- the annotation ---------------------------------------------------------

def test_phn_times_come_from_the_file_sample_rate(tmp_path):
    p = tmp_path / "k.PHN"
    p.write_text("0 1600 h#\n1600 3200 iy\n")
    at16 = read_phn(p, 16000)
    at8 = read_phn(p, 8000)
    assert at16[1].start == 0.1 and at8[1].start == 0.2


# --- the corpus -------------------------------------------------------------

def test_corpus_loads_with_speaker_and_uid_from_the_layout(tmp_path):
    corpus = timit_corpus(_make_tree(tmp_path), exclude_sa=False)
    assert len(corpus) == 4
    assert corpus.speakers == ["FCJF0", "MDAB0"]
    assert {u.uid for u in corpus} == {"FCJF0_SA1", "FCJF0_SI648",
                                       "MDAB0_SA1", "MDAB0_SI648"}
    u = corpus.utterances[0]
    assert u.sample_rate == 16000
    assert abs(u.duration - 0.6) < 1e-9
    assert u.segments[0].label == "h#"
    assert len(u.boundaries()) == len(PHN) - 1


def test_sa_sentences_are_excluded_by_default(tmp_path):
    corpus = timit_corpus(_make_tree(tmp_path))
    assert all(u.uid.split("_")[1] not in SA_SENTENCES for u in corpus)
    assert len(corpus) == 2


def test_lowercase_distributions_load_the_same(tmp_path):
    """Copies differ on case, and `.WAV` matched literally finds nothing on
    half of them — a silent empty corpus rather than an error."""
    corpus = timit_corpus(_make_tree(tmp_path, ext=".wav"), exclude_sa=False)
    assert len(corpus) == 4


def test_an_empty_root_says_what_it_expected(tmp_path):
    with pytest.raises(FileNotFoundError, match="TRAIN/DR1"):
        timit_corpus(tmp_path)


def test_t2_is_unavailable_rather_than_invented(tmp_path):
    """TIMIT carries no f0. Proposal 4.2 wants two trackers and their measured
    disagreement; until one exists the utterances must have no contour, so T2
    raises by name instead of scoring something made up (Q40)."""
    from spikeenc.tasks import f0_targets
    corpus = timit_corpus(_make_tree(tmp_path))
    assert corpus.utterances[0].f0 is None
    with pytest.raises(ValueError, match="no f0 reference"):
        f0_targets(corpus.utterances[0], 0.010)


def test_f0_fn_supplies_the_contour_when_one_exists(tmp_path):
    def tracker(audio, rate, hop):
        n = int(np.floor((len(audio) / rate) / hop)) + 1
        return np.full(n, 120.0), np.ones(n, dtype=bool)

    corpus = timit_corpus(_make_tree(tmp_path), f0_fn=tracker)
    u = corpus.utterances[0]
    assert u.f0 is not None and u.f0_hop == 0.010
    assert len(u.f0) == int(np.floor(u.duration / 0.010)) + 1


# --- the 39-symbol collapse -------------------------------------------------

def test_folding_merges_adjacent_silences_and_drops_the_glottal_stop(tmp_path):
    corpus = timit_corpus(_make_tree(tmp_path), exclude_sa=False)
    folded = fold_to_39(corpus)
    segments = folded.utterances[0].segments
    labels = [s.label for s in segments]
    assert labels == ["sil", "p", "ih", "aa", "sil", "t", "sil"]
    assert "q" not in labels
    # `h#` and the `pcl` after it both fold to `sil` and are adjacent, so the
    # nine input segments become seven and the boundary between them is gone —
    # which is the collapse doing its job, and the reason T3 must not use it.
    assert segments[0].start == 0.0 and segments[0].end == 0.15
    assert len(segments) == len(PHN) - 2
    # `ao` folds to `aa`, and the glottal stop leaves a labelled gap.
    assert folded.utterances[0].label_at(0.30) is None


def test_folded_labels_are_all_in_the_39_symbol_set(tmp_path):
    folded = fold_to_39(timit_corpus(_make_tree(tmp_path), exclude_sa=False))
    assert set(folded.labels) <= set(TIMIT_39)


def test_folding_never_maps_a_symbol_outside_the_39_set():
    """The table is provisional (Q39). What can be checked without the source
    is that it is internally consistent: every value it produces is a symbol
    the 39-set contains, or None."""
    for source, target in TIMIT_61_TO_39.items():
        assert target is None or target in TIMIT_39, f"{source} -> {target}"


def test_folding_leaves_boundaries_alone_in_the_unfolded_corpus(tmp_path):
    """T3 scores against the hand-placed boundaries, and folding deletes some
    of them by construction. The corpus it is given must be the unfolded one,
    so folding has to return a new corpus rather than mutate."""
    corpus = timit_corpus(_make_tree(tmp_path), exclude_sa=False)
    before = [u.boundaries().copy() for u in corpus]
    fold_to_39(corpus)
    for u, b in zip(corpus, before):
        assert np.array_equal(u.boundaries(), b)
