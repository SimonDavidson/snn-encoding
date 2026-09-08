"""Corpora — the interface between a body of audio and the probe harness.

The study runs on TIMIT (stage one) and the MANCHESTER Dataset (stage two),
neither of which is available on this machine: TIMIT is LDC-licensed and the
licence question is open O2, and the MANCHESTER Dataset is unrecorded. The
harness is therefore written against an *interface* rather than against a
corpus, with a synthetic corpus supplied here as a stand-in whose answer is
known by construction.

That is not a placeholder to be thrown away. A corpus whose ground truth is
generated rather than annotated is the only thing that can distinguish "the
probe scores 40 per cent because the encoder lost the information" from "the
probe scores 40 per cent because the harness mislabelled every frame". Real
corpora cannot make that distinction, because on a real corpus every number is
plausible. `timit_corpus` at the foot of this file implements the same three
attributes, so nothing downstream changes when the licence clears.

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-08
"""
import dataclasses
import pathlib
from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter, butter, sosfilt

from .sphere import read_audio


@dataclass(frozen=True)
class Segment:
    """A labelled interval, half-open in time: `start <= t < end`."""
    start: float
    end: float
    label: str


@dataclass(frozen=True)
class Utterance:
    """One recording, with everything the three probe tasks need.

    `segments` carries the phone labels T1 classifies and the boundaries T3
    detects. `f0` and `voiced` are sampled on a uniform grid of spacing
    `f0_hop` and carry T2's reference contour; on a real corpus they come from
    a pitch tracker and are a proxy reference (proposal 4.2), while here they
    are exact, which is the point of the stand-in.
    """
    uid: str
    speaker: str
    audio: np.ndarray
    sample_rate: int
    segments: tuple = ()
    f0: np.ndarray = None
    voiced: np.ndarray = None
    f0_hop: float = 0.010

    @property
    def duration(self) -> float:
        return len(self.audio) / self.sample_rate

    def label_at(self, t: float):
        """Label of the segment containing `t`, or None outside every segment."""
        for s in self.segments:
            if s.start <= t < s.end:
                return s.label
        return None

    def boundaries(self) -> np.ndarray:
        """Interior segment boundaries, in seconds — T3's ground truth."""
        if len(self.segments) < 2:
            return np.empty(0, dtype=np.float64)
        return np.array([s.start for s in self.segments[1:]], dtype=np.float64)


@dataclass(frozen=True)
class Corpus:
    """A named collection of utterances. Iterating yields `Utterance`s."""
    name: str
    utterances: tuple
    labels: tuple = ()          # the label inventory, in a fixed order

    def __iter__(self):
        return iter(self.utterances)

    def __len__(self):
        return len(self.utterances)

    @property
    def speakers(self):
        """Speaker identifiers, sorted — the unit C4 splits on."""
        return sorted({u.speaker for u in self.utterances})

    @property
    def total_duration(self) -> float:
        return sum(u.duration for u in self.utterances)


# --- the synthetic stand-in -------------------------------------------------

# Formant triples, in hertz, for a notional neutral speaker. These are textbook
# values for the corresponding English vowels; they are used because they are
# spread over the F1-F2 plane in the way real vowels are, not because the
# synthesiser is claimed to produce intelligible speech. It does not.
_VOWELS = {
    "iy": (280.0, 2250.0, 2890.0),
    "eh": (530.0, 1840.0, 2480.0),
    "aa": (710.0, 1100.0, 2540.0),
    "ao": (570.0, 840.0, 2410.0),
    "uw": (310.0, 870.0, 2250.0),
}

# Fricative-like: a noise band, given as (low, high) in hertz.
_FRICATIVES = {
    "s": (4000.0, 7800.0),
    "sh": (1800.0, 4000.0),
    "f": (1000.0, 7800.0),
}

PHONES = tuple(_VOWELS) + tuple(_FRICATIVES)
VOICED_PHONES = frozenset(_VOWELS)


def _resonator(f, bw, sample_rate):
    """Two-pole resonator at `f` hertz with -3 dB bandwidth `bw`.

    The standard Klatt parametrisation: a pole pair at radius r = exp(-pi*bw/fs)
    and angle 2*pi*f/fs, with the numerator chosen for unit gain at DC so that
    cascading resonators does not compound a gain.
    """
    r = np.exp(-np.pi * bw / sample_rate)
    theta = 2.0 * np.pi * f / sample_rate
    a = [1.0, -2.0 * r * np.cos(theta), r * r]
    return [sum(a)], a


