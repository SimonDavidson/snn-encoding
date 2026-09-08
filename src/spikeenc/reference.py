"""Reference points — R2, the non-spiking upper bound of proposal 5.9.

R2 is not a candidate encoder and produces no events. It is forty mel-scale
filterbank features over 25 ms windows at 10 ms hop, fed to the same decoder as
every spiking condition, and proposal 5.9 calls it "the essential control":
without it a phone accuracy figure means nothing, because a reader cannot tell
whether a shortfall reflects the encoding, the decoder, the corpus or the task.
With it, the study's central question has a number — what accuracy is given up,
and what is saved, by representing the audio as events.

**Where the analysis window sits is a decision and is made here explicitly.**
Section 5.9 fixes forty bands, 25 ms and 10 ms and says nothing about the phase
of the window relative to the frame instant `t = k*hop` at which SPEC section 5
says frame k is sampled, and at which `tasks.frame_labels` reads its label.
That gap is not cosmetic. Q24 measured the cost of a one-frame misalignment on
this corpus at between 4.5 and 18.5 accuracy points, which is larger than any
difference this study expects to resolve between encoders.

Two conventions are therefore implemented and the choice is declared with the
result:

- `"causal"` (default) — the window *ends* at `t = k*hop`, so frame k
  summarises only audio at or before that instant. This is what equation (32)
  does for the spiking conditions, whose exponential kernel is strictly causal,
  so R2 and every encoder see the same span of history at frame k. It is the
  only setting under which the R2 gap is attributable to the encoding.
- `"centred"` — the window is centred on `t = k*hop`, the convention under
  which a spectral estimate is usually attributed to its window centre. It
  lets R2 see 12.5 ms of audio that no spiking condition can see, so a gap
  measured against it is part encoding and part clairvoyance.

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-08
"""
import numpy as np

from .frontend import hz_to_mel, mel_to_hz

#: Floor inside the logarithm, preventing a singularity on a silent frame. The
#: same role as `epsilon` in equation (10); named separately because this is
#: not equation (10) and should not be read as it.
LOG_FLOOR = 1e-10


def mel_filters(n_mels, n_fft, sample_rate, f_min=50.0, f_max=8000.0):
    """Triangular mel-spaced filters, `(n_mels, n_fft // 2 + 1)`.

    `n_mels + 2` points are placed uniformly on the mel scale between `f_min`
    and `f_max`; filter m rises from point m to point m+1 and falls to point
    m+2, so adjacent filters overlap at half amplitude and the bank tiles the
    range. `hz_to_mel` and `mel_to_hz` are imported from the front end rather
    than restated, so the study has one mel scale and not two.
    """
    if n_mels < 1:
        raise ValueError(f"n_mels must be at least 1, got {n_mels}")
    f_max = min(f_max, 0.5 * sample_rate)
    points = mel_to_hz(np.linspace(hz_to_mel(f_min), hz_to_mel(f_max),
                                   n_mels + 2))
    bins = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
    filters = np.zeros((n_mels, len(bins)))
    for m in range(n_mels):
        lo, mid, hi = points[m], points[m + 1], points[m + 2]
        rising = (bins >= lo) & (bins <= mid)
        falling = (bins > mid) & (bins <= hi)
        if mid > lo:
            filters[m, rising] = (bins[rising] - lo) / (mid - lo)
        if hi > mid:
            filters[m, falling] = (hi - bins[falling]) / (hi - mid)
    return filters


