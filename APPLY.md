# Patch: Q09-Q16 answered, Q03 corrected, P-01 amendment drafted

Eight questions, D38-D46. Unblocks E5 and E6. Nothing left open except Q07,
which is with Oliver and blocks nothing until packaging.

## Read first: two things are not settled by this patch

**`P-01a` is drafted and is NOT live.** `PREDICTIONS.md` carries it with a
`PENDING SIGN-OFF` marker that only Simon removes. Do not treat it as a
pre-registered prediction, and do not choose an E4 sweep range from it, until
that marker is gone.

**`test_G3[E5]`'s span is a prediction, not a measurement.** `cycle_divisor`
was specified without an environment to run it in. If the standard sweep comes
in under 4x, that is a finding to raise as a question, not a threshold to relax
— exactly as with `threshold` before it.

## The answers

**Q09** — softened, and it makes an earlier decision better than its stated
reason. D38. SPEC 4.4 carried the same "same number" claim and gets the same
correction. Anchoring E3's lattice at exactly zero was justified aesthetically
in D26; your measurement makes it substantive.

**Q10** — none of the four options. D39. The first-spike latency after silence
is adaptation-free by construction (`a = 0` at the step), so measuring onset
emphasis against it rather than against the first ISI gives a monotone
quantity. The new content is asserting that the latency is *invariant* and
equals the closed form, which nothing else in the suite does and which is what
pins D34.

**Q11** — a fifth option. D40. `RATE_PARAM` becomes `cycle_divisor`: keep every
k-th gated crossing. Option 1 was rejected because a Poisson process cannot
satisfy `test_G4`'s exact shift-equivariance, which trades one broken gate for
another; option 4 because reaching low budgets by cutting channels removes
frequency resolution at the same time, confounding the one thing E5 is in the
battery to test. `lambda_max` and `z_0` are added so the Poisson mode is
coherent, but it is excluded from 6.4, G3 and G4.

**Q12** — rectify-and-lowpass, not Hilbert, on causality grounds. D41. The
fallback above `f_lock` is an `LIF` instance so the reversion becomes a
testable identity rather than three named constants.

**Q13** — a fifth option, chosen over option 1. D42. Mean retained fraction
over twenty seeds. It tests the rate the test is named for; lengthening the
drive only makes a single draw more reliable.

**Q14** — option 2. D43. `e_frac`, gating at `e_frac * E_max`, registry point
0.20. Two things the question did not pin down are now specified: `E_max` is
over *all channels and all frames*, and the resulting utterance-level
normalisation is a known asymmetry recorded in SPEC 4.7.

**Q15** — options 1 and 3. D45. Dated correction above the Q03 answer with the
original left visible, and a new section 8 of the validation protocol requiring
every reported figure to carry its metric definition.

**Q16** — D44, taken with D43. Making the gate relative resolves parts 1 and 2
and removes your clipping decision as a side effect: a strict gate puts every
offset strictly inside its frame by construction. Part 3 is mine and both tests
are rewritten onto the state matrices.

## Files

| File | Change |
|---|---|
| `SPEC.md` | 4.4 Q09 correction; 4.5 D34 restated; 4.6 rewritten (E5); 4.7 rewritten (E6) |
| `tests/test_known_answers.py` | `test_T4_3` replaced; `test_T6_1`, `test_T6_2`, `test_corrupt_delete_*` rewritten; G3 docstring corrected; `test_T6_3` argument renamed |
| `tests/conftest.py` | E5 and E6 registry operating points |
| `docs/proposal_v2.md` | 5.5 and 5.6 rate parameters |
| `docs/validation_protocol.md` | new section 8 |
| `PREDICTIONS.md` | P-01a drafted, pending sign-off |
| `QUESTIONS.md` | Q09-Q16 answered; Q03 correction appended |
| `DECISIONS.md` | D38-D46 |
| `NOTEBOOK.md` | design entry |

## Apply

From the repository root:

    tar xzf q09_q16_patch.tar.gz

`SPEC.md`, `tests/test_known_answers.py` and `tests/conftest.py` are behind the
CI guard, so the commit message needs `[spec]`.

## New API surface

Three additions, all of them contract rather than implementation choice:

- `PhaseLocked` gains `cycle_divisor`, `env_cutoff`, `lambda_max`, `z_0`.
- `TTFS` takes `e_frac` in place of `e_min`, and raises `ValueError` on
  `e_frac <= 0` in `mode="log"`.
- `TTFS.encode_from_drive(..., return_state=True)` must expose `"energy"` and
  `"offsets"`, both shape `(n_channels, n_frames)`, with `offsets` holding NaN
  where a channel did not fire. This is the one place the patch asks for more
  than a reading of the spec, and it is what lets `test_T6_1` and `test_T6_2`
  assert on frames rather than on unrecoverable time windows.

## Expected result

`test_T4_3` should go green once E4 is rerun; it needs no code change. Q10's own
table predicts the ratio column as 1.00, 2.73, 3.84, 5.69, 8.80, 13.57, and the
onset latency as 8.125 ms at every `delta_a`. If the latency moves with
`delta_a`, adaptation is being driven by something other than the spike train
and that is a real defect, not a tolerance to widen.

E5 and E6 are unblocked in full. The order that clears most is E5 first — the
whole T5 block plus its generic tests — then E6.

## One caution about E6

`test_T6_2` now asserts a Pearson correlation of exactly -1 between log energy
and offset within a frame. That is a tight assertion and it is deliberate: it
holds only if every channel shares the same `E_max` and `E_min`, so it is what
detects a per-channel normalisation. If it fails at around -0.9 rather than
-1.0, check the scope of `E_max` before checking anything else.
