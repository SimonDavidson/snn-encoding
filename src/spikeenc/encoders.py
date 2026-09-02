"""Encoders — the API surface of SPEC.md section 4.

STATUS: E1 and E2 implemented. E3-E6 remain skeletons.

Class attributes (NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND) and the
__init__ signatures are part of the contract — the known-answer suite reads
them. Do not change the signatures without raising it in QUESTIONS.md first.

Equation numbers refer to docs/proposal_v2.md.

Author:        Simon Davidson & Claude
Created:       2026-09-02
Last modified: 2026-09-02
"""
import numpy as np
from .spiketrain import SpikeTrain

# A last-spike index far enough in the past that no channel starts refractory.
_NEVER = -(1 << 40)

# Tolerance, in lattice units, on the ">= C" comparison of equations (14)-(15).
#
# A drive value landing exactly on a lattice point is measure-zero in theory and
# routine in practice: test signals with round amplitudes, quantised audio, and
# any drive whose extremes are an exact multiple of C all hit it. There the
# comparison is decided by double-rounding noise rather than by the equation --
# u = 1.0 against r = 0.9 with C = 0.1 evaluates u - r as 0.09999999999999998,
# so ">= C" is False and the crest event of the excursion is dropped, costing
# two events per half cycle because the return journey then starts one step in.
#
# 1e-9 is ~7 orders above double rounding noise and ~9 below anything the study
# measures. It can only cause an event to fire marginally early, never late, so
# the equation (16) bound is tightened by it and never loosened.
_LATTICE_TOL = 1e-9


class Encoder:
    NAME: str = "?"
    RATE_PARAM: str = "?"
    RATE_DIRECTION: int = -1
    DRIVE_KIND: str = "envelope"

    #: Optional Filterbank used by `encode`. Left None, `encode` builds one
    #: with SPEC section 3 defaults at the audio's sample rate. Set it to sweep
    #: front-end parameters, which are deliberately not encoder constructor
    #: arguments.
    filterbank = None

    def encode(self, audio, sample_rate, seed=None):
        """Front end composed with encode_from_drive, nothing more.
        SPEC section 4.1."""
        from .frontend import Filterbank

        fb = self.filterbank
        if fb is None:
            fb = Filterbank(self.n_channels, sample_rate=sample_rate)
        if self.DRIVE_KIND == "subband":
            drive = fb.subbands(audio)
        else:
            drive = fb.compress(fb.envelope(audio))
        return self.encode_from_drive(drive, 1.0 / sample_rate, seed=seed)

    def encode_from_drive(self, drive, dt, seed=None, return_state=False):
        raise NotImplementedError(f"{self.NAME}.encode_from_drive")

    # -- helpers shared by every encoder -----------------------------------

    def _check_drive(self, drive):
        """Validate shape and return a float64 view. SPEC section 4.1 forbids
        any filtering, compression, scaling or normalisation here, so this
        does nothing but check and cast."""
        d = np.asarray(drive, dtype=np.float64)
        if d.ndim != 2:
            raise ValueError(f"drive must be 2-D (n_channels, n_samples), "
                             f"got shape {d.shape}")
        if d.shape[0] != self.n_channels:
            raise ValueError(f"drive has {d.shape[0]} channels, "
                             f"encoder declares {self.n_channels}")
        return d

    def _params(self, **extra):
        """Provenance record for the SpikeTrain, SPEC section 2: encoder name
        plus every constructor parameter."""
        p = {"encoder": self.NAME}
        p.update({k: v for k, v in vars(self).items()
                  if not k.startswith("_") and k != "filterbank"})
        p.update(extra)
        return p


def _integrate_and_fire(drive, dt, theta, tau_m, gain, refractory,
                        want_state=False):
    """Discrete leaky integrate-and-fire, equations (12)-(13).

        V[n] = beta * V[n-1] * (1 - s[n-1]) + (1 - beta) * g * u[n]
        s[n] = Theta(V[n] - theta)

    with beta = exp(-dt / tau_m) and a hard reset to zero: the (1 - s[n-1])
    factor zeroes the carried-over potential on the step after an event.

    Refractory semantics are SPEC section 4.2 / D17: during an absolute
    refractory period the potential is clamped to the reset value and incoming
    drive is discarded, so the interspike interval under saturating drive is
    exactly `refractory` and the rate ceiling exactly 1/refractory.

    Returns (channel_idx, sample_idx, v_trace_or_None), with events in sample
    order and channel order within a sample.
    """
    n_ch, n = drive.shape
    beta = np.exp(-dt / tau_m)

    v = np.zeros(n_ch, dtype=np.float64)
    fired = np.zeros(n_ch, dtype=bool)
    last = np.full(n_ch, _NEVER, dtype=np.int64)
    trace = np.zeros((n_ch, n), dtype=np.float64) if want_state else None

    chan_out, samp_out = [], []
    for i in range(n):
        # Hard reset: potential carried over is zeroed for channels that fired
        # on the previous step.
        v = beta * v * ~fired + (1.0 - beta) * gain * drive[:, i]

        if refractory > 0.0:
            blocked = (i - last) * dt < refractory
            v = np.where(blocked, 0.0, v)
            fired = (v >= theta) & ~blocked
        else:
            fired = v >= theta

        if trace is not None:
            trace[:, i] = v

        if fired.any():
            idx = np.flatnonzero(fired)
            chan_out.append(idx)
            samp_out.append(np.full(idx.size, i, dtype=np.int64))
            last[idx] = i

    if chan_out:
        return (np.concatenate(chan_out), np.concatenate(samp_out), trace)
    return (np.empty(0, np.int64), np.empty(0, np.int64), trace)


