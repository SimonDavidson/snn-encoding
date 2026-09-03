# Patch: Q06 answered — E3 event rule, and three things found alongside it

Answers Q06 and unblocks E3. Raises Q07, which blocks nothing.

**What changed and why.** Equation (21) was written as a level condition, the
prose introducing it said "threshold crossings", and all four T3 tests passed
under either reading. The implementation session's analysis was right and its
recommendation is adopted: E3's event rule is the reference-lattice rule of
SPEC §4.3 applied to `d` instead of to the drive. D26.

The choice is more forced than the Q06 write-up claims. Any rule emitting at
most one event per crossing has an event count bounded above by the number of
excursions of `d`, which is a property of the drive and of the time constants
rather than of `theta`, so the count saturates as `theta` falls instead of
growing. That disqualifies the whole crossing family at once, not just the two
members measured. The full argument is in the Q06 answer.

Three things came out of answering it:

- **G3 was the wrong shape.** It asserted monotonicity, which is necessary,
  when §6.4 needs dynamic range, which is sufficient. One rejected candidate
  gave 52, 52, 52, 35, 0 — monotonic, and useless. G3 now also requires a 4x
  span. D27.
- **The discretisation never reached SPEC.** Proposal §5.3 states
  `alpha = exp(-dt/tau)`, but SPEC cites equations by number and does not
  reproduce them, so the convention was absent from the only document a Layer 3
  reimplementation works from. Restated in SPEC §1. D28.
- **T3.1's rationale was false, as flagged.** Docstring corrected, and the fact
  it depended on — E2's silence on a constant drive — now has its own
  assertion, since nothing pinned it. D29.

## Files in this patch

| File | Change |
|---|---|
| `SPEC.md` | §1 discretisation convention; §4.4 rewritten with the event rule |
| `docs/proposal_v2.md` | §5.3: equation (21) rewritten, rationale and cost stated, Δ~ref~ clarified |
| `tests/test_known_answers.py` | G3 span assertion; new `test_T3_5`, new `test_T2_6`; `test_T3_1` docstring and T3 block header corrected |
| `DECISIONS.md` | D26–D29 |
| `QUESTIONS.md` | Q06 answered; Q07 raised (non-blocking) |
| `NOTEBOOK.md` | design entry |
| `CLAUDE.md` | two file-discipline conventions, after the stale-entry incident |

## Apply

From the repository root:

    tar xzf q06_patch.tar.gz

`SPEC.md`, `tests/test_known_answers.py` and `tests/conftest.py` are guarded by
CI, so the commit message must contain `[spec]`. `conftest.py` is unchanged;
`step_drive` was already there and `test_T3_5` uses it as-is.

## Expected result

`test_T2_6` should pass immediately against the existing E2 — if it does not,
the reference is not being initialised to `drive[:, 0]` and that is a real
finding, not a test to adjust. `test_T3_5` fails until D26 is implemented.
G3 should be unaffected for E1 and E2, which span roughly 16x.

## Read `test_T3_5`'s docstring before running it

Its expected values are derived from the closed-form step response, not from
any implementation. Three things in it look like bugs and are not:

- **4 ON but only 3 OFF.** On the decay `d` approaches zero from above, so
  `|d - 0.2|` approaches `theta` from below and never reaches it; the run stops
  at `m = 1`. This is the "first index within `theta`, not the nearest" rule of
  SPEC §4.3 — the same asymmetry Q04 identified for E2 — and checking it is
  part of the point.
- **The 0.30 s duration is load-bearing.** The `1e-9` tolerance does admit that
  fourth OFF event once `d` falls below 2e-10, roughly 1.12 s after the step.
  Lengthening the signal changes the correct answer to 4 and 4. Do not extend
  it.
- **The peak tolerance is 1e-4, which is tight on purpose.** An Euler pole
  reads 0.9070919 against the correct 0.9048007, and that assertion is how D28
  gets enforced rather than merely stated.

If it fails, the assertion messages name the likely cause.

## Next

E3 under D26 until T3.1–T3.5 pass, then E4 until T4.1–T4.4, with E4 wrapping
`_integrate_and_fire` as before. D24 and the `features`/`corrupt` stubs remain
unblocked and independent of this patch.

One thing to expect rather than be surprised by: G3 may fail for E6 when it is
implemented, if time-to-first-spike emits one spike per channel per frame and
its event count is therefore structurally fixed. That would be a real result —
matched budgets for E6 would have to come from channel count or frame rate —
and it should be raised in `QUESTIONS.md`, not accommodated by relaxing the
threshold.