def _glottal_source(n, f0_track, sample_rate, rng):
    """Impulse train at the instantaneous frequency `f0_track`, one sample per
    period, with the period jittered by 1 per cent.

    Placed on the sample grid rather than interpolated: the reference contour
    returned with the utterance is the *commanded* f0_track, so a fractional
    period error appears as reference noise, which is honest — a real pitch
    tracker has more than 1 per cent — and keeps T2 from being exactly solvable.
    """
    src = np.zeros(n)
    i = 0
    while i < n:
        src[i] = 1.0
        period = sample_rate / f0_track[min(i, n - 1)]
        period *= 1.0 + 0.01 * rng.standard_normal()
        i += max(1, int(round(period)))
    return src


def _ramp(x, n_ramp):
    """Raised-cosine onset and offset, so concatenated phones do not click.

    A click is broadband and instantaneous, which is precisely what T3 detects;
    without ramping, boundary detection would be trivially solvable from an
    artefact of the synthesiser rather than from the spectral change.
    """
    if len(x) < 2 * n_ramp or n_ramp < 1:
        return x
    w = 0.5 * (1.0 - np.cos(np.pi * np.arange(n_ramp) / n_ramp))
    x = x.copy()
    x[:n_ramp] *= w
    x[-n_ramp:] *= w[::-1]
    return x


def synthetic_corpus(n_speakers=12, utterances_per_speaker=4,
                     phones_per_utterance=8, sample_rate=16000, seed=0,
                     noise_level=0.005, f0_hop=0.010):
    """A source-filter corpus with known phone labels, boundaries and f0.

    Each speaker has a vocal tract length factor scaling every formant and a
    mean f0; these are the two things proposal 2.3 says the source-filter model
    separates, and separating them here is what lets T1 (filter) and T2
    (source) be genuinely different tasks on the stand-in as they are on real
    speech. Splits are speaker-disjoint (C4), so a probe that has memorised a
    speaker's formant scaling is measured on speakers it has never seen.

    The task is deliberately neither trivial nor impossible: phones differ by
    formant pattern, but the vocal tract factor spans 0.85 to 1.15, which moves
    a formant far enough that the vowel classes overlap across speakers.
    """
    rng = np.random.default_rng(seed)
    fs = int(sample_rate)
    n_ramp = int(0.005 * fs)
    utterances = []

    for s in range(n_speakers):
        spk = f"S{s:02d}"
        vtl = float(rng.uniform(0.85, 1.15))       # vocal tract length factor
        f0_mean = float(rng.uniform(90.0, 220.0))

        for u in range(utterances_per_speaker):
            audio, segments = [], []
            t = 0.0
            # Declination: f0 falls across the utterance, as it does in speech.
            decl = float(rng.uniform(0.75, 0.95))

            prev = None
            for p in range(phones_per_utterance):
                # Never twice in succession: a boundary between two instances
                # of the same phone is a boundary in the label sequence and not
                # in the audio, and T3 would be scored against a ground truth
                # containing events that are not there to be detected.
                phone = PHONES[rng.integers(len(PHONES))]
                while phone == prev:
                    phone = PHONES[rng.integers(len(PHONES))]
                prev = phone
                dur = float(rng.uniform(0.06, 0.14))
                n = int(round(dur * fs))
                frac0 = p / max(1, phones_per_utterance - 1)
                frac1 = (p + 1) / max(1, phones_per_utterance - 1)

                if phone in _VOWELS:
                    f0_hi = f0_mean * (1.0 - (1.0 - decl) * frac0)
                    f0_lo = f0_mean * (1.0 - (1.0 - decl) * frac1)
                    track = np.linspace(f0_hi, f0_lo, n)
                    x = _glottal_source(n, track, fs, rng)
                    # -12 dB/octave source spectrum, one pole at 100 Hz.
                    x = lfilter(*_resonator(0.0, 200.0, fs), x)
                    for f in _VOWELS[phone]:
                        bw = max(50.0, 0.06 * f * vtl)
                        x = lfilter(*_resonator(f * vtl, bw, fs), x)
                    seg_f0, seg_voiced = track, np.ones(n, dtype=bool)
                else:
                    lo, hi = _FRICATIVES[phone]
                    hi = min(hi, 0.99 * 0.5 * fs)
                    sos = butter(4, [lo / (0.5 * fs), hi / (0.5 * fs)],
                                 btype="band", output="sos")
                    x = sosfilt(sos, rng.standard_normal(n))
                    seg_f0 = np.zeros(n)
                    seg_voiced = np.zeros(n, dtype=bool)

                peak = np.max(np.abs(x))
                if peak > 0:
                    x = x / peak
                # Per-phone gain: real speech is not loudness-flat, and a
                # constant-gain corpus would let a probe read phone identity
                # off total energy alone.
                x = _ramp(x, n_ramp) * float(rng.uniform(0.5, 1.0))

                audio.append(x)
                segments.append(Segment(t, t + n / fs, phone))
                if p == 0:
                    f0_samples, voiced_samples = [seg_f0], [seg_voiced]
                else:
                    f0_samples.append(seg_f0)
                    voiced_samples.append(seg_voiced)
                t += n / fs

            x = np.concatenate(audio)
            x = x + noise_level * rng.standard_normal(len(x))
            peak = np.max(np.abs(x))
            if peak > 0:
                x = x / peak

            # Reference contour, resampled from the per-sample commanded track
            # onto the f0_hop grid the T2 probe will be scored on.
            f0_full = np.concatenate(f0_samples)
            v_full = np.concatenate(voiced_samples)
            n_f0 = int(np.floor((len(x) / fs) / f0_hop)) + 1
            idx = np.minimum((np.arange(n_f0) * f0_hop * fs).astype(int),
                             len(f0_full) - 1)

            utterances.append(Utterance(
                uid=f"{spk}_U{u:02d}", speaker=spk, audio=x, sample_rate=fs,
                segments=tuple(segments), f0=f0_full[idx],
                voiced=v_full[idx], f0_hop=f0_hop))

    return Corpus(name=f"synthetic(seed={seed})", utterances=tuple(utterances),
                  labels=PHONES)


