"""Encoder stubs — the API surface of SPEC.md section 4.

STATUS: skeleton. Every encode_from_drive raises NotImplementedError.

Class attributes (NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND) and the
__init__ signatures are part of the contract and are already correct — the
known-answer suite reads them. Fill in the method bodies; do not change the
signatures without raising it in QUESTIONS.md first.

Equation numbers refer to docs/proposal_v2.md.
"""
import numpy as np
from .spiketrain import SpikeTrain


class Encoder:
    NAME: str = "?"
    RATE_PARAM: str = "?"
    RATE_DIRECTION: int = -1
    DRIVE_KIND: str = "envelope"

    def encode(self, audio, sample_rate, seed=None):
        """Front end composed with encode_from_drive. SPEC section 4.1."""
        raise NotImplementedError(f"{self.NAME}.encode")

    def encode_from_drive(self, drive, dt, seed=None, return_state=False):
        raise NotImplementedError(f"{self.NAME}.encode_from_drive")


class LIF(Encoder):
    """E1 — leaky integrate-and-fire. Equations (11)-(13)."""
    NAME, RATE_PARAM, RATE_DIRECTION, DRIVE_KIND = "E1", "theta", -1, "envelope"

    def __init__(self, n_channels, theta=1.0, tau_m=0.02, gain=1.0,
                 refractory=0.0, reset="hard"):
        self.n_channels, self.theta, self.tau_m = n_channels, theta, tau_m
        self.gain, self.refractory, self.reset = gain, refractory, reset

    def encode_from_drive(self, drive, dt, seed=None, return_state=False):
        raise NotImplementedError("E1: equations (12)-(13), hard reset to zero")


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
        raise NotImplementedError("E2: equations (14)-(15)")


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
