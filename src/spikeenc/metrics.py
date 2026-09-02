"""Metrics — SPEC.md section 6, proposal equations (26), (34)-(38).

Author:        Simon Davidson & Claude
Created:       2026-09-02
Last modified: 2026-09-02
"""
import numpy as np


def event_rate(train) -> float:
    """Total event rate Lambda, equation (35).

        Lambda = N_events / D

    Events per second, summed over all channels. This is the primary budget
    variable for the matched-budget comparison of proposal section 6.4.
    """
    if train.duration <= 0.0:
        return 0.0
    return float(len(train)) / float(train.duration)


def rate_per_channel(train) -> float:
    """Mean per-channel event rate R, equation (34).

        R = N_events / (N_ch * D)

    Events per second per channel.
    """
    if train.duration <= 0.0 or train.n_channels <= 0:
        return 0.0
    return float(len(train)) / (float(train.n_channels) * float(train.duration))


def bandwidth_bps(train, timestamp_bits=20, polarity_bits=1) -> float:
    """Event-stream bandwidth B, equation (36).

        B = Lambda * (log2(N_ch) + b_t + b_p)   bits per second

    The channel field costs log2(N_ch) bits; b_t and b_p are the declared
    timestamp and polarity widths. A single-channel train needs no channel
    field, and log2(1) = 0 gives that for free.
    """
    if train.n_channels <= 0:
        return 0.0
    channel_bits = np.log2(train.n_channels)
    return event_rate(train) * (float(channel_bits) + float(timestamp_bits)
                                + float(polarity_bits))


def vector_strength(times, frequency) -> float:
    """Vector strength VS, equation (26).

        VS = (1/N) * | sum_k exp(j * 2*pi*f * t_k) |

    One for events perfectly locked to a fixed phase of f, tending to zero for
    events uniformly distributed in phase. SPEC section 6: fewer than two
    events returns 0.0, since the statistic is degenerate there (a single event
    always scores 1.0 and would read as perfect locking).
    """
    t = np.asarray(times, dtype=np.float64)
    if t.size < 2:
        return 0.0
    phase = 2.0 * np.pi * float(frequency) * t
    return float(np.abs(np.sum(np.exp(1j * phase))) / t.size)


def decoded_information(confusion) -> float:
    """Decoded information I(Y ; Y_hat) in bits, equation (38).

        I = sum_{y, yhat} p(y, yhat) * log2[ p(y, yhat) / (p(y) p(yhat)) ]

    `confusion` holds counts (or any non-negative weights) with true labels on
    rows and predicted labels on columns; it is normalised here to the joint
    distribution. Zero-probability cells contribute nothing, which is the
    standard 0*log(0) = 0 convention and not a numerical fudge.

    By the data processing inequality this lower-bounds the information the
    encoding carries about the task. Perfect classification of C equiprobable
    classes gives log2(C); chance-level prediction gives 0.
    """
    counts = np.asarray(confusion, dtype=np.float64)
    total = counts.sum()
    if total <= 0.0:
        return 0.0

    joint = counts / total
    p_true = joint.sum(axis=1, keepdims=True)        # p(y)
    p_pred = joint.sum(axis=0, keepdims=True)        # p(yhat)
    outer = p_true * p_pred

    nz = joint > 0.0
    return float(np.sum(joint[nz] * np.log2(joint[nz] / outer[nz])))