# --- TIMIT ------------------------------------------------------------------

# The two dialect sentences every one of the 630 speakers reads. They are
# conventionally excluded, because with the same text in every speaker's set
# they are shared between any train/test partition in content if not in
# recording, and a probe can learn the sentence rather than the phone.
SA_SENTENCES = ("SA1", "SA2")

# The 61-to-39 collapse of proposal 4.1 — "following near-universal convention
# on TIMIT, the 61-symbol label set is collapsed to 39 for scoring, and this
# must be stated whenever a figure is quoted".
#
# PROVISIONAL. This is the mapping attributed to Lee and Hon (1989) and used by
# the HTK and Kaldi TIMIT recipes, written out from that convention. It has not
# been checked against the paper, which is not on this machine, and a folding
# table is exactly the kind of thing that is quoted from memory and is wrong in
# one row. Q39 asks the design session to confirm it against the source before
# any 39-symbol figure is reported. Symbols not listed map to themselves.
TIMIT_61_TO_39 = {
    "ao": "aa",
    "ax": "ah", "ax-h": "ah",
    "axr": "er",
    "hv": "hh",
    "ix": "ih",
    "el": "l",
    "em": "m",
    "en": "n", "nx": "n",
    "eng": "ng",
    "zh": "sh",
    "ux": "uw",
    # Every closure, pause and non-speech symbol becomes one silence class.
    "pcl": "sil", "tcl": "sil", "kcl": "sil", "bcl": "sil", "dcl": "sil",
    "gcl": "sil", "h#": "sil", "pau": "sil", "epi": "sil",
    # The glottal stop is deleted rather than mapped, which is the convention
    # and which leaves a labelled gap rather than inventing a label for it.
    "q": None,
}

TIMIT_39 = ("aa", "ae", "ah", "aw", "ay", "b", "ch", "d", "dh", "dx", "eh",
            "er", "ey", "f", "g", "hh", "ih", "iy", "jh", "k", "l", "m", "n",
            "ng", "ow", "oy", "p", "r", "s", "sh", "sil", "t", "th", "uh",
            "uw", "v", "w", "y", "z")


def read_phn(path, sample_rate):
    """TIMIT's hand-placed phone alignment: `start_sample end_sample label`.

    Indices are sample offsets into the companion audio file, so the sample
    rate has to come from that file rather than be assumed — a `.PHN` read at
    the wrong rate produces segments that look entirely plausible and are all
    in the wrong place, which is the failure mode C5 exists to catch and would
    catch far too late.
    """
    segments = []
    with open(path, encoding="ascii") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) != 3:
                continue
            start, end, label = parts
            segments.append(Segment(int(start) / sample_rate,
                                    int(end) / sample_rate, label))
    return tuple(segments)


