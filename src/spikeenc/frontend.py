"""Front end — SPEC.md section 3, proposal equations (4)-(10).

A gammatone filterbank, its envelope extraction and its compressive
nonlinearity. Shared by every encoder except E7, so that differences between
candidates are attributable to the event generation rule rather than to
incidental differences in filtering (proposal section 5.0).

Implemented as FIR: each channel's impulse response is equation (4) sampled and
truncated, and `subbands` is a convolution. SPEC section 8 leaves FIR against
IIR free; FIR is chosen because the taps *are* equation (4), so what F1 and F2
check is the thing the filterbank actually uses, with no cascade-of-biquads
approximation in between.

Author:        Simon Davidson & Claude
Created:       2026-09-02
Last modified: 2026-09-02
"""
import numpy as np
from scipy.signal import butter, fftconvolve, hilbert, lfilter

# Tail of the gammatone envelope retained in the FIR taps, as a multiple of the
# envelope peak time (order-1)/(2*pi*b). At 8 the residual amplitude is ~4e-7 of
# the peak, which is below float32 noise and far below anything the study
# measures.
_TAIL_FACTOR = 8.0


def erb(f):
    """Equivalent rectangular bandwidth, Glasberg and Moore, equation (5).

        ERB(f) = 24.7 * (0.00437 * f + 1)
    """
    return 24.7 * (0.00437 * np.asarray(f, dtype=np.float64) + 1.0)


def erb_rate(f):
    """ERB-rate scale, equation (6).

        E(f) = 21.4 * log10(0.00437 * f + 1)
    """
    return 21.4 * np.log10(0.00437 * np.asarray(f, dtype=np.float64) + 1.0)


def erb_rate_inverse(e):
    """Inverse of `erb_rate`, for placing centre frequencies."""
    return (10.0 ** (np.asarray(e, dtype=np.float64) / 21.4) - 1.0) / 0.00437


def hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f, dtype=np.float64) / 700.0)


def mel_to_hz(m):
    return 700.0 * (10.0 ** (np.asarray(m, dtype=np.float64) / 2595.0) - 1.0)


