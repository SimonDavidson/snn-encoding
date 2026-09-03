# SPEC.md — interface contract

Authored by the **design session** before implementation. `tests/test_known_answers.py`
is written against this contract, so the contract is binding: if the
implementation needs to deviate, raise it in `QUESTIONS.md` rather than changing
the tests.

Package name: `spikeenc`, installed with `pip install -e .` from the repo root.

---

## 1. Units and conventions

Fixed throughout, no exceptions:

| Quantity | Unit | Notes |
|---|---|---|
| Time, time constants, refractory | seconds (float64) | never samples, never milliseconds |
| Frequency, sample rate | hertz | |
| Audio | float64, nominal range [-1, 1] | mono, single channel |
| Channel index | int, 0 = lowest centre frequency | ascending in frequency |
| Polarity | int8, +1 or -1 | unipolar encoders emit +1 only |

Channel 0 is always the lowest frequency. Any encoder that reverses this
silently will fail `test_F3_erb_spacing_is_uniform` and several others.

---

## 2. `spikeenc.SpikeTrain`

```python
@dataclass(frozen=True)
class SpikeTrain:
    channel:    np.ndarray  # int32,   shape (N,)
    time:       np.ndarray  # float64, shape (N,), seconds
    polarity:   np.ndarray  # int8,    shape (N,), +1 or -1
    n_channels: int
    duration:   float       # seconds, of the source audio
    params:     dict        # encoder name + every parameter, for provenance
```

**Canonical ordering.** Events are sorted by `time` ascending; ties broken by
`channel` ascending, then by `polarity` descending (+1 before -1). Every
`SpikeTrain` returned by any encoder must already be in canonical order.
Determinism tests compare arrays elementwise and will fail on unordered output.

**Empty trains are legal.** Zero events is a valid encoding of silence and must
not raise.

Required methods:

```python
def counts_per_channel(self) -> np.ndarray   # int64, shape (n_channels,)
def times_in_channel(self, c: int) -> np.ndarray  # float64, ascending
def __len__(self) -> int
```

---

## 3. Front end — `spikeenc.frontend.Filterbank`

```python
Filterbank(
    n_channels: int,
    f_min: float = 50.0,
    f_max: float = 8000.0,
    sample_rate: int = 16000,
    spacing: str = "erb",        # "erb" | "mel" | "linear"
    order: int = 4,
    compensate_group_delay: bool = False,
)
```

Attributes and methods:

```python
.centre_frequencies -> np.ndarray   # (n_channels,), ascending
.bandwidths         -> np.ndarray   # (n_channels,), the b_c of eq (4)
.impulse_response(channel: int, n_samples: int) -> np.ndarray
.subbands(audio)    -> np.ndarray   # (n_channels, n_samples), eq (7)
.envelope(audio, method="hilbert") -> np.ndarray   # "hilbert" | "rectify_lowpass"
.compress(env, method="log", epsilon=1e-8, exponent=0.3) -> np.ndarray
```

`spacing="erb"` places centre frequencies uniformly on the ERB-rate scale of
equation (6) between `f_min` and `f_max` inclusive, so `centre_frequencies[0] ==
f_min` and `centre_frequencies[-1] == f_max`.

**Group-delay compensation applies to the path, not the filterbank.** When
`compensate_group_delay=True`, each channel is advanced by the sum of the
declared lags of every stage between the input and the returned envelope:

    lag_c = gammatone_lag_c + envelope_stage_lag_c

with `gammatone_lag_c = (order - 1) / (2 * pi * b_c)` and the envelope-stage
lag being zero for `method="hilbert"` and `method="none"`, and the lowpass
group delay at DC for `method="rectify_lowpass"`. Every stage that introduces a
channel-dependent lag must declare it; a stage that cannot must raise rather
than allow silent partial compensation.

The reason for stating it this way is that compensation applied inside
`subbands` cannot remove a lag introduced downstream of it. Under the
channel-relative cutoff above, the envelope lowpass contributes the *larger* of
the two lags, and contributes most in the low channels where the gammatone
delay is already worst. Compensating only the first stage would leave roughly
two thirds of the onset skew in place while the flag reported alignment, which
is worse than not compensating at all: an uncompensated bias is a known
quantity, a partially compensated one is not.