def fold_to_39(corpus):
    """Collapse a 61-symbol TIMIT corpus to the 39-symbol scoring set.

    Adjacent segments folding to the same symbol are merged, which is not a
    tidying step but the substance of the collapse: `pcl` followed by `p`
    becomes `sil` followed by `p`, while `pcl` followed by `bcl` becomes one
    `sil`, and leaving them separate would put a boundary where the 39-symbol
    transcription has none. Segments whose label folds to `None` — the glottal
    stop — are dropped, leaving a gap that `label_at` reports as unlabelled.

    **Use this for T1 and not for T3.** T3's ground truth is the hand-placed
    boundary set, and folding deletes some of those boundaries by construction.
    """
    out = []
    for u in corpus:
        merged = []
        for seg in u.segments:
            label = TIMIT_61_TO_39.get(seg.label, seg.label)
            if label is None:
                continue
            if (merged and merged[-1].label == label
                    and merged[-1].end == seg.start):
                merged[-1] = Segment(merged[-1].start, seg.end, label)
            else:
                merged.append(Segment(seg.start, seg.end, label))
        out.append(dataclasses.replace(u, segments=tuple(merged)))
    labels = tuple(sorted({s.label for u in out for s in u.segments}))
    return dataclasses.replace(corpus, name=f"{corpus.name}+39",
                               utterances=tuple(out), labels=labels)


def timit_corpus(root, subset="TRAIN", exclude_sa=True, speakers=None,
                 max_utterances=None, f0_fn=None, f0_hop=0.010):
    """TIMIT as a `Corpus` — the same three attributes as the stand-in.

    `root` is the directory containing `TRAIN` and `TEST`. Case is not assumed:
    distributions differ on whether paths and extensions are upper or lower,
    and matching on the literal `.WAV` would silently find nothing on half of
    them. Files are found by walking, so an extra level of nesting — some
    copies wrap everything in a `TIMIT/` or `data/` directory — does not
    matter as long as `root` contains the split directory somewhere below it.

    `subset` selects `TRAIN` or `TEST`, or `None` for both. **This is not the
    train/test split of the study.** C4 splits on speaker with
    `speaker_disjoint_split`, from whichever utterances are loaded; TIMIT's own
    partition is a different one, made for a different purpose, and using it
    here would silently replace the control.

    `f0_fn(utterance_audio, sample_rate, hop) -> (f0, voiced)` supplies T2's
    reference contour, which TIMIT does not carry. With `f0_fn=None` the
    utterances have no `f0` and T2 raises a named error rather than running on
    something invented; proposal 4.2 requires two trackers and their measured
    disagreement, and neither exists yet (Q40).

    Labels are the 61-symbol set as read. `fold_to_39` collapses them for T1
    scoring; see its docstring for why T3 must not use it.
    """
    root = pathlib.Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"TIMIT root {root} is not a directory")
    wanted = None if subset is None else str(subset).upper()

    found = []
    for path in root.rglob("*"):
        if path.suffix.upper() != ".PHN" or not path.is_file():
            continue
        parts = [p.upper() for p in path.parts]
        if wanted is not None and wanted not in parts:
            continue
        stem = path.stem.upper()
        if exclude_sa and stem in SA_SENTENCES:
            continue
        speaker = path.parent.name.upper()
        if speakers is not None and speaker not in {s.upper()
                                                    for s in speakers}:
            continue
        found.append((speaker, stem, path))
    found.sort()
    if not found:
        raise FileNotFoundError(
            f"no .PHN files under {root}"
            + (f" for subset {wanted}" if wanted else "")
            + ". Expected the TIMIT layout, e.g. TRAIN/DR1/FCJF0/SA1.PHN.")
    if max_utterances is not None:
        found = found[:max_utterances]

    utterances = []
    for speaker, stem, phn in found:
        audio_path = None
        for candidate in (phn.with_suffix(".WAV"), phn.with_suffix(".wav")):
            if candidate.exists():
                audio_path = candidate
                break
        if audio_path is None:
            raise FileNotFoundError(f"{phn} has no companion .WAV")

        audio, rate = read_audio(audio_path)
        if audio.ndim > 1:
            raise ValueError(
                f"{audio_path} has {audio.shape[0]} channels; TIMIT is mono, "
                "so this is not the corpus that was expected")
        segments = read_phn(phn, rate)
        # The last segment's end is the file length in TIMIT. Clip rather than
        # trust it: a segment running past the audio would put labels on frames
        # that do not exist, and `frame_labels` would not notice.
        duration = len(audio) / rate
        segments = tuple(Segment(s.start, min(s.end, duration), s.label)
                         for s in segments if s.start < duration)

        f0 = voiced = None
        if f0_fn is not None:
            f0, voiced = f0_fn(audio, rate, f0_hop)
        utterances.append(Utterance(
            uid=f"{speaker}_{stem}", speaker=speaker, audio=audio,
            sample_rate=rate, segments=segments, f0=f0, voiced=voiced,
            f0_hop=f0_hop))

    labels = tuple(sorted({s.label for u in utterances for s in u.segments}))
    name = f"TIMIT({wanted or 'all'}, {len(utterances)} utterances)"
    return Corpus(name=name, utterances=tuple(utterances), labels=labels)
