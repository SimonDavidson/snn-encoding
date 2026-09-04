# Patch: Q08 answered, `test_T3_6` added, SPEC 4.4 guard ratified

Review of E3 at 6d69374. Nothing here blocks E4; apply it and start.

## What changed

**Q08 — both corrections accepted, both errors were the design session's.**
D33. The continuous peak is 0.9048013, not 0.9048124; the error came from
rounding the two exponentials to seven digits before subtracting them, which is
the arithmetic the closed form exists to avoid. The residual at 0.30 s is
6.738e-3 = `exp(-5)`, not 2.5e-3; the diagnosis in Q08 is right, the sentence
was written against time after the step and the parameter against total
duration. A third that went unreported: `t*` is 3.99186 ms, written as 3.9918 by
truncating instead of rounding — the 3.9919 in Q08 is right.

No assertion changes. The corrected docstring now records that those values were
once wrong, rather than quietly reading correctly, because they exist to be
hand-checked and a reader is entitled to know they failed that check once.

**`test_T3_6` added.** D31. E3 at `theta = C` must emit exactly the events E2
emits at `C` when handed E3's own `d`. This is an identity in the equations: E2
anchors its lattice at its input's first sample, `d[:, 0]` is zero by the SPEC
4.4 initialisation, and zero is E3's anchor. D30 makes it true by construction,
which is the right structure — this is what keeps it true if that structure ever
changes, since two separate loops would each go on passing their own block while
drifting apart and D26's single-factor contrast would stop holding with nothing
noticing.

**SPEC 4.4 now requires the `tau_slow <= tau_fast` raise.** D32. The guard was
a good addition and correctly within implementation remit, but a Layer 3
reimplementation works from SPEC alone and would not have it. Note that
`test_T3_4` does not catch an inverted pair: it checks that negating the drive
swaps the polarities, which an already-swapped encoder satisfies.

## Read before running: `test_T3_6` was written after sight of the code

Unlike everything else in `tests/test_known_answers.py`, `test_T3_6` was written
by a design session that had read `src/spikeenc/encoders.py`. It is derived from
equations (20)-(21) and SPEC 4.3, and as far as its author could tell nothing in
it came from the implementation — but that is exactly the assurance the no-sight
rule exists to avoid needing to accept.

The file header has been qualified rather than left as an approximation, the
test's own docstring says so, and NOTEBOOK records it. Weigh `test_T3_6` as
weaker independent evidence than its neighbours. The alternative was to withhold
the test to protect the appearance of the discipline at the cost of its
substance.

## Files

| File | Change |
|---|---|
| `tests/test_known_answers.py` | header qualified; `test_T3_5` docstring corrected; `test_T3_6` added |
| `SPEC.md` | 4.4 required raise |
| `QUESTIONS.md` | Q08 answered |
| `DECISIONS.md` | D31-D33 |
| `NOTEBOOK.md` | design entry, including the review notes |

## Apply

From the repository root:

    tar xzf q08_patch.tar.gz

`SPEC.md` and `tests/test_known_answers.py` are behind the CI guard, so the
commit message needs `[spec]`.

## Expected result

`test_T3_6` should pass immediately against 6d69374, since D30 makes it true by
construction. If it fails, the two encoders have already diverged and that is
the finding, not a test to adjust. The three docstring corrections change no
assertion, so the counts should go from 43/40/1 to 44/40/1.

## Notes from the review, for context rather than action

The lattice arithmetic was traced by hand against the T3.5 case rather than
inferred from the green test. Truncation toward zero is the correct rounding —
`floor` would overshoot on the OFF side and leave a residual of the wrong sign —
and applying the tolerance as `sign(step) * tol` widens the emit condition
symmetrically rather than biasing one polarity. The filter initialisation is
right in a way that is easy to get subtly wrong: setting `y` to `u[:, 0]` and
then updating at `i = 0` gives `y[0] == u[0]` exactly. Initialising to zero and
starting at `i = 0`, or initialising to `u[0]` and starting at `i = 1`, both look
reasonable and both shift the step response by a sample.

D30 is endorsed, and the usual objection to sharing an implementation between
two things being compared does not apply. It runs the other way here: T2 and T3
are now two independent known-answer blocks aimed at the same routine, so a bug
in the lattice rule has more chances of being caught, not fewer.

## Next

E4 `ALIF`, wrapping `_integrate_and_fire` so T4.1's `delta_a == 0` reduction
holds by construction. D24 and the `features`/`corrupt` stubs remain unblocked
and independent.

E3's Layer 1 is complete. Its Layer 2 and Layer 3 are not, `G8[E3]` is still red
on the `features` stub, and D24 is unimplemented — which matters to E3
specifically, since it sits on the envelope path where the group delay is
largest. E3 is not finished, only its known-answer block is.
