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
plausible. When TIMIT arrives, `TimitCorpus` implements the same three
attributes and nothing downstream changes.

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-07
"""
from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter, butter, sosfilt


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
