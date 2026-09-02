"""Metrics stub — SPEC.md section 6, proposal equations (26), (34)-(38)."""
import numpy as np


def event_rate(train):
    raise NotImplementedError("equation (35)")


def rate_per_channel(train):
    raise NotImplementedError("equation (34)")


def bandwidth_bps(train, timestamp_bits=20, polarity_bits=1):
    raise NotImplementedError("equation (36)")


def vector_strength(times, frequency):
    raise NotImplementedError("equation (26); return 0.0 for fewer than 2 events")


def decoded_information(confusion):
    raise NotImplementedError("equation (38), in bits")
