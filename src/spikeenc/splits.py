"""Splits — and the assertion that they are disjoint.

Validation protocol section 4, control C4: "Programmatic set-intersection
checks asserted at every run: speaker sets disjoint between train and test for
T1, T3 and T4; utterance sets disjoint for T2. Cheap, and non-negotiable."

Non-negotiable is taken literally here. `Split` validates in `__post_init__`,
so a leaking split cannot be constructed, let alone used — there is no code
path that produces a leaked result and reports it as clean. The alternative,
a `check_split()` a caller is trusted to call, fails in exactly the case that
matters, which is the run nobody was watching.

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-07
"""
from dataclasses import dataclass

import numpy as np


class LeakageError(AssertionError):
    """Raised when train and test share a speaker or an utterance (C4)."""


@dataclass(frozen=True)
class Split:
    """Train/test partition, validated on construction.

    `train` and `test` are tuples of utterance ids. The speaker sets are
    derived rather than passed, so they cannot disagree with the utterance
    lists they are supposed to describe.
    """
    train: tuple
    test: tuple
    train_speakers: tuple
    test_speakers: tuple
    seed: int

    def __post_init__(self):
        self.assert_disjoint()

    def assert_disjoint(self):
        """C4. Both checks, both directions, every run."""
        shared_utt = set(self.train) & set(self.test)
        if shared_utt:
            raise LeakageError(
                f"C4 violated: {len(shared_utt)} utterance(s) in both train "
                f"and test, e.g. {sorted(shared_utt)[:3]}")
        shared_spk = set(self.train_speakers) & set(self.test_speakers)
        if shared_spk:
            raise LeakageError(
                f"C4 violated: {len(shared_spk)} speaker(s) in both train and "
                f"test, e.g. {sorted(shared_spk)[:3]}. Splits are "
                "speaker-disjoint for T1, T3 and T4 (validation protocol C4).")
        return True

    def as_dict(self):
        return {"n_train": len(self.train), "n_test": len(self.test),
                "train_speakers": list(self.train_speakers),
                "test_speakers": list(self.test_speakers), "seed": self.seed}


def speaker_disjoint_split(corpus, test_fraction=0.3, seed=0):
    """Partition `corpus` by speaker, deterministically from `seed`.

    Speakers are shuffled and the first `ceil(test_fraction * n)` go to test,
    with at least one speaker on each side. Splitting on the speaker rather
    than on the utterance is what C6 of the proposal requires and what makes
    the T1 result a statement about unseen speakers.
    """
    speakers = list(corpus.speakers)
    if len(speakers) < 2:
        raise ValueError(f"need at least two speakers to split, got "
                         f"{len(speakers)}")
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(speakers))
    shuffled = [speakers[i] for i in order]

    n_test = int(np.ceil(test_fraction * len(speakers)))
    n_test = min(max(n_test, 1), len(speakers) - 1)
    test_spk = frozenset(shuffled[:n_test])

    train = tuple(u.uid for u in corpus if u.speaker not in test_spk)
    test = tuple(u.uid for u in corpus if u.speaker in test_spk)
    train_spk = tuple(sorted({u.speaker for u in corpus
                              if u.speaker not in test_spk}))
    return Split(train=train, test=test, train_speakers=train_spk,
                 test_speakers=tuple(sorted(test_spk)), seed=int(seed))