class Filterbank:
    """Gammatone filterbank. SPEC section 3.

    Channel 0 is always the lowest centre frequency (SPEC section 1).
    """

    def __init__(self, n_channels, f_min=50.0, f_max=8000.0, sample_rate=16000,
                 spacing="erb", order=4, compensate_group_delay=False):
        self.n_channels = int(n_channels)
        self.f_min = float(f_min)
        self.f_max = float(f_max)
        self.sample_rate = int(sample_rate)
        self.spacing = spacing
        self.order = int(order)
        self.compensate_group_delay = bool(compensate_group_delay)
        self._taps = None                      # lazily built, then cached

    # -- geometry ----------------------------------------------------------

    @property
    def centre_frequencies(self):
        """Ascending centre frequencies, endpoints hit exactly. Equation (6)
        for `spacing="erb"`."""
        n = self.n_channels
        if n == 1:
            return np.array([self.f_min], dtype=np.float64)
        if self.spacing == "erb":
            scale = erb_rate(np.array([self.f_min, self.f_max]))
            return erb_rate_inverse(np.linspace(scale[0], scale[1], n))
        if self.spacing == "mel":
            scale = hz_to_mel(np.array([self.f_min, self.f_max]))
            return mel_to_hz(np.linspace(scale[0], scale[1], n))
        if self.spacing == "linear":
            return np.linspace(self.f_min, self.f_max, n, dtype=np.float64)
        raise ValueError(f"unknown spacing {self.spacing!r}; "
                         "expected 'erb', 'mel' or 'linear'")

    @property
    def bandwidths(self):
        """The b_c of equation (4): b_c = 1.019 * ERB(f_c)."""
        return 1.019 * erb(self.centre_frequencies)

    @property
    def group_delays(self):
        """Envelope peak delay of each channel, (order - 1) / (2*pi*b_c).

        This is the frequency-dependent timing bias discussed in SPEC section
        3: low-frequency channels respond later than high-frequency ones to the
        same acoustic event.
        """
        return (self.order - 1) / (2.0 * np.pi * self.bandwidths)

    # -- impulse responses -------------------------------------------------

    def impulse_response(self, channel, n_samples):
        """Equation (4), sampled at the filterbank sample rate:

            g_c(t) = a * t^(n-1) * exp(-2*pi*b_c*t) * cos(2*pi*f_c*t + phi_c)

        with phi_c = 0. The gain `a` normalises the response to unit magnitude
        at f_c, so that summed subband energy stays comparable with input
        energy (test F5) instead of scaling with an arbitrary constant.
        """
        fc = float(self.centre_frequencies[channel])
        b = float(self.bandwidths[channel])
        t = np.arange(int(n_samples), dtype=np.float64) / self.sample_rate
        h = t ** (self.order - 1) * np.exp(-2.0 * np.pi * b * t) * np.cos(
            2.0 * np.pi * fc * t)
        # Magnitude of the DTFT at f_c, evaluated directly rather than via an
        # FFT bin so the normalisation does not depend on n_samples.
        gain = np.abs(np.sum(h * np.exp(-2j * np.pi * fc * t)))
        if gain > 0.0:
            h = h / gain
        return h

    def _filter_taps(self):
        """FIR taps per channel, truncated where the envelope has decayed."""
        if self._taps is None:
            self._taps = [
                self.impulse_response(c, self._n_taps(c))
                for c in range(self.n_channels)
            ]
        return self._taps

    def _n_taps(self, channel):
        peak = (self.order - 1) / (2.0 * np.pi * float(self.bandwidths[channel]))
        return max(8, int(np.ceil(_TAIL_FACTOR * peak * self.sample_rate)))

    # -- analysis ----------------------------------------------------------

    def subbands(self, audio):
        """Equation (7): x_c = g_c * x, shape (n_channels, n_samples).

        Causal convolution truncated to the input length, so each channel
        carries its own group delay. With `compensate_group_delay=True` each
        channel is advanced by its own delay, aligning onsets across the bank
        (SPEC section 3).
        """
        x = np.asarray(audio, dtype=np.float64).ravel()
        n = x.size
        out = np.empty((self.n_channels, n), dtype=np.float64)
        for c, h in enumerate(self._filter_taps()):
            out[c] = fftconvolve(x, h)[:n]

        if self.compensate_group_delay:
            shifts = np.round(self.group_delays * self.sample_rate).astype(int)
            for c, s in enumerate(shifts):
                if s > 0:
                    out[c] = np.concatenate([out[c, s:], np.zeros(min(s, n))])[:n]
        return out

    def envelope(self, audio, method="hilbert", f_cut=300.0, lowpass_order=4):
        """Subband envelopes, equation (8) or (9).

        "hilbert"          : |x_c + j H{x_c}|, the analytic signal magnitude.
        "rectify_lowpass"  : LPF_fcut(max(x_c, 0)), the cheaper route and the
                             more plausible model of hair cell transduction.

        `f_cut` and `lowpass_order` are not part of the SPEC section 3
        signature and are ignored by the "hilbert" branch. They are exposed so
        that the cutoff of equation (9) is a declared value rather than a
        buried constant.

        Caveat on the "rectify_lowpass" branch, which no known-answer test
        covers (F4 exercises "hilbert" only). Equation (9) specifies a single
        cutoff for the whole bank, so channels whose centre frequency is not
        well above `f_cut` retain carrier in their "envelope": measured against
        a known 5 Hz modulator at these defaults the correlation is 0.996 at
        3057 Hz and 0.980 at 953 Hz, but 0.25 at 196 Hz. That is inherent to a
        fixed cutoff, not a bug, and it is why "hilbert" is the SPEC default. A
        channel-relative cutoff would fix it but departs from equation (9), so
        it is raised as Q03 rather than adopted here.
        """
        sub = self.subbands(audio)
        if method == "hilbert":
            return np.abs(hilbert(sub, axis=-1))
        if method == "rectify_lowpass":
            nyquist = 0.5 * self.sample_rate
            b, a = butter(lowpass_order, min(f_cut / nyquist, 0.99), btype="low")
            return lfilter(b, a, np.maximum(sub, 0.0), axis=-1)
        raise ValueError(f"unknown envelope method {method!r}; "
                         "expected 'hilbert' or 'rectify_lowpass'")

    def compress(self, env, method="log", epsilon=1e-8, exponent=0.3):
        """Compressive nonlinearity, equation (10). SPEC section 3.

        "log"   : log(e_c + epsilon)   -- `epsilon` prevents the singularity
                  in silence and applies to this branch only.
        "power" : e_c ** exponent      -- `exponent` applies to this branch only.
        "none"  : returned unchanged, for E5, whose drive is the subband
                  waveform rather than a compressed envelope.
        """
        e = np.asarray(env, dtype=np.float64)
        if method == "none":
            return e
        if method == "log":
            return np.log(e + epsilon)
        if method == "power":
            # Envelopes are non-negative by construction; clipping keeps a
            # fractional exponent from producing NaN if that is ever violated.
            return np.power(np.clip(e, 0.0, None), exponent)
        raise ValueError(f"unknown compression method {method!r}; "
                         "expected 'log', 'power' or 'none'")
