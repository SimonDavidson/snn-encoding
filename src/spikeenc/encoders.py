"""Encoders — the API surface of SPEC.md section 4.

STATUS: E1-E6 implemented.

Class attributes (NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND) and the
__init__ signatures are part of the contract — the known-answer suite reads
them. Do not change the signatures without raising it in QUESTIONS.md first.

Equation numbers refer to docs/proposal_v2.md.

Author:        Simon Davidson & Claude
Created:       2026-09-02
Last modified: 2026-09-10
"""
import numpy as np
from scipy.signal import butter, sosfilt

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

    #: Whether RATE_PARAM takes integer values only. Harness metadata rather
    #: than contract: it says nothing about what an encoder does, only how
    #: `calibrate_rate_param` may search for a value. D50 calibrates by
    #: bisection in log space over a continuous bracket, which for an integer
    #: parameter fails on its first probe — E5 rejects `cycle_divisor = 1e-4`
    #: before any events are counted. Declared here because it is a property
    #: of the encoder and not of the run.
    RATE_PARAM_INTEGER: bool = False

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


def _integrate_and_fire(drive, dt, theta_0, tau_m, gain, refractory,
                        delta_a=0.0, tau_a=1.0, want_state=False):
    """Leaky integrate-and-fire with an adaptive threshold. Equations (12)-(13)
    and (22)-(23).

        a[n]  = rho * a[n-1] + delta_a * s[n-1]         rho  = exp(-dt / tau_a)
        th[n] = theta_0 + a[n]
        V[n]  = beta * V[n-1] * (1 - s[n-1]) + (1 - beta) * g * u[n]
        s[n]  = Theta(V[n] - th[n])

    with beta = exp(-dt / tau_m) and a hard reset to zero: the (1 - s[n-1])
    factor zeroes the carried-over potential on the step after an event.
    Equation (23) reads s[n-1], the same one-step lag the reset carries, so
    `fired` serves both and is read before it is overwritten.

    E1 and E4 are one routine here, not two routines that agree, which is what
    SPEC section 4.5 asks for. With delta_a = 0 the adaptation state stays
    exactly 0.0 -- rho * 0.0 is 0.0, and delta_a * s is 0.0 for either value of
    s -- so th[n] is theta_0 + 0.0, which is theta_0 to the bit, and the
    comparison is the one E1 would have made with a scalar threshold. The
    bit-identity of test_T4_1 therefore holds by construction rather than by
    numerical coincidence, and an edit touching one encoder cannot leave the
    other behind. `tau_a` is immaterial in that case: rho multiplies a state
    that is exactly zero.

    Refractory semantics are SPEC section 4.2 / D17: during an absolute
    refractory period the potential is clamped to the reset value and incoming
    drive is discarded, so the interspike interval under saturating drive is
    exactly `refractory` and the rate ceiling exactly 1/refractory.

    Adaptation keeps decaying through a refractory period, and is not
    incremented within it because no event occurs there. Equation (23) has no
    refractory term, and the threshold is a property of the spike history
    rather than of the membrane, so clamping the membrane says nothing about
    it. Simon's ruling, 2026-09-04. Unobservable in the comparison runs, where
    SPEC section 4.5 fixes refractory at 0.0, but a Layer 3 reimplementation
    must make the same choice for test_G7b to agree event for event.

    Returns (channel_idx, sample_idx, v_trace_or_None, threshold_trace_or_None),
    with events in sample order and channel order within a sample.
    """
    n_ch, n = drive.shape
    beta = np.exp(-dt / tau_m)
    rho = np.exp(-dt / tau_a)

    v = np.zeros(n_ch, dtype=np.float64)
    a = np.zeros(n_ch, dtype=np.float64)      # adaptation state, equation (23)
    fired = np.zeros(n_ch, dtype=bool)
    last = np.full(n_ch, _NEVER, dtype=np.int64)
    v_trace = np.zeros((n_ch, n), dtype=np.float64) if want_state else None
    th_trace = np.zeros((n_ch, n), dtype=np.float64) if want_state else None

    chan_out, samp_out = [], []
    for i in range(n):
        # Equations (23) and (22). a starts at zero, so th[0] is theta_0 and a
        # constant drive meets no startup transient in the threshold.
        a = rho * a + delta_a * fired
        theta = theta_0 + a

        # Hard reset: potential carried over is zeroed for channels that fired
        # on the previous step.
        v = beta * v * ~fired + (1.0 - beta) * gain * drive[:, i]

        if refractory > 0.0:
            blocked = (i - last) * dt < refractory
            v = np.where(blocked, 0.0, v)
            fired = (v >= theta) & ~blocked
        else:
            fired = v >= theta

        if want_state:
            v_trace[:, i] = v
            th_trace[:, i] = theta

        if fired.any():
            idx = np.flatnonzero(fired)
            chan_out.append(idx)
            samp_out.append(np.full(idx.size, i, dtype=np.int64))
            last[idx] = i

    if chan_out:
        return (np.concatenate(chan_out), np.concatenate(samp_out),
                v_trace, th_trace)
    return (np.empty(0, np.int64), np.empty(0, np.int64), v_trace, th_trace)