Compensation is exact only for components slow relative to the stage
bandwidths, since Butterworth group delay is not flat. For T3, where the
quantity of interest is onset timing, `test_F6` measures the alignment actually
achieved rather than assuming the analytic value; report the measured residual
spread alongside any T3 result taken with compensation on.

**Envelope cutoff (equation 9).** The `"rectify_lowpass"` branch uses a
channel-relative cutoff rather than one value for the whole bank:

    f_cut_c = min(f_cut, b_c)

with `b_c` the channel's own bandwidth from equation (5) and `f_cut` a global
ceiling, default 1000 Hz. Fourth order.

The reason is physical rather than empirical. A subband of bandwidth `b_c`
cannot carry envelope modulation faster than `b_c`, so a cutoff above the
channel bandwidth admits carrier without admitting any more envelope. A single
fixed cutoff cannot satisfy both ends of the bank at once: 300 Hz sits above
the carrier in a 196 Hz channel and removes nothing, while a cutoff low enough
for that channel would discard genuine envelope at 3 kHz.

This departs from equation (9) as written in proposal v2, which specifies one
cutoff. The equation is underspecified rather than wrong, and proposal 5.0
should carry the channel-relative form when v3 is issued.

Note for the record why the fixed-cutoff alternative was rejected on more than
accuracy. Carrier leaking into the low-channel envelope would make E1, E2, E3,
E4 and E6 partly phase-locking encoders in exactly the channels where F_0 and
its low harmonics live. E5 exists to be the encoder that carries fine
structure, and prediction P-03 turns on the contrast between it and the
envelope encoders on T2. An envelope method that smuggles periodicity into the
others would not merely lose accuracy; it would blur the distinction the probe
battery is built to measure, and it would do so invisibly.

`method="none"` returns the rectified subband without lowpass filtering, for
callers that want to supply their own.

**Compression method strings.** `compress` takes `method="log"` for the
logarithmic branch of equation (10) and `method="power"` for the power-law
branch, the latter using `exponent`. `epsilon` applies to the logarithmic
branch only. `method="none"` returns the envelope unchanged, which is needed
for E5, whose drive is the subband waveform rather than a compressed envelope.

**Group delay.** Gammatone filters have frequency-dependent group delay: a
low-frequency channel responds later than a high-frequency one to the same
acoustic event. This is biologically faithful and is the default
(`compensate_group_delay=False`).

It is also a systematic, frequency-dependent bias on event timing, and
therefore on T3 boundary detection, where a single onset appears at different
times in different channels. **No test in the known-answer suite detects
it** — F1 checks spectral peaks, and G4 passes because a uniform shift of the
input remains uniform at the output. It has to be handled by declaration
rather than by test.

With `compensate_group_delay=True`, each channel's output is advanced by that
channel's group delay at its centre frequency, aligning onsets across the
bank. Treated as a swept binary axis in the study; whichever setting produced
a reported result is stated in the paper, since a reader comparing T3 figures
against another group's has no way to infer it.

---

## 4. Encoders

### 4.1 Base contract

Every encoder subclasses `spikeenc.encoders.Encoder` and declares:

```python
class Encoder:
    NAME: str                # "E1", "E2", ...
    RATE_PARAM: str          # constructor kwarg controlling event rate
    RATE_DIRECTION: int      # +1 if increasing the param increases rate, -1 if decreases
    DRIVE_KIND: str          # "envelope" | "subband"

    def encode(self, audio: np.ndarray, sample_rate: int,
               seed: int | None = None) -> SpikeTrain: ...

    def encode_from_drive(self, drive: np.ndarray, dt: float,
                          seed: int | None = None,
                          return_state: bool = False) -> SpikeTrain: ...
```

`encode_from_drive` is the testable core. It takes a pre-computed drive array of
shape `(n_channels, n_samples)` — the compressed envelope for
`DRIVE_KIND == "envelope"`, the subband waveform for `"subband"` — and bypasses
the filterbank entirely. **This method must not apply any additional
filtering, compression, scaling or normalisation to `drive`.** Every analytic
test in the suite goes through it, and any hidden preprocessing invalidates the
comparison against the closed-form predictions.

`encode` is `encode_from_drive` composed with the front end, nothing more.

With `return_state=True`, return `(SpikeTrain, dict)` where the dict carries
named internal traces of shape `(n_channels, n_samples)`. Required keys are
listed per encoder below.

