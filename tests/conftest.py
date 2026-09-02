"""
Shared fixtures for the known-answer suite.

AUTHORED BY THE DESIGN SESSION. See the header of test_known_answers.py.
Do not edit to make a failing test pass.
"""
import numpy as np
import pytest

FS = 16000
DT = 1.0 / FS


@pytest.fixture
def dt():
    return DT


@pytest.fixture
def fs():
    return FS


def constant_drive(value, n_channels=4, duration=1.0, dt=DT):
    """Flat drive at `value` in every channel."""
    n = int(round(duration / dt))
    return np.full((n_channels, n), float(value))


def ramp_drive(slope, n_channels=4, duration=1.0, dt=DT):
    """Linear ramp starting at zero, slope in units per second."""
    n = int(round(duration / dt))
    t = np.arange(n) * dt
    return np.tile(slope * t, (n_channels, 1))


def sine_drive(amplitude, frequency, n_channels=4, duration=2.0, dt=DT):
    """Sinusoidal drive, starting and ending at zero phase."""
    n = int(round(duration / dt))
    t = np.arange(n) * dt
    return np.tile(amplitude * np.sin(2 * np.pi * frequency * t), (n_channels, 1))


def step_drive(low, high, t_step, n_channels=4, duration=1.0, dt=DT):
    n = int(round(duration / dt))
    t = np.arange(n) * dt
    return np.tile(np.where(t < t_step, low, high), (n_channels, 1))


def tone(frequency, duration=1.0, dt=DT, amplitude=1.0, phase=0.0):
    n = int(round(duration / dt))
    t = np.arange(n) * dt
    return amplitude * np.sin(2 * np.pi * frequency * t + phase)


def harmonic_complex(f0, n_harmonics=8, duration=1.0, dt=DT):
    n = int(round(duration / dt))
    t = np.arange(n) * dt
    x = np.zeros(n)
    for k in range(1, n_harmonics + 1):
        x += np.sin(2 * np.pi * f0 * k * t) / k
    return x / np.max(np.abs(x))


def speechlike(duration=1.0, dt=DT, seed=0):
    """Amplitude-modulated noise. Not speech, but broadband and non-stationary,
    which is what the robustness tests need."""
    rng = np.random.default_rng(seed)
    n = int(round(duration / dt))
    t = np.arange(n) * dt
    noise = rng.standard_normal(n)
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 4 * t) ** 2
    return 0.5 * noise * env


# --- encoder registry -------------------------------------------------------
# Each entry: (label, factory, kwargs for a mid-range operating point).
# Generic tests are parametrised over this. Extend it as encoders land; do not
# remove entries to make a suite pass.

def all_encoders():
    from spikeenc import encoders as E
    return [
        ("E1", E.LIF, dict(n_channels=4, theta=1.0, tau_m=0.02)),
        ("E2", E.SendOnDelta, dict(n_channels=4, C=0.1)),
        ("E3", E.TemporalContrast, dict(n_channels=4, theta=0.2)),
        ("E4", E.ALIF, dict(n_channels=4, theta_0=1.0, delta_a=0.5, tau_a=0.1)),
        ("E5", E.PhaseLocked, dict(n_channels=4, threshold=0.05)),
        ("E6", E.TTFS, dict(n_channels=4, e_min=1e-6)),
    ]


@pytest.fixture(params=all_encoders(), ids=lambda p: p[0])
def encoder_case(request):
    label, cls, kwargs = request.param
    return label, cls, kwargs


def drive_for(cls, n_channels=4, duration=1.0, dt=DT, seed=0):
    """A drive array of the kind the encoder declares it consumes."""
    if cls.DRIVE_KIND == "subband":
        x = speechlike(duration=duration, dt=dt, seed=seed)
        return np.tile(x, (n_channels, 1))
    rng = np.random.default_rng(seed)
    n = int(round(duration / dt))
    t = np.arange(n) * dt
    base = 1.0 + 0.8 * np.sin(2 * np.pi * 3 * t)
    return np.stack([base * (0.6 + 0.2 * i) + 0.02 * rng.standard_normal(n)
                     for i in range(n_channels)])