def _reference_lattice(sig, dt, C, refractory, reference_update, r0,
                       want_state=False):
    """The reference-reset event rule of SPEC sections 4.3 and 4.4.

    At each sample, emit events until |sig - r| < C, where the reference r sits
    on a lattice of spacing C anchored at `r0`. A transient spanning several
    thresholds therefore emits several events sharing that timestamp, which is
    what makes the equation (16) bound hold as a theorem rather than as a
    tolerance.

    E2 applies this to the drive with r0 = drive[:, 0]. E3 applies it to the
    difference of exponentials of equation (20) with r0 = 0 -- the lattice is
    anchored at d = 0 as a property of the rule, not of the signal (SPEC 4.4,
    D26).

    One implementation rather than two, deliberately. D26 makes E2 against E3 a
    single-factor contrast in which equation (20) is the whole of the
    difference, and that claim is only true of the study if it is true of the
    code. Two copies of this rule could drift apart without any test noticing,
    because each encoder would still pass its own block.

    `reference_update="lattice"` holds the reference as an integer index m with
    r = r0 + m*C, never accumulated by repeated addition of C, so rounding
    error cannot creep into the bound over a long utterance (D18). `"exact"`
    sets the reference to the current signal value at event time.

    With refractory > 0 a channel emits at most one event per refractory
    period, and the equation (16) bound degrades accordingly.

    Returns (channel_idx, sample_idx, polarity, reference_trace_or_None), with
    events in sample order and channel order within a sample.
    """
    n_ch, n = sig.shape
    lattice = reference_update == "lattice"

    m = np.zeros(n_ch, dtype=np.int64)       # lattice index
    ref = np.array(r0, dtype=np.float64)     # used by the "exact" variant
    last = np.full(n_ch, _NEVER, dtype=np.int64)
    trace = np.zeros((n_ch, n)) if want_state else None

    chan_out, samp_out, pol_out = [], [], []
    for i in range(n):
        # Steps outstanding, in lattice units. For the lattice variant this is
        # measured from r0 rather than from the current reference value:
        # sig - (r0 + m*C) subtracts two nearly equal quantities and loses the
        # precision the ">= C" comparison needs, whereas (sig - r0)/C - m does
        # not. See _LATTICE_TOL.
        if lattice:
            step = (sig[:, i] - r0) / C - m
        else:
            step = (sig[:, i] - ref) / C
        # Truncation toward zero is what leaves the residual below C, which is
        # exactly the "emit until within C" rule of SPEC section 4.3.
        k = np.trunc(step + np.sign(step) * _LATTICE_TOL).astype(np.int64)

        if refractory > 0.0:
            blocked = (i - last) * dt < refractory
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
            ref = np.where(k != 0, sig[:, i], ref)

        if trace is not None:
            trace[:, i] = r0 + m * C if lattice else ref

    if chan_out:
        return (np.concatenate(chan_out), np.concatenate(samp_out),
                np.concatenate(pol_out), trace)
    return (np.empty(0, np.int64), np.empty(0, np.int64),
            np.empty(0, np.int8), trace)


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
        # delta_a = 0.0 makes this the non-adapting case of the E4 routine,
        # bit for bit -- see _integrate_and_fire and SPEC section 4.5.
        chan, samp, v_trace, _ = _integrate_and_fire(
            d, dt, self.theta, self.tau_m, self.gain, self.refractory,
            delta_a=0.0, want_state=return_state)

        train = SpikeTrain.from_events(
            channel=chan,
            time=samp * dt,
            polarity=np.ones(chan.size, dtype=np.int8),
            n_channels=self.n_channels,
            duration=n * dt,
            params=self._params(dt=dt),
        )
        if return_state:
            return train, {"v": v_trace}
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

        if n == 0:
            train = SpikeTrain.empty(self.n_channels, 0.0,
                                     self._params(dt=dt))
            return (train, {"reference": np.zeros((n_ch, 0))}) if return_state \
                else train

        chan, samp, pol, trace = _reference_lattice(
            d, dt, float(self.C), self.refractory, self.reference_update,
            r0=d[:, 0].copy(),                   # SPEC 4.3: reference init
            want_state=return_state)

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

    The event rule is the reference-lattice rule of SPEC section 4.3 applied to
    the difference signal d rather than to the drive (SPEC 4.4, D26), and is
    shared with E2 through `_reference_lattice`. What separates the two
    encoders is the bandpass of equation (20) and nothing else, which is what
    makes the E2-against-E3 comparison a single-factor contrast; test_T3_2 is
    the check that the bandpass is present.
    """
    NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND = "E3", "theta", -1, "envelope"

    def __init__(self, n_channels, theta=0.5, tau_fast=0.001, tau_slow=0.05,
                 refractory=0.0, reference_update="lattice"):
        self.n_channels, self.theta = n_channels, theta
        self.tau_fast, self.tau_slow, self.refractory = tau_fast, tau_slow, refractory
        self.reference_update = reference_update

    def encode_from_drive(self, drive, dt, seed=None, return_state=False):
        """Equations (18)-(21). Deterministic: `seed` is accepted for interface
        uniformity and unused.

        Two exponential lowpass filters with alpha = exp(-dt/tau) (SPEC section
        1, D28 — not the Euler pole dt/tau, which would put the peak of the
        step response about 0.25 per cent high and is what test_T3_5's first
        assertion is watching for), their difference taken by equation (20),
        and the SPEC 4.3 lattice rule applied to that difference.

        The lattice is anchored at d = 0 because the anchor is a property of
        the rule rather than of the signal. Under the initialisation above the
        two coincide — both filters start at drive[:, 0], so d[:, 0] is zero —
        but D26 specifies them independently and they are written that way.
        """
        if self.theta <= 0.0:
            raise ValueError(f"theta must be positive, got {self.theta}")
        if self.tau_slow <= self.tau_fast:
            raise ValueError(
                f"tau_slow ({self.tau_slow}) must exceed tau_fast "
                f"({self.tau_fast}); equation (20) otherwise changes sign, "
                "which silently exchanges the ON and OFF channels rather than "
                "failing")
        if self.reference_update not in ("lattice", "exact"):
            raise ValueError(f"unknown reference_update "
                             f"{self.reference_update!r}; "
                             "expected 'lattice' or 'exact'")

        u = self._check_drive(drive)
        n_ch, n = u.shape

        if n == 0:
            train = SpikeTrain.empty(self.n_channels, 0.0,
                                     self._params(dt=dt))
            return (train, {"d": np.zeros((n_ch, 0))}) if return_state else train

        # Equations (18)-(20). Both filters initialised to drive[:, 0], so a
        # constant drive leaves y_fast == y_slow == u at every sample and d
        # identically zero: no startup transient, and hence no events.
        alpha_f = np.exp(-dt / self.tau_fast)
        alpha_s = np.exp(-dt / self.tau_slow)
        y_fast = u[:, 0].copy()
        y_slow = u[:, 0].copy()
        d = np.zeros((n_ch, n))
        for i in range(n):
            y_fast = alpha_f * y_fast + (1.0 - alpha_f) * u[:, i]
            y_slow = alpha_s * y_slow + (1.0 - alpha_s) * u[:, i]
            d[:, i] = y_fast - y_slow

        # Equation (21): the SPEC 4.3 rule on d, lattice anchored at zero.
        chan, samp, pol, _ = _reference_lattice(
            d, dt, float(self.theta), self.refractory, self.reference_update,
            r0=np.zeros(n_ch), want_state=False)

        train = SpikeTrain.from_events(
            channel=chan,
            time=samp * dt,
            polarity=pol,
            n_channels=self.n_channels,
            duration=n * dt,
            params=self._params(dt=dt),
        )
        if return_state:
            return train, {"d": d}
        return train


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
        """Equations (22)-(23) over (12)-(13). SPEC section 4.5.

        The whole of E4 is the shared routine with delta_a passed through. The
        reduction to E1 at delta_a = 0 is therefore not something this method
        arranges or approximates; it is what the same code does when handed a
        zero. Deterministic, so `seed` is unused.
        """
        d = self._check_drive(drive)
        n = d.shape[1]
        chan, samp, v_trace, th_trace = _integrate_and_fire(
            d, dt, self.theta_0, self.tau_m, self.gain, self.refractory,
            delta_a=self.delta_a, tau_a=self.tau_a, want_state=return_state)

        train = SpikeTrain.from_events(
            channel=chan,
            time=samp * dt,
            polarity=np.ones(chan.size, dtype=np.int8),
            n_channels=self.n_channels,
            duration=n * dt,
            params=self._params(dt=dt),
        )
        if return_state:
            return train, {"v": v_trace, "threshold": th_trace}
        return train


class PhaseLocked(Encoder):
    """E5 — phase-locked fine structure. SPEC section 4.6, equations (24)-(26).

    Consumes the subband waveform, not the envelope: the whole point of this
    encoder is to represent the carrier that the envelope discards.

    The rate parameter is `cycle_divisor`, not `threshold`. Q11 measured
    `threshold` moving the event count by 1.04x over the standard sweep, because
    the count is bounded above by the number of upward zero crossings — a
    property of the carrier and the drive, not of any parameter — and the
    threshold only gates quiet passages. `cycle_divisor` moves the count as 1/k
    while leaving frequency resolution and per-event timing precision untouched,
    which matters because E5 is in the battery to test whether fine timing buys
    anything: reaching a low budget by discarding channels would remove
    frequency resolution at the same time and confound the result. D40.
    """
    NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND = ("E5", "cycle_divisor", -1,
                                                    "subband")
    RATE_PARAM_INTEGER = True

    def __init__(self, n_channels, cycle_divisor=1, threshold=0.05,
                 env_cutoff=100.0, gamma=1.0, f_lock=1500.0, refractory=0.001,
                 mode="deterministic", centre_frequencies=None,
                 lambda_max=200.0, z_0=0.0):
        if cycle_divisor != int(cycle_divisor) or int(cycle_divisor) < 1:
            raise ValueError("cycle_divisor must be a positive integer, got "
                             f"{cycle_divisor!r}")
        self.n_channels = n_channels
        self.cycle_divisor = int(cycle_divisor)
        self.threshold, self.env_cutoff, self.gamma = threshold, env_cutoff, gamma
        self.f_lock, self.refractory, self.mode = f_lock, refractory, mode
        self.centre_frequencies = centre_frequencies
        self.lambda_max, self.z_0 = lambda_max, z_0

    # -- internal signals --------------------------------------------------

    def _internal_envelope(self, drive, dt):
        """Half-wave rectification then a fourth-order Butterworth lowpass at
        `env_cutoff`, matching the filter family of equation (9). D41.

        This is computed here rather than taken from the front end because
        `encode_from_drive` receives the subband waveform. SPEC section 4.1
        forbids further filtering, compression, scaling or normalisation of the
        *drive*; this is an internal gating signal and the drive itself reaches
        the event rule untouched.

        Hilbert magnitude is the obvious alternative and is rejected: the
        analytic signal uses the whole record, so the gate at time t would
        depend on signal after t. For a battery whose T3 probe is boundary
        detection that leaks post-boundary information into the pre-boundary
        gate, and it would do so for one encoder out of six. The cost is that
        `env_cutoff` is a fixed constant rather than the channel-relative
        cutoff of D21, since there are no channel bandwidths here to use.
        """
        nyquist = 0.5 / dt
        sos = butter(4, min(self.env_cutoff / nyquist, 0.99), btype="low",
                     output="sos")
        return sosfilt(sos, np.maximum(drive, 0.0), axis=-1)

    def _above_lock(self):
        """Channels whose centre frequency exceeds `f_lock`. With
        `centre_frequencies` None every channel is treated as below cutoff,
        which is what `encode_from_drive` sees unless a caller supplies them."""
        if self.centre_frequencies is None:
            return np.zeros(self.n_channels, dtype=bool)
        return np.asarray(self.centre_frequencies, dtype=np.float64) > self.f_lock

    # -- event rules -------------------------------------------------------

    def _locked_events(self, x, env, dt):
        """SPEC 4.6 deterministic rule, in the order the specification states
        it: upward zero crossings of the subband; discard those where the
        envelope does not exceed `threshold`; of the survivors keep every
        `cycle_divisor`-th, counting from the first survivor in this channel;
        then apply `refractory`.

        The refractory comparison is an integer sample difference, as
        `_integrate_and_fire` does, and not a difference of absolute times.
        `(i + s) * dt - (j + s) * dt` is not bit-identical to `i * dt - j * dt`,
        so an interval of exactly `refractory / dt` samples decides differently
        at different offsets and `test_G4` fails by a handful of events.
        """
        crossings = np.where((x[:-1] <= 0.0) & (x[1:] > 0.0))[0] + 1
        survivors = crossings[env[crossings] > self.threshold]
        kept = survivors[::self.cycle_divisor]
        if self.refractory <= 0.0:
            return kept
        out, last = [], _NEVER
        for i in kept:
            if (i - last) * dt >= self.refractory:
                out.append(i)
                last = i
        return np.asarray(out, dtype=np.int64)

    def _poisson_events(self, x, dt, rng):
        """Inhomogeneous Poisson, equations (24)-(25).

            z = max(x, 0) ** gamma
            lambda = lambda_max * z / (z + z_0)

        `z_0 = 0` is the default and makes the saturation trivial: the
        intensity is `lambda_max` wherever the rectified signal is positive.
        Guarded so that z = 0 gives zero intensity rather than 0/0.

        SPEC 4.6 does not say whether `refractory` applies here. It is applied,
        because it is a declared parameter of the encoder and a refractory
        period is physiological; the reading is recorded here rather than
        raised, since this mode is excluded from the six-encoder comparison of
        section 6.4 and from `test_G3` and `test_G4`, and no test exercises it.
        """
        z = np.maximum(x, 0.0) ** self.gamma
        denom = z + self.z_0
        lam = np.where(denom > 0.0, self.lambda_max * z / np.where(denom > 0.0,
                                                                   denom, 1.0), 0.0)
        fired = rng.random(x.size) < lam * dt
        idx = np.flatnonzero(fired)
        if self.refractory <= 0.0:
            return idx
        out, last = [], _NEVER
        for i in idx:
            if (i - last) * dt >= self.refractory:
                out.append(i)
                last = i
        return np.asarray(out, dtype=np.int64)

    # -- the encoder -------------------------------------------------------

    def encode_from_drive(self, drive, dt, seed=None, return_state=False):
        if self.mode not in ("deterministic", "poisson"):
            raise ValueError(f"unknown mode {self.mode!r}; expected "
                             "'deterministic' or 'poisson'")
        if self.mode == "poisson" and seed is None:
            raise ValueError("mode='poisson' requires a seed: the draws must be "
                             "reproducible for test_G1 and for the manifest")

        d = self._check_drive(drive)
        n = d.shape[1]
        env = self._internal_envelope(d, dt)
        above = self._above_lock()
        rng = np.random.default_rng(seed)

        channels, times = [], []

        # Channels above f_lock revert to envelope-driven LIF behaviour. Built
        # as an LIF instance on the internal envelope rather than as a copy of
        # its constants, so that "E5 with f_lock below every centre frequency
        # equals E1 on the same envelope" is an identity a test can assert
        # rather than an agreement two code paths happen to reach. D41.
        if np.any(above):
            idx_above = np.flatnonzero(above)
            fallback = LIF(n_channels=int(idx_above.size))
            sub = fallback.encode_from_drive(env[idx_above], dt)
            channels.extend(idx_above[sub.channel].tolist())
            times.extend(sub.time.tolist())

        for c in np.flatnonzero(~above):
            if self.mode == "deterministic":
                idx = self._locked_events(d[c], env[c], dt)
            else:
                idx = self._poisson_events(d[c], dt, rng)
            channels.extend([int(c)] * idx.size)
            times.extend((idx * dt).tolist())

        train = SpikeTrain.from_events(
            channels, times, np.ones(len(times), dtype=np.int8),
            self.n_channels, n * dt, self._params())
        if return_state:
            return train, {"envelope": env}
        return train



class TTFS(Encoder):
    """E6 — time to first spike. Equations (27)-(29), SPEC section 4.7.

    The sparsest scheme in the set, and the exact inverse of E1: all the
    information is in *when* the single event of a channel-frame arrives and
    none of it is in how many events there are. The event budget is bounded
    exactly at `n_channels / hop` events per second, which no other encoder
    here can promise.

    The drive is framed, the energy of each channel-frame is measured, and a
    channel emits once in a frame at a latency that decreases with that energy.
    `mode="log"` maps energy to latency by equation (28); `mode="lif"` by the
    closed-form first-passage time of a LIF under constant current, equation
    (29). `mode` is not one of the swept axes of proposal section 6.6 -- the
    SPEC 4.7 default `"log"` is what the comparison runs use.

    **The gate is relative, strict, and over the whole utterance.** A channel
    emits in frame m when `E_c[m] > e_frac * E_max`, with `E_max` the largest
    frame energy over *all* channels and *all* frames. Three properties of that
    sentence are load-bearing and each was paid for:

    - *Relative*, because the absolute `e_min` of the earlier draft sat 6.8
      decades below the quietest frame of the test drive and gated nothing,
      giving `test_G3` a span of exactly 1.00x. No absolute default can suit
      both a synthetic drive and real audio through the front end. Q14, D43.
    - *Strict*, because on an all-zero drive `E_max` is zero and a non-strict
      gate emits in every channel of every frame, which violates the silence
      clause of SPEC 4.1. Strictness also removes the clipping rule that
      proposal 5.6 asks for: see `_log_offsets`. Q14, D43.
    - *Over all channels*, not per channel. A per-channel maximum is the more
      natural reading and it is wrong: it maps every channel's own loudest
      frame to latency zero, which flattens the spectral profile that is the
      entire content of a time-to-first-spike snapshot. `test_T6_2` detects
      the mistake, by asserting a Pearson correlation of exactly -1 within a
      frame, which holds only if every channel shares one pair of
      normalisation constants. Q14, Q16, D44.

    The cost is that E6 is the only encoder in the battery with utterance-level
    normalisation -- E1 to E5 are level-sensitive -- so at matched budget E6
    gets a scale invariance the others do not. Recorded in SPEC 4.7 and D43 as
    a limitation for the paper rather than left for a referee to find.

    Unipolar: every event carries polarity +1. A latency code has no second
    polarity to carry, there being no such thing as a negative first spike.

    Note that with `hop < frame` -- the declared default, 10 ms against 25 ms --
    two events in the *same* channel from *adjacent* frames can share a
    timestamp, when their offsets differ by exactly one hop. That is legal:
    `SpikeTrain` orders ties and `test_T6_1` counts finite offsets rather than
    distinct times. It is also why the state matrices exist. Frame membership
    is not recoverable from event times at `hop < frame`, so the T6 tests read
    `state["offsets"]` and `state["energy"]` directly. D44.
    """
    NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND = "E6", "e_frac", -1, "envelope"

    def __init__(self, n_channels, e_frac=0.20, frame=0.025, hop=0.010,
                 tau_m=0.02, theta=1.0, mode="log"):
        self.n_channels, self.e_frac = n_channels, e_frac
        self.frame, self.hop = frame, hop
        self.tau_m, self.theta, self.mode = tau_m, theta, mode

    # -- framing -----------------------------------------------------------

    def _frame_energies(self, d, dt):
        """Equation (27): the sum of squared drive samples in each frame.

        Computed on whatever drive is supplied with no further transformation,
        as SPEC 4.7 requires, so that a test can reproduce it independently --
        `test_T6_3` does exactly that, with `np.sum(drive[0] ** 2)`.

        Frame m covers `[m*hop, m*hop + frame)` and there are
        `floor((n_samples*dt - frame)/hop) + 1` of them, which is SPEC 4.7
        verbatim and is evaluated in seconds for that reason: it is the formula
        a Layer 3 reimplementation works from. The integer-sample form
        `(n - round(frame/dt)) // round(hop/dt) + 1` agrees with it at every
        frame and hop the suite uses, including the knife-edge case of
        `test_T6_3` where `frame == hop == n*dt` makes the expression exactly
        zero and one frame is expected rather than none. Checked rather than
        assumed, because a value of -1e-16 there would floor to -1, yield zero
        frames, and silently produce an encoder that emits nothing.

        A drive shorter than one frame gives zero frames and hence no events,
        rather than raising: SPEC 4.1 makes an empty train legal.
        """
        n_ch, n = d.shape
        n_frames = max(int(np.floor((n * dt - self.frame) / self.hop)) + 1, 0)
        energy = np.zeros((n_ch, n_frames), dtype=np.float64)
        for m in range(n_frames):
            i0 = int(round(m * self.hop / dt))
            i1 = min(int(round((m * self.hop + self.frame) / dt)), n)
            energy[:, m] = np.sum(d[:, i0:i1] ** 2, axis=1)
        return energy

    # -- energy-to-latency maps --------------------------------------------

    def _log_offsets(self, e, e_max, e_min):
        """Equation (28), the direct logarithmic map:

            offset = T_f * (1 - (log E - log E_min) / (log E_max - log E_min))

        `E_min` is the gate itself, `e_frac * E_max`. The two roles proposal
        5.6 gives it -- emission gate and normalisation floor -- are one
        quantity here, which is what makes the equation evaluable: a floor of
        zero would send `log E_min` to -inf and every offset to nan, and Q16
        found two of E6's own tests passing `e_min=0.0`. D44.

        Two consequences, and neither needs a rule of its own. A frame at the
        gate maps to `T_f` and a frame at `E_max` maps to zero, and because the
        gate is *strict*, anything that fires has `log E - log E_min > 0` and
        so an offset strictly inside its frame. Proposal 5.6's "clipped to the
        frame" is therefore unreachable rather than implemented, and the one
        event Q16 measured landing on the next window's edge was an artefact of
        the non-strict gate. `test_T6_1` asserts the strictness directly.

        The denominator is written as `log E_max - log E_min` rather than the
        algebraically equal and better-conditioned `-log e_frac`, because
        equation (28) is written that way and SPEC section 1 is explicit about
        the cost of a Layer 3 reimplementation differing from this one in the
        last bits. It cannot vanish when anything fires: some `E > E_min` and
        every `E <= E_max`, so `E_min < E_max` strictly.
        """
        return self.frame * (1.0 - (np.log(e) - np.log(e_min))
                             / (np.log(e_max) - np.log(e_min)))

    def _lif_offsets(self, e):
        """Equation (29), the first-passage time of a LIF under constant
        current I proportional to the frame energy:

            offset = tau_m * log(I / (I - theta))    for I > theta

        The constant of proportionality is 1, so `I = E_c[m]`. SPEC 4.7 gives
        no `gain` for this encoder, and `test_T6_3` computes its expected
        latency from `I = np.sum(drive[0] ** 2)`, which is the frame energy
        itself; anything else would fail it.

        **A reading SPEC 4.7 does not fix.** Equation (29) is unbounded as
        I approaches theta from above -- at I = 1.001 and theta = 1 it gives
        138 ms, five and a half times the default 25 ms frame -- and the
        specification says nothing about a latency exceeding the frame that
        produced it. Such an event is suppressed here, on the reading that the
        neuron simply did not reach threshold inside its window, so there is no
        first spike in that frame. The alternative readings are to clip to
        `T_f`, which stacks unrelated energies onto one timestamp, or to emit
        outside the frame, which puts the event in a later frame's territory
        and breaks the invariant `test_T6_1` asserts for the log map.

        Recorded here rather than raised as a question: `mode` is not a swept
        axis of proposal section 6.6, the comparison runs use the SPEC 4.7
        default `"log"`, and the only test of this branch drives it at I = 4.0,
        well clear of the boundary. It is a reading a Layer 3 reimplementation
        must know about, which is why it is written where one will look.
        """
        lat = np.full(e.shape, np.nan, dtype=np.float64)
        spiking = e > self.theta
        i = e[spiking]
        lat[spiking] = self.tau_m * np.log(i / (i - self.theta))
        # NaN compares False, so a non-spiking entry stays NaN rather than
        # being re-flagged here.
        lat[lat >= self.frame] = np.nan
        return lat

    # -- the encoder -------------------------------------------------------

    def encode_from_drive(self, drive, dt, seed=None, return_state=False):
        """Equations (27)-(29). Deterministic: `seed` is accepted for interface
        uniformity and unused.

        `e_frac >= 1` puts the gate at or above the largest frame energy in the
        utterance and so emits nothing at all. That is coherent rather than an
        error -- a gate above the maximum gates everything -- and is left to
        produce an empty train, which SPEC 4.1 makes legal.
        """
        if self.mode not in ("log", "lif"):
            raise ValueError(f"unknown mode {self.mode!r}; expected "
                             "'log' or 'lif'")
        if self.mode == "log" and self.e_frac <= 0.0:
            raise ValueError(
                f"e_frac must be positive in mode='log', got {self.e_frac!r}: "
                "under D44 it is both the emission gate and the normalisation "
                "floor E_min of equation (28), and the value is legal as a "
                "gate but not as a floor -- log E_min would be -inf and every "
                "offset nan")
        if self.frame <= 0.0 or self.hop <= 0.0:
            raise ValueError(f"frame and hop must be positive, got "
                             f"frame={self.frame!r}, hop={self.hop!r}")

        d = self._check_drive(drive)
        n = d.shape[1]
        energy = self._frame_energies(d, dt)
        offsets = np.full(energy.shape, np.nan, dtype=np.float64)

        # E_max over all channels and all frames, and the gate below it. On
        # silence E_max is 0.0, the strict gate admits nothing, and no
        # logarithm of zero is ever taken.
        e_max = float(energy.max()) if energy.size else 0.0
        e_min = self.e_frac * e_max
        gated = energy > e_min

        if np.any(gated):
            if self.mode == "log":
                offsets[gated] = self._log_offsets(energy[gated], e_max, e_min)
            else:
                offsets[gated] = self._lif_offsets(energy[gated])

        emit = np.isfinite(offsets)
        chan, frame_idx = np.nonzero(emit)
        times = frame_idx * self.hop + offsets[chan, frame_idx]

        train = SpikeTrain.from_events(
            channel=chan,
            time=times,
            polarity=np.ones(chan.size, dtype=np.int8),
            n_channels=self.n_channels,
            duration=n * dt,
            params=self._params(dt=dt),
        )
        if return_state:
            return train, {"energy": energy, "offsets": offsets}
        return train