**Determinism.** With `seed` fixed (or for deterministic encoders, regardless),
two calls on identical input return elementwise-identical arrays.

**Silence.** All-zero drive produces zero events for every encoder. For
log-compressed drive this follows naturally; implementations that normalise or
auto-gain must still honour it.

### 4.2 E1 — LIF

`LIF(n_channels, theta=1.0, tau_m=0.02, gain=1.0, refractory=0.0, reset="hard")`

RATE_PARAM `"theta"`, RATE_DIRECTION `-1`, DRIVE_KIND `"envelope"`.

Discrete update, equations (12)–(13), hard reset to zero. Unipolar: all
polarities `+1`. State keys: `"v"`.

**Refractory semantics.** During an absolute refractory period the membrane
potential is clamped to the reset value and incoming drive is discarded. The
interspike interval under saturating drive is therefore exactly `refractory`,
and the rate ceiling exactly `1/refractory`.

This is a declared modelling choice rather than an implementation detail,
because clamping is itself mildly adaptive: discarding drive during recovery
suppresses the response to sustained strong input, in the same direction as
spike-frequency adaptation. E1 must be a clean *non*-adapting baseline for the
E1-against-E4 contrast that prediction P-01 rests on, so **`refractory` is
fixed at `0.0` for all E1 and E4 comparison runs.**

Note also that `refractory` is a second rate-limiting mechanism alongside the
declared RATE_PARAM `theta`. Sweeping both would confound the matched-budget
comparison of proposal §6.4, so `refractory` is a fixed, declared parameter
and never a swept axis.

### 4.3 E2 — Send-on-delta

`SendOnDelta(n_channels, C=0.1, refractory=0.0, reference_update="lattice")`

RATE_PARAM `"C"`, RATE_DIRECTION `-1`, DRIVE_KIND `"envelope"`.

Reference initialised to `drive[:, 0]`. `reference_update="lattice"` advances the
reference by exactly ±C per event (equations 14–15); `"exact"` sets it to the
current drive value.

**Required behaviour, on which the reconstruction bound depends:** at each
sample, emit events until `|drive − reference| < C`, i.e. a fast transient
spanning several thresholds emits several events at that sample timestamp. With
`refractory > 0` this is capped and the bound of equation (16) degrades; with
`refractory == 0` the bound holds strictly. State keys: `"reference"`.

**Reference representation.** In the `"lattice"` variant the reference is held
as an integer lattice index `m`, with the value computed as `r = r0 + m * C`,
not accumulated by repeated addition of `C`. Repeated floating-point addition
accumulates rounding error across a long utterance and can erode the equation
(16) bound that `test_T2_1` asserts; an integer index keeps the bound exact
regardless of duration.

**Threshold comparison tolerance.** Outstanding lattice steps are measured as
`(u - r0)/C - m`, never as `(u - r0 - m*C)/C`, and the comparison against the
threshold carries a tolerance of `1e-9` lattice units.

This is part of the contract, not an implementation detail, because Layer 3 of
the validation protocol calls for an independent reimplementation of E2 whose
output is compared event for event. Two implementations that differ here
disagree at every excursion crest, and the disagreement would look like a bug
in one of them.

The reason it is needed: drive landing exactly on a lattice point is routine,
not exceptional. With `u = 1.0` and `r = 9C = 0.9`, equation (14) asks whether
`u - r >= C`. In exact arithmetic `0.1 >= 0.1` fires; in doubles the
subtraction yields `0.09999999999999998` and it does not, so the crest event of
every excursion is dropped and the descent begins one step in. The tolerance
can only fire an event early, never late, so the bound of equation (16)
tightens rather than loosens.


### 4.4 E3 — Temporal contrast

`TemporalContrast(n_channels, theta=0.5, tau_fast=0.001, tau_slow=0.05, refractory=0.0)`

RATE_PARAM `"theta"`, RATE_DIRECTION `-1`, DRIVE_KIND `"envelope"`.

Equations (18)–(21). Both filters initialised to `drive[:, 0]`, so a constant
drive produces no startup transient and hence no events. Symmetric thresholds:
`theta_plus == theta_minus == theta`. State keys: `"d"`.

### 4.5 E4 — Adaptive-threshold LIF

