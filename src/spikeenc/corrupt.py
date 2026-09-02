"""Corruption operators stub — SPEC.md section 7. Used by P2 and by test_T5_4."""
import numpy as np


def jitter(train, sigma, rng):
    raise NotImplementedError("Gaussian time perturbation; restore canonical order")


def channel_shift(train, delta):
    raise NotImplementedError("shift indices; drop out-of-range, do not wrap")


def delete(train, p, rng):
    raise NotImplementedError("retain each event with probability 1 - p")


def randomise_times(train, rng):
    raise NotImplementedError("resample times, preserve per-channel counts")