def frame_signal(audio, sample_rate, n_frames, frame=0.025, hop=0.010,
                 alignment="causal"):
    """Cut `audio` into `n_frames` windows on the SPEC section 5 frame grid.

    Frame k is positioned so that it corresponds to the instant `t = k*hop`
    under the chosen `alignment`, and is zero-padded where it runs off either
    end of the signal. Returns `(n_frames, n_samples_per_frame)`.
    """
    n_frame = int(round(frame * sample_rate))
    n_hop = int(round(hop * sample_rate))
    if n_frame < 1:
        raise ValueError(f"frame of {frame} s is under one sample")

    centres = np.arange(n_frames) * n_hop
    if alignment == "causal":
        # The window ends on, and includes, the sample at t = k*hop.
        starts = centres + 1 - n_frame
    elif alignment == "centred":
        starts = centres - n_frame // 2
    else:
        raise ValueError(f"unknown alignment {alignment!r}; expected "
                         "'causal' or 'centred'")

    out = np.zeros((n_frames, n_frame), dtype=np.float64)
    n = len(audio)
    for k, s in enumerate(starts):
        lo, hi = max(0, s), min(n, s + n_frame)
        if hi > lo:
            out[k, lo - s:hi - s] = audio[lo:hi]
    return out


def mel_alignment_prediction(frame=0.025, hop=0.010, alignment="causal",
                             window="hamming"):
    """The label alignment offset R2's analysis window predicts (D69).

    R2 has a declared lag of its own, and it is not the front end's: the
    causal window of D52 ends at the frame instant, so its energy is centred
    half a window earlier and a frame at `t` describes speech around
    `t - frame/2`. A centred window has no such lag. The symmetric taper does
    not move the centroid, so the window shape does not enter.

    Reported beside R2's selected offset for the same reason the gammatone
    prediction is reported beside a spiking one: it makes the sweep a check on
    a quantity computed without fitting anything, rather than a free parameter.
    """
    lag = 0.5 * float(frame) if alignment == "causal" else 0.0
    return {"analysis_window_lag_s": lag, "alignment": alignment,
            "window": window, "hop": hop,
            "by_tau": {"0": {"lag_s": lag,
                             "offset": int(-np.round(lag / float(hop)))}},
            "offset": int(-np.round(lag / float(hop)))}


def mel_features(utterance, n_mels=40, frame=0.025, hop=0.010,
                 alignment="causal", f_min=50.0, f_max=8000.0,
                 window="hamming", n_frames=None):
    """R2's features: log mel filterbank energies, `(n_frames, n_mels)`.

    Forty bands, 25 ms, 10 ms hop — proposal 5.9, the front end of Wu and
    colleagues and of Bittar and Garner, so figures are comparable to the
    published literature as well as internally.

    No normalisation is applied. The probe standardises from training
    statistics, exactly as it does for the spiking conditions, and adding a
    step here would break the C4 requirement that decoding be identical.
    """
    fs = utterance.sample_rate
    if n_frames is None:
        n_frames = int(np.floor(utterance.duration / hop)) + 1

    frames = frame_signal(utterance.audio, fs, n_frames, frame=frame, hop=hop,
                          alignment=alignment)
    n_frame = frames.shape[1]
    if window == "hamming":
        frames = frames * np.hamming(n_frame)
    elif window == "hann":
        frames = frames * np.hanning(n_frame)
    elif window != "none":
        raise ValueError(f"unknown window {window!r}; expected 'hamming', "
                         "'hann' or 'none'")

    n_fft = int(2 ** np.ceil(np.log2(n_frame)))
    power = np.abs(np.fft.rfft(frames, n=n_fft, axis=1)) ** 2
    bank = mel_filters(n_mels, n_fft, fs, f_min=f_min, f_max=f_max)
    return np.log(power @ bank.T + LOG_FLOOR)


def feature_bandwidth_bps(n_mels, hop, bits_per_feature=32):
    """What R2 costs to transmit, for comparison with equation (36).

    Not an equation from the proposal. R2 emits a dense frame of `n_mels`
    numbers every `hop` seconds whether or not anything happened, which is the
    quantity an event rate is being compared against when 6.3 argues the
    event-based case. Reported with its `bits_per_feature` because a bandwidth
    without its declared width is not a figure (D45).
    """
    return n_mels * bits_per_feature / hop