`ALIF(n_channels, theta_0=1.0, delta_a=0.5, tau_a=0.1, tau_m=0.02, gain=1.0, refractory=0.0)`

RATE_PARAM `"theta_0"`, RATE_DIRECTION `-1`, DRIVE_KIND `"envelope"`.

Equations (22)–(23) with (12)–(13) otherwise unchanged. **With `delta_a == 0`
this must be bit-identical to `LIF` at the same `theta_0`, `tau_m`, `gain` and
`refractory`.** Share the implementation rather than duplicating it. State
keys: `"v"`, `"threshold"`.

The refractory rule of §4.2 applies unchanged, including the requirement that
`refractory == 0.0` for comparison runs.

### 4.6 E5 — Phase-locked

`PhaseLocked(n_channels, threshold=0.05, gamma=1.0, f_lock=1500.0, refractory=0.001, mode="deterministic", centre_frequencies=None)`

RATE_PARAM `"threshold"`, RATE_DIRECTION `-1`, DRIVE_KIND `"subband"`.

`mode="deterministic"`: emit at each upward zero crossing of the subband
waveform where the envelope exceeds `threshold`, subject to `refractory`.
`mode="poisson"`: inhomogeneous Poisson with intensity from equation (25);
requires `seed`.

Channels whose centre frequency exceeds `f_lock` revert to envelope-driven LIF
behaviour. When called through `encode_from_drive`, centre frequencies come from
the `centre_frequencies` constructor argument; if `None`, all channels are
treated as below cutoff.

### 4.7 E6 — Time-to-first-spike

`TTFS(n_channels, e_min=1e-6, frame=0.025, hop=0.010, tau_m=0.02, theta=1.0, mode="log")`

RATE_PARAM `"e_min"`, RATE_DIRECTION `-1`, DRIVE_KIND `"envelope"`.

`mode="log"` uses equation (28); `mode="lif"` uses equation (29). At most one
event per channel per frame. Frame energy is the sum of squared drive samples
within the frame — computed on whatever drive is supplied, with no further
transformation, so that a test can reproduce it independently. Frame `m` covers `[m·hop, m·hop + frame)`, and the
number of frames is `floor((n_samples·dt − frame)/hop) + 1`.

---

## 5. Featurisation — `spikeenc.features`

```python
featurise(train: SpikeTrain, tau: float = 0.005, hop: float = 0.010,
          split_polarity: bool = True) -> np.ndarray
```

Equation (32): exponential kernel, sampled at `hop`. Returns shape
`(n_frames, n_channels)` if `split_polarity` is False, or
`(n_frames, 2 * n_channels)` if True, with ON channels first then OFF.
`n_frames = floor(duration / hop) + 1`; frame `k` samples at `t = k · hop`.

Must be invariant to the order in which events appear in the arrays.

---

## 6. Metrics — `spikeenc.metrics`

```python
event_rate(train) -> float                    # Λ, eq (35)
rate_per_channel(train) -> float              # R, eq (34)
bandwidth_bps(train, timestamp_bits=20, polarity_bits=1) -> float   # eq (36)
vector_strength(times: np.ndarray, frequency: float) -> float       # eq (26)
decoded_information(confusion: np.ndarray) -> float                 # eq (38), bits
```

`vector_strength` returns 0.0 for fewer than two events.

---

## 7. Corruption operators — `spikeenc.corrupt`

Used by preliminary experiment P2 and by the E5 jitter test.

```python
jitter(train, sigma: float, rng) -> SpikeTrain
channel_shift(train, delta: int) -> SpikeTrain
delete(train, p: float, rng) -> SpikeTrain
randomise_times(train, rng) -> SpikeTrain
```

- `jitter` perturbs each time by N(0, σ²), preserves event count, re-sorts into
  canonical order, and clips times into `[0, duration]`.
- `channel_shift` adds `delta` to every channel index and **drops** events
  falling outside `[0, n_channels)`; it does not wrap.
- `delete` retains each event independently with probability `1 − p`.
- `randomise_times` resamples times uniformly in `[0, duration]` while
  preserving each channel's event count.

---

## 8. What is deliberately unspecified

Internal data structures, vectorisation strategy, whether the filterbank is FIR
or IIR, choice of ODE solver, file formats for intermediate results. Optimise
these freely — the contract above is the only part the tests depend on.