class LIF(Encoder):
    """E1 — leaky integrate-and-fire. Equations (11)-(13).

    The rate-like anchor: for constant input the firing rate is roughly
    proportional to input amplitude above threshold, so information sits mainly
    in how many events a channel produces and only weakly in when.

    Unipolar — every event carries polarity +1, so no polarity bit is needed.
    """
    NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND = "E1", "theta", -1, "envelope"

    def __init__(self, n_channels, theta=1.0, tau_m=0.02, gain=1.0,
                 refractory=0.0, reset="hard"):
        self.n_channels, self.theta, self.tau_m = n_channels, theta, tau_m
        self.gain, self.refractory, self.reset = gain, refractory, reset

    def encode_from_drive(self, drive, dt, seed=None, return_state=False):
        """Equations (12)-(13), hard reset to zero. Deterministic: `seed` is
        accepted for interface uniformity and unused.

        Under constant drive u the interspike interval is the closed form of
        protocol equation (V1), T = tau_m * ln(V_inf / (V_inf - theta)) with
        V_inf = gain * u, which is what test_T1_1 asserts.
        """
        if self.reset != "hard":
            raise NotImplementedError(
                f"reset={self.reset!r}; only 'hard' is implemented. The soft "
                "reset of proposal section 5.1 is not yet a study variable.")

        d = self._check_drive(drive)
        n = d.shape[1]
        chan, samp, trace = _integrate_and_fire(
            d, dt, self.theta, self.tau_m, self.gain, self.refractory,
            want_state=return_state)

        train = SpikeTrain.from_events(
            channel=chan,
            time=samp * dt,
            polarity=np.ones(chan.size, dtype=np.int8),
            n_channels=self.n_channels,
            duration=n * dt,
            params=self._params(dt=dt),
        )
        if return_state:
            return train, {"v": trace}
        return train


class SendOnDelta(Encoder):
    """E2 — send-on-delta. Equations (14)-(17).

    Note the requirement in SPEC section 4.3: at each sample, emit events until
    |drive - reference| < C. The reconstruction bound of equation (16) depends
    on it, and test_T2_1 checks the bound directly.
    """
    NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND = "E2", "C", -1, "envelope"

    def __init__(self, n_channels, C=0.1, refractory=0.0,
                 reference_update="lattice"):
        self.n_channels, self.C = n_channels, C
        self.refractory, self.reference_update = refractory, reference_update

    def encode_from_drive(self, drive, dt, seed=None, return_state=False):
        """Equations (14)-(15). Deterministic: `seed` is accepted for interface
        uniformity and unused.

        At each sample the channel emits until |u - r| < C, so a transient
        spanning several thresholds emits several events sharing that
        timestamp. That is what makes equation (16) hold as a theorem rather
        than a tolerance, and test_T2_1 asserts it directly.

        Reference representation follows SPEC section 4.3 and D18: in the
        "lattice" variant the reference is an integer lattice index m with
        r = r0 + m*C, never accumulated by repeated addition, so rounding error
        cannot creep into the bound over a long utterance.

        With refractory > 0 a channel emits at most one event per refractory
        period, and the equation (16) bound degrades accordingly.
        """
        if self.C <= 0.0:
            raise ValueError(f"C must be positive, got {self.C}")
        if self.reference_update not in ("lattice", "exact"):
            raise ValueError(f"unknown reference_update "
                             f"{self.reference_update!r}; "
                             "expected 'lattice' or 'exact'")

        d = self._check_drive(drive)
        n_ch, n = d.shape
        C = float(self.C)
        lattice = self.reference_update == "lattice"

        if n == 0:
            train = SpikeTrain.empty(self.n_channels, 0.0,
                                     self._params(dt=dt))
            return (train, {"reference": np.zeros((n_ch, 0))}) if return_state \
                else train

        r0 = d[:, 0].copy()                      # SPEC 4.3: reference init
        m = np.zeros(n_ch, dtype=np.int64)       # lattice index
        ref = r0.copy()                          # used by the "exact" variant
        last = np.full(n_ch, _NEVER, dtype=np.int64)
        trace = np.zeros((n_ch, n)) if return_state else None

        chan_out, samp_out, pol_out = [], [], []
        for i in range(n):
            # Steps outstanding, in lattice units. For the lattice variant this
            # is measured from r0 rather than from the current reference value:
            # u - (r0 + m*C) subtracts two nearly equal quantities and loses the
            # precision the ">= C" comparison needs, whereas (u - r0)/C - m does
            # not. See _LATTICE_TOL.
            if lattice:
                step = (d[:, i] - r0) / C - m
            else:
                step = (d[:, i] - ref) / C
            # Truncation toward zero is what leaves the residual below C, which
            # is exactly the "emit until within C" rule of SPEC section 4.3.
            k = np.trunc(step + np.sign(step) * _LATTICE_TOL).astype(np.int64)

            if self.refractory > 0.0:
                blocked = (i - last) * dt < self.refractory
                k = np.where(blocked, 0, np.sign(k))

            nz = np.flatnonzero(k)
            if nz.size:
                counts = np.abs(k[nz])
                chan_out.append(np.repeat(nz, counts))
                samp_out.append(np.full(int(counts.sum()), i, dtype=np.int64))
                pol_out.append(np.repeat(np.sign(k[nz]).astype(np.int8), counts))
                last[nz] = i

            if lattice:
                m += k
            else:
                ref = np.where(k != 0, d[:, i], ref)

            if trace is not None:
                trace[:, i] = r0 + m * C if lattice else ref

        if chan_out:
            chan = np.concatenate(chan_out)
            samp = np.concatenate(samp_out)
            pol = np.concatenate(pol_out)
        else:
            chan = np.empty(0, np.int64)
            samp = np.empty(0, np.int64)
            pol = np.empty(0, np.int8)

        train = SpikeTrain.from_events(
            channel=chan,
            time=samp * dt,
            polarity=pol,
            n_channels=self.n_channels,
            duration=n * dt,
            params=self._params(dt=dt),
        )
        if return_state:
            # The running reconstruction r(t) after each sample's events, which
            # is the quantity equation (16) bounds against the drive.
            return train, {"reference": trace}
        return train


