"""The probe harness — corpus in, scored operating point out, controls run.

This is the weeks 1-2 infrastructure of proposal section 9: the path from a
body of audio through the front end, an encoder, the featurisation of equation
(32) and a probe, to an accuracy and a budget. Everything above it in the
schedule — P1, P2, the week 8 screen, the full sweep — is this loop called
repeatedly with different arguments.

**The Layer 2 controls run as part of a run, not as a separate script.**
Validation protocol section 4 lists them as things to do; a control that has to
be remembered is a control that will one day be forgotten, and the run it is
forgotten on is by construction the one nobody was watching. C4 is enforced in
`splits.Split`, which cannot be constructed leaking; C2, C3 and C5 are computed
by `run_t1` on every call and returned beside the headline number. There is no
argument to switch them off.

What is not here, and why:

- **The nonlinear probe** of proposal 6.2, and therefore the accessibility gap
  of equation (33). It needs a tensor library this box does not have.
- **T2 and T3.** Both need decisions not yet taken; see `tasks.py`.
- **C1**, the upper-bound anchor. It is a statement about TIMIT (82.68 per cent
  frame accuracy, Ponghiran and Roy) and cannot be checked against a synthetic
  stand-in. Until the licence question O2 is resolved, a number from this
  harness says the pipeline is self-consistent, not that it is calibrated.
- **C7**, round-trip integrity, and the strong form of **C6**. Both are
  statements about the released event file format, which does not exist and
  cannot be written before Q07 settles whether ON and OFF are separate channel
  indices or a polarity field.

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-07
"""
import time

import numpy as np

from . import encoders as _encoders
from . import metrics
from .features import featurise
from .frontend import Filterbank
from .probes import LinearProbe
from .splits import speaker_disjoint_split
from .tasks import (UNLABELLED, LabelSet, frame_labels, majority_floor,
                    shift_labels, stack_context)


def encoder_class(name):
    """Look an encoder up by its declared NAME, so configs name "E1" and not a
    Python path. The registry is derived from the module rather than written
    out, which keeps it from drifting as encoders are added."""
    table = {cls.NAME: cls for cls in vars(_encoders).values()
             if isinstance(cls, type) and issubclass(cls, _encoders.Encoder)
             and cls is not _encoders.Encoder}
    if name not in table:
        raise KeyError(f"unknown encoder {name!r}; known: {sorted(table)}")
    return table[name]


def compute_drive(utterance, n_channels, front_end, drive_kind):
    """The common front end of proposal 5.0, exactly as `Encoder.encode` does it.

    Separated out because the drive is the expensive part and does not depend
    on the rate parameter: a six-point sweep over one utterance computes the
    filterbank once, not six times.
    """
    fb = Filterbank(n_channels, sample_rate=utterance.sample_rate,
                    f_min=front_end.get("f_min", 50.0),
                    f_max=front_end.get("f_max", 8000.0),
                    spacing=front_end.get("spacing", "erb"),
                    compensate_group_delay=front_end.get(
                        "compensate_group_delay", False))
    if drive_kind == "subband":
        return fb.subbands(utterance.audio)
    env = fb.envelope(utterance.audio,
                      method=front_end.get("envelope", "hilbert"))
    return fb.compress(env, method=front_end.get("compression", "log"),
                       epsilon=front_end.get("epsilon", 1e-8),
                       exponent=front_end.get("exponent", 0.3))


def encode_corpus(corpus, encoder_name, rate_values, n_channels, front_end,
                  encoder_params=None, seed=None):
    """Encode every utterance at every rate-parameter value.

    Returns `{rate_value: {uid: SpikeTrain}}`. The loop is utterance-outer and
    rate-inner so each drive is computed once; at 700 channels the drive for a
    single utterance is tens of megabytes and holding the whole corpus in
    memory to sweep over it would not fit.
    """
    cls = encoder_class(encoder_name)
    params = dict(encoder_params or {})
    out = {float(v): {} for v in rate_values}

    for utt in corpus:
        drive = compute_drive(utt, n_channels, front_end, cls.DRIVE_KIND)
        dt = 1.0 / utt.sample_rate
        for v in rate_values:
            enc = cls(n_channels, **{cls.RATE_PARAM: v}, **params)
            out[float(v)][utt.uid] = enc.encode_from_drive(drive, dt, seed=seed)
    return out


def corpus_event_rate(trains, corpus):
    """Corpus-level Lambda, equation (35): total events over total duration."""
    total_events = sum(len(t) for t in trains.values())
    return total_events / corpus.total_duration


def calibrate_rate_param(corpus, encoder_name, target_lambda, n_channels,
                         front_end, encoder_params=None, bracket=(1e-4, 1e4),
                         tol=0.02, max_iter=40, seed=None):
    """Find the rate-parameter value giving total event rate `target_lambda`.

    Needed because a rate parameter's useful range depends on the scale of the
    drive, and the drive's scale depends on the compression: under
    `log(e + eps)` compression an ordinary audio envelope is negative
    everywhere, and E1 at the SPEC default `theta = 1.0` emits **no events at
    all**. The SPEC defaults are calibrated to the known-answer suite's
    synthetic drives, which is right for the suite and wrong for audio, so a
    sweep specified as parameter values would be a sweep over an arbitrary and
    encoder-dependent range. Proposal 6.4 asks for a sweep in Lambda; this is
    what makes one expressible.

    Bisection in log space on the bracket, oriented by the encoder's declared
    RATE_DIRECTION. Returns `(value, achieved_lambda, n_iter)`.
    """
    cls = encoder_class(encoder_name)
    drives = [(compute_drive(u, n_channels, front_end, cls.DRIVE_KIND),
               1.0 / u.sample_rate) for u in corpus]
    duration = corpus.total_duration
    params = dict(encoder_params or {})

    def lam(value):
        n = 0
        for drive, dt in drives:
            enc = cls(n_channels, **{cls.RATE_PARAM: value}, **params)
            n += len(enc.encode_from_drive(drive, dt, seed=seed))
        return n / duration

    lo, hi = float(bracket[0]), float(bracket[1])
    # RATE_DIRECTION = -1 means a larger parameter gives a lower rate, so the
    # bracket is oriented low-rate-first either way and the same bisection runs.
    if cls.RATE_DIRECTION < 0:
        lo, hi = hi, lo

    lam_lo, lam_hi = lam(lo), lam(hi)
    if not (min(lam_lo, lam_hi) <= target_lambda <= max(lam_lo, lam_hi)):
        raise ValueError(
            f"target Lambda {target_lambda:g} is outside the reachable range "
            f"[{min(lam_lo, lam_hi):g}, {max(lam_lo, lam_hi):g}] for "
            f"{encoder_name}.{cls.RATE_PARAM} over bracket {bracket}")

    for i in range(1, max_iter + 1):
        mid = float(np.exp(0.5 * (np.log(abs(lo)) + np.log(abs(hi)))))
        lam_mid = lam(mid)
        if abs(lam_mid - target_lambda) <= tol * target_lambda:
            return mid, lam_mid, i
        if (lam_mid < target_lambda) == (lam_lo < target_lambda):
            lo, lam_lo = mid, lam_mid
        else:
            hi, lam_hi = mid, lam_mid
    return mid, lam_mid, max_iter


def build_dataset(trains, corpus, labelset, tau, hop, context):
    """Featurise every utterance and pair each frame with its T1 label.

    Returns `(X, y, uid_of_frame)`. Frame `k` of an utterance takes the label
    of the segment containing `t = k * hop`, which is the instant SPEC section
    5 says that frame samples — features and targets are on one grid by
    construction, and control C5 checks that the construction is right.
    """
    xs, ys, uids = [], [], []
    for utt in corpus:
        f = featurise(trains[utt.uid], tau=tau, hop=hop, split_polarity=True)
        y = frame_labels(utt, hop, labelset, n_frames=f.shape[0])
        xs.append(stack_context(f, context))
        ys.append(y)
        uids.append(np.full(len(y), utt.uid, dtype=object))
    return (np.concatenate(xs), np.concatenate(ys), np.concatenate(uids))


def budget_cross_check(trains):
    """C6, in the form available before the release file format exists.

    Two independent paths to the same total: the length of the event arrays,
    and the sum of the per-channel histogram. They share the container and not
    the counting, so this catches a channel index out of range or an event
    dropped in canonical ordering — but it is *not* the control the protocol
    asks for, which counts rows in the written file. That one waits on the
    format, and the format waits on Q07. Returned so a reader can see which
    version was run.
    """
    by_len = sum(len(t) for t in trains.values())
    by_channel = sum(int(t.counts_per_channel().sum()) for t in trains.values())
    return {"events_by_array_length": by_len,
            "events_by_channel_histogram": by_channel,
            "agree": by_len == by_channel,
            "form": "in-memory (weak): the file-format cross-check of C6 "
                    "needs the release format, which is blocked on Q07"}