class TemporalContrast(Encoder):
    """E3 — temporal contrast. Equations (18)-(21).

    Both filters initialise to drive[:, 0], so constant drive gives no startup
    transient and therefore no events at all (test_T3_1).
    """
    NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND = "E3", "theta", -1, "envelope"

    def __init__(self, n_channels, theta=0.5, tau_fast=0.001, tau_slow=0.05,
                 refractory=0.0):
        self.n_channels, self.theta = n_channels, theta
        self.tau_fast, self.tau_slow, self.refractory = tau_fast, tau_slow, refractory

    def encode_from_drive(self, drive, dt, seed=None, return_state=False):
        raise NotImplementedError("E3: equations (18)-(21); state key 'd'")


class ALIF(Encoder):
    """E4 — adaptive-threshold LIF. Equations (22)-(23).

    With delta_a == 0 this must be bit-identical to LIF at matched parameters
    (test_T4_1). Share the implementation rather than duplicating it.
    """
    NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND = "E4", "theta_0", -1, "envelope"

    def __init__(self, n_channels, theta_0=1.0, delta_a=0.5, tau_a=0.1,
                 tau_m=0.02, gain=1.0, refractory=0.0):
        self.n_channels, self.theta_0, self.delta_a, self.tau_a = (
            n_channels, theta_0, delta_a, tau_a)
        self.tau_m, self.gain, self.refractory = tau_m, gain, refractory

    def encode_from_drive(self, drive, dt, seed=None, return_state=False):
        raise NotImplementedError("E4: equations (22)-(23); state keys 'v','threshold'")


class PhaseLocked(Encoder):
    """E5 — phase-locked fine structure. Equations (24)-(26).

    Consumes the subband waveform, not the envelope.
    """
    NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND = "E5", "threshold", -1, "subband"

    def __init__(self, n_channels, threshold=0.05, gamma=1.0, f_lock=1500.0,
                 refractory=0.001, mode="deterministic", centre_frequencies=None):
        self.n_channels, self.threshold, self.gamma = n_channels, threshold, gamma
        self.f_lock, self.refractory, self.mode = f_lock, refractory, mode
        self.centre_frequencies = centre_frequencies

    def encode_from_drive(self, drive, dt, seed=None, return_state=False):
        raise NotImplementedError("E5: upward zero crossings above threshold")


class TTFS(Encoder):
    """E6 — time to first spike. Equations (27)-(29).

    Frame energy is the sum of squared drive samples in the frame, computed on
    whatever drive is supplied, with no further transformation (SPEC 4.7).
    """
    NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND = "E6", "e_min", -1, "envelope"

    def __init__(self, n_channels, e_min=1e-6, frame=0.025, hop=0.010,
                 tau_m=0.02, theta=1.0, mode="log"):
        self.n_channels, self.e_min = n_channels, e_min
        self.frame, self.hop = frame, hop
        self.tau_m, self.theta, self.mode = tau_m, theta, mode

    def encode_from_drive(self, drive, dt, seed=None, return_state=False):
        raise NotImplementedError("E6: equations (27)-(29)")