def run_t1(corpus, trains, *, labelset=None, tau=0.005, hop=0.010, context=0,
           test_fraction=0.3, seed=0, alpha=1e-4, control_offsets=(-1, 1)):
    """Score one operating point on T1, and run the Layer 2 controls with it.

    Returns a dict of everything the manifest should carry for this point:
    the headline accuracy, both C2 floors, the C3 shuffled-label control, the
    C5 misalignment controls, the C6 cross-check, the C4 split description, the
    budget of equations (34)-(36), and the decoded information of equation (38).
    """
    labelset = labelset or LabelSet(corpus.labels)
    t0 = time.time()

    x, y, uid = build_dataset(trains, corpus, labelset, tau, hop, context)
    split = speaker_disjoint_split(corpus, test_fraction=test_fraction,
                                   seed=seed)
    train_mask = np.isin(uid, np.asarray(split.train, dtype=object))
    test_mask = np.isin(uid, np.asarray(split.test, dtype=object))

    def fit_score(y_all):
        probe = LinearProbe(len(labelset), alpha=alpha).fit(
            x[train_mask], y_all[train_mask])
        return probe, probe.score(x[test_mask], y_all[test_mask])

    probe, accuracy = fit_score(y)

    # C3 — shuffled-label control. Training labels are permuted, the probe
    # refitted, and test performance must return to the floor. This is the
    # primary detector of leakage: if a speaker or an utterance is on both
    # sides of the split, a probe can still score above the floor here.
    rng = np.random.default_rng(seed + 991)
    y_shuffled = y.copy()
    idx = np.flatnonzero(train_mask & (y != UNLABELLED))
    y_shuffled[idx] = y[rng.permutation(idx)]
    _, shuffled_accuracy = fit_score(y_shuffled)

    # C5 — deliberate misalignment. Labels are offset against features and the
    # probe refitted, so what is measured is whether the alignment carries
    # information, not merely whether shifted labels score worse at test time.
    misaligned = {}
    for k in control_offsets:
        y_k = np.concatenate([
            shift_labels(y[uid == u.uid], k) for u in corpus])
        misaligned[str(k)] = fit_score(y_k)[1]

    floor = majority_floor(y[test_mask])
    confusion = probe.confusion(x[test_mask], y[test_mask])
    lam = corpus_event_rate(trains, corpus)
    n_ch = next(iter(trains.values())).n_channels
    # Equation (39) divides the decoded information by the mean number of
    # events per classified unit. The information comes from the test-set
    # confusion matrix, so the event count must come from the test set too;
    # taking it over the whole corpus would mix the two sides of the split.
    test_events = sum(len(trains[u]) for u in split.test)
    n_test_frames = max(1, int(np.sum(test_mask & (y != UNLABELLED))))
    mean_events_per_frame = test_events / n_test_frames

    return {
        "accuracy": accuracy,
        "majority_floor": floor,                      # C2
        "chance": labelset.chance,                    # C2
        "shuffled_label_accuracy": shuffled_accuracy,  # C3
        "misaligned_accuracy": misaligned,            # C5
        "budget_cross_check": budget_cross_check(trains),  # C6
        "split": split.as_dict(),                     # C4
        "lambda_events_per_s": lam,                   # eq (35)
        "rate_per_channel": lam / n_ch,               # eq (34)
        "bandwidth_bps": lam * (np.log2(n_ch) + 20 + 1),  # eq (36)
        "decoded_information_bits": metrics.decoded_information(confusion),
        "bits_per_event": (metrics.decoded_information(confusion)
                           / mean_events_per_frame
                           if mean_events_per_frame > 0 else 0.0),
        "confusion": confusion.tolist(),
        "n_frames_train": int(np.sum(train_mask & (y != UNLABELLED))),
        "n_frames_test": int(np.sum(test_mask & (y != UNLABELLED))),
        "n_features": int(x.shape[1]),
        "probe_settings": probe.settings,             # C4 fairness
        "probe_converged": probe.converged_,
        "probe_iterations": probe.n_iter_,
        "featurisation": {"tau": tau, "hop": hop, "context": context},
        "seconds": time.time() - t0,
    }
