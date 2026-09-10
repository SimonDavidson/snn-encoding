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
Last modified: 2026-09-08
"""
import time

import numpy as np

from . import encoders as _encoders
from . import metrics
from .features import featurise
from .frontend import Filterbank
from .probes import LinearProbe, RidgeProbe
from .boundaries import (DEFAULT_TOLERANCE, frame_auc, pick_peaks,
                         score_boundaries, uniform_baseline)
from .reference import feature_bandwidth_bps, mel_features
from .segments import (segment_counts, segment_table, segment_votes,
                       temporal_information_index)
from .selection import (fold_sizes, interior_maximum, predicted_offset,
                        profile_scores, select_on_folds, speaker_folds)
from .splits import speaker_disjoint_split
from .tasks import (SEMITONE_REF_HZ, UNLABELLED, LabelSet, boundary_labels,
                    f0_targets, frame_labels, majority_floor, shift_labels,
                    stack_context)


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

    **An encoder declaring `RATE_PARAM_INTEGER` is searched over integers
    instead**, and the rule for stopping is different in a way that matters.
    A continuous parameter can be driven to within `tol` of any reachable
    target; a discrete one cannot, because the achievable event rates are a
    countable set with gaps in it. The integer search therefore returns the
    **nearest achievable** rate rather than raising when no value is within
    `tol`, and the caller is expected to record the residual — `achieved` is
    returned for exactly that purpose. For E5 the gaps are roughly `1/k`
    relative, so they narrow as the divisor grows: wide at the sparse end of
    the sweep and a few per cent by `k = 16`. Whether a budget matched only to
    that precision satisfies proposal 6.4 is a question for the design session,
    not something this function can decide (Q44).
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

    if cls.RATE_PARAM_INTEGER:
        return _calibrate_integer(lam, cls, encoder_name, target_lambda,
                                  bracket)

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


def _calibrate_integer(lam, cls, encoder_name, target_lambda, bracket):
    """Integer search for `calibrate_rate_param`. See its docstring.

    Binary search on the integers in the bracket, then the nearest achievable
    of the two that bracket the target. Every evaluation is cached, because on
    a corpus each one re-encodes the whole thing and the search revisits
    endpoints.
    """
    lo = max(1, int(np.ceil(min(bracket))))
    hi = max(lo, int(np.floor(max(bracket))))
    if hi <= lo:
        raise ValueError(
            f"integer bracket for {encoder_name}.{cls.RATE_PARAM} collapses to "
            f"[{lo}, {hi}]; declare an integer bracket in the config, e.g. "
            "[1, 256]")

    seen = {}

    def at(k):
        if k not in seen:
            seen[k] = lam(k)
        return seen[k]

    lam_lo, lam_hi = at(lo), at(hi)
    if not (min(lam_lo, lam_hi) <= target_lambda <= max(lam_lo, lam_hi)):
        raise ValueError(
            f"target Lambda {target_lambda:g} is outside the reachable range "
            f"[{min(lam_lo, lam_hi):g}, {max(lam_lo, lam_hi):g}] for "
            f"{encoder_name}.{cls.RATE_PARAM} over integer bracket "
            f"[{lo}, {hi}]")

    a, b = lo, hi
    while b - a > 1:
        mid = (a + b) // 2
        lam_mid = at(mid)
        # `a` is kept on the same side of the target as `lam_lo` throughout,
        # so the invariant holds whichever way RATE_DIRECTION points.
        if (lam_mid < target_lambda) == (lam_lo < target_lambda):
            a = mid
        else:
            b = mid

    best = min(seen, key=lambda k: abs(seen[k] - target_lambda))
    return best, seen[best], len(seen)


def build_dataset(trains, corpus, labelset, tau, hop, context,
                  labels_only=False):
    """Featurise every utterance and pair each frame with its T1 label.

    Returns `(X, y, uid_of_frame)`. Frame `k` of an utterance takes the label
    of the segment containing `t = k * hop`, which is the instant SPEC section
    5 says that frame samples — features and targets are on one grid by
    construction, and control C5 checks that the construction is right.

    With `labels_only`, `X` comes back as None and `trains` is not read. That
    is for callers whose features come from somewhere other than an encoder —
    R2 — and which need the labels and the frame-to-utterance map on exactly
    the same grid.
    """
    xs, ys, uids = [], [], []
    for utt in corpus:
        n_frames = int(np.floor(utt.duration / hop)) + 1
        if not labels_only:
            f = featurise(trains[utt.uid], tau=tau, hop=hop,
                          split_polarity=True)
            n_frames = f.shape[0]
            xs.append(stack_context(f, context))
        y = frame_labels(utt, hop, labelset, n_frames=n_frames)
        ys.append(y)
        uids.append(np.full(len(y), utt.uid, dtype=object))
    x = None if labels_only else np.concatenate(xs)
    return (x, np.concatenate(ys), np.concatenate(uids))


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


def _uid_mask(uid, uids):
    """Boolean mask over rows whose utterance id is in `uids`."""
    return np.isin(uid, np.asarray(sorted(uids), dtype=object))


def predicted_alignment(front_end, n_channels, sample_rate, drive_kind, taus,
                        hop):
    """The label alignment offset the declared lags predict, before any fit.

    D69 makes the offset a swept axis; a swept axis with nothing to compare
    against is a fit. The front end declares its own lag under D24 — the
    filterbank group delay plus every declared stage in the envelope path — and
    the equation (32) kernel's first moment is `tau` exactly, so the offset
    that should win is computable from two quantities no probe has touched.
    Recorded beside the selected offset, which turns the sweep into a check on
    the two lags rather than a free parameter.

    The per-channel spread is reported as well as the mean, because it is
    large: at 32 ERB channels from 50 Hz the group delay runs 0.53 ms at the
    top of the bank to 15.57 ms at the bottom. A task living in the low
    channels — T2, which is about f0 — should align later than one spread over
    the whole bank, and the bracket says by how much.
    """
    fb = Filterbank(n_channels, sample_rate=sample_rate,
                    f_min=front_end.get("f_min", 50.0),
                    f_max=front_end.get("f_max", 8000.0),
                    spacing=front_end.get("spacing", "erb"),
                    compensate_group_delay=front_end.get(
                        "compensate_group_delay", False))
    lag = fb.declared_lag(drive_kind,
                          envelope=front_end.get("envelope", "hilbert"))
    taus = [taus] if np.isscalar(taus) else list(taus)
    return {
        "front_end_lag_s": {"mean": float(np.mean(lag)),
                            "median": float(np.median(lag)),
                            "min": float(np.min(lag)),
                            "max": float(np.max(lag))},
        "compensated": bool(front_end.get("compensate_group_delay", False)),
        "hop": hop,
        "by_tau": {f"{t}": {
            "lag_s": float(np.mean(lag) + t),
            "offset": predicted_offset(float(np.mean(lag)) + t, hop),
            "offset_low_channels": predicted_offset(float(np.max(lag)) + t,
                                                    hop),
            "offset_high_channels": predicted_offset(float(np.min(lag)) + t,
                                                     hop)} for t in taus},
    }


def score_t1(corpus, x, y, uid, *, labelset=None, test_fraction=0.3, seed=0,
             alpha=1e-4, offsets=(0,), n_folds=3, c5_radius=2,
             alignment_prediction=None):
    """Split, select the alignment, fit, and run the Layer 2 controls.

    Factored out of `run_t1` so that the spiking conditions and the R2
    reference of proposal 5.9 go through *one* decoder path rather than two
    that are meant to match. C4 requires identical decoding — "same probe
    architectures, same optimiser, schedule, regularisation and stopping
    criterion across all encoders" — and two copies could drift while each
    still looked right on its own. This is the argument D30 made for E2 and E3
    sharing one lattice rule, applied to the decoder.

    **The alignment offset is selected on speaker-disjoint folds inside the
    training split** (D69, D71), never on test, and the grid is recorded. The
    test-side profile is computed too and reported beside it, because the gap
    between the offset validation picks and the offset test would have picked
    is the size of the bias that selecting on test introduces — a quantity
    worth measuring once rather than assuming.

    Everything above the features is shared: the split, the probe, C2, C3, C5,
    and the confusion matrix feeding equation (38). What differs between a
    spiking condition and R2 is only what produced `x`.
    """
    labelset = labelset or LabelSet(corpus.labels)
    split = speaker_disjoint_split(corpus, test_fraction=test_fraction,
                                   seed=seed)
    train_mask = _uid_mask(uid, split.train)
    test_mask = _uid_mask(uid, split.test)
    speaker_of = {u.uid: u.speaker for u in corpus}
    folds = speaker_folds(split.train, speaker_of, n_folds=n_folds, seed=seed)

    offsets = tuple(int(o) for o in offsets)
    ys = {o: np.concatenate([shift_labels(y[uid == u.uid], o) for u in corpus])
          for o in offsets}

    def evaluate(offset, fit_uids, val_uids):
        y_o = ys[int(offset)]
        fit_rows, val_rows = _uid_mask(uid, fit_uids), _uid_mask(uid, val_uids)
        probe = LinearProbe(len(labelset), alpha=alpha).fit(x[fit_rows],
                                                            y_o[fit_rows])
        return probe.score(x[val_rows], y_o[val_rows])

    chosen, grid = select_on_folds(offsets, folds, evaluate, key=str)
    chosen = int(chosen)

    # The test-side profile: every offset refitted on the whole training split.
    # This is a diagnostic and never a selection — `chosen` is already fixed.
    probes, test_profile = {}, {}
    for o in offsets:
        p = LinearProbe(len(labelset), alpha=alpha).fit(x[train_mask],
                                                        ys[o][train_mask])
        probes[o] = p
        test_profile[str(o)] = p.score(x[test_mask], ys[o][test_mask])

    probe, y_sel = probes[chosen], ys[chosen]
    accuracy = test_profile[str(chosen)]

    # C3 — shuffled-label control. Training labels are permuted, the probe
    # refitted, and test performance must return to the floor. This is the
    # primary detector of leakage: if a speaker or an utterance is on both
    # sides of the split, a probe can still score above the floor here.
    rng = np.random.default_rng(seed + 991)
    y_shuffled = y_sel.copy()
    idx = np.flatnonzero(train_mask & (y_sel != UNLABELLED))
    y_shuffled[idx] = y_sel[rng.permutation(idx)]
    shuffled_accuracy = LinearProbe(len(labelset), alpha=alpha).fit(
        x[train_mask], y_shuffled[train_mask]).score(x[test_mask],
                                                     y_sel[test_mask])

    # C5 — deliberate misalignment, in the form D70 restates: an interior
    # maximum over at least two frames either side of the selected offset,
    # rather than a drop at plus or minus one. As written the old control
    # presumed zero was correct and would have been recorded as failed when
    # that presumption, rather than the alignment, was what had failed.
    val_profile = profile_scores(grid)
    c5 = interior_maximum(val_profile, chosen, radius=c5_radius)
    c5_test = interior_maximum(test_profile, chosen, radius=c5_radius)
    # Only offsets actually in the sweep: this key is a dict of numbers that
    # the report builder averages, and a None from an offset outside the grid
    # would propagate into a table rather than announce itself.
    misaligned = {str(chosen + d): test_profile[str(chosen + d)]
                  for d in range(-c5_radius, c5_radius + 1)
                  if d != 0 and str(chosen + d) in test_profile}

    test_best = max((k for k, v in test_profile.items() if v is not None),
                    key=lambda k: test_profile[k], default=str(chosen))
    confusion = probe.confusion(x[test_mask], y_sel[test_mask])
    return {
        "accuracy": accuracy,
        "majority_floor": majority_floor(y_sel[test_mask]),   # C2
        "chance": labelset.chance,                            # C2
        "shuffled_label_accuracy": shuffled_accuracy,         # C3
        "misaligned_accuracy": misaligned,                    # C5
        "c5_alignment": {"validation": c5, "test": c5_test},  # C5, D70
        "selection": {                                        # D71
            "parameters": ["offset"],
            "chosen": {"offset": chosen},
            "criterion": "frame accuracy",
            "selected_on": "speaker-disjoint folds within the training split",
            "n_folds": len(folds),
            "folds": fold_sizes(folds, speaker_of),
            "grid": grid,
            "candidates": list(offsets),
            "test_profile": test_profile,
            "test_argmax_offset": int(test_best),
            "test_score_at_selected": accuracy,
            "test_score_at_argmax": test_profile[test_best],
            "selection_bias": (None if accuracy is None
                               else test_profile[test_best] - accuracy),
            "predicted": alignment_prediction,
        },
        "best_offset": chosen,
        "split": split.as_dict(),                             # C4
        "decoded_information_bits": metrics.decoded_information(confusion),
        "confusion": confusion.tolist(),
        "n_frames_train": int(np.sum(train_mask & (y_sel != UNLABELLED))),
        "n_frames_test": int(np.sum(test_mask & (y_sel != UNLABELLED))),
        "n_features": int(x.shape[1]),
        "probe_settings": probe.settings,                     # C4 fairness
        "probe_converged": probe.converged_,
        "probe_iterations": probe.n_iter_,
        "_split": split,
        "_test_mask": test_mask,
        "_y": y_sel,
    }


def run_t1(corpus, trains, *, labelset=None, tau=0.005, hop=0.010, context=0,
           test_fraction=0.3, seed=0, alpha=1e-4, offsets=(0,), n_folds=3,
           c5_radius=2, alignment_prediction=None,
           timestamp_bits=20, polarity_bits=1):
    """Score one spiking operating point on T1, with its budget and controls.

    Returns a dict of everything the manifest should carry for this point:
    the headline accuracy at the selected alignment, both C2 floors, the C3
    shuffled-label control, the C5 interior-maximum control, the C6
    cross-check, the C4 split description, the budget of equations (34)-(36),
    and the decoded information of equation (38).

    `offsets` defaults to `(0,)` — the alignment pinned, as every recorded T1
    figure was taken. D72 keeps those figures as lower bounds rather than
    errors; passing a wider grid makes T1 sweep the axis D69 declares, on the
    same selection mechanism as T2, T3 and P1.
    """
    labelset = labelset or LabelSet(corpus.labels)
    t0 = time.time()

    x, y, uid = build_dataset(trains, corpus, labelset, tau, hop, context)
    out = score_t1(corpus, x, y, uid, labelset=labelset,
                   test_fraction=test_fraction, seed=seed, alpha=alpha,
                   offsets=offsets, n_folds=n_folds, c5_radius=c5_radius,
                   alignment_prediction=alignment_prediction)
    split, test_mask = out.pop("_split"), out.pop("_test_mask")
    y = out.pop("_y")

    lam = corpus_event_rate(trains, corpus)
    n_ch = next(iter(trains.values())).n_channels
    # Equation (39) divides the decoded information by the mean number of
    # events per classified unit. The information comes from the test-set
    # confusion matrix, so the event count must come from the test set too;
    # taking it over the whole corpus would mix the two sides of the split.
    test_events = sum(len(trains[u]) for u in split.test)
    n_test_frames = max(1, int(np.sum(test_mask & (y != UNLABELLED))))
    mean_events_per_frame = test_events / n_test_frames

    out.update({
        "budget_cross_check": budget_cross_check(trains),  # C6
        "lambda_events_per_s": lam,                   # eq (35)
        "rate_per_channel": lam / n_ch,               # eq (34)
        # Equation (36) at corpus scale. `metrics.bandwidth_bps` is per-train
        # and cannot be summed over utterances of unequal length, so the
        # formula is applied to the corpus Lambda here; the bit widths are
        # parameters carrying that function's defaults rather than literals,
        # so the two cannot drift apart silently, and they are reported below
        # because a bandwidth without its declared widths is not a figure.
        "bandwidth_bps": lam * (float(np.log2(n_ch)) + timestamp_bits
                                + polarity_bits),     # eq (36)
        "bandwidth_bits": {"channel": float(np.log2(n_ch)),
                           "timestamp": timestamp_bits,
                           "polarity": polarity_bits},
        "bits_per_event": (out["decoded_information_bits"]
                           / mean_events_per_frame
                           if mean_events_per_frame > 0 else 0.0),
        "featurisation": {"tau": tau, "hop": hop, "context": context},
        "seconds": time.time() - t0,
    })
    return out


def run_t1_reference(corpus, *, labelset=None, n_mels=40, frame=0.025,
                     hop=0.010, alignment="causal", context=0,
                     test_fraction=0.3, seed=0, alpha=1e-4, offsets=(0,),
                     n_folds=3, c5_radius=2, alignment_prediction=None,
                     bits_per_feature=32, f_min=50.0, f_max=8000.0):
    """R2, the non-spiking upper bound of proposal 5.9, on T1.

    Same corpus, same labels, same split, same probe, same controls as every
    spiking condition — only the features differ, which is the whole point of
    a control. Emits no events, so equations (34)-(36) do not apply; what is
    reported instead is the dense feature bandwidth R2 costs, which is the
    quantity 6.3's argument for event-based representation is against.
    """
    labelset = labelset or LabelSet(corpus.labels)
    t0 = time.time()

    xs, ys, uids = [], [], []
    for utt in corpus:
        f = mel_features(utt, n_mels=n_mels, frame=frame, hop=hop,
                         alignment=alignment, f_min=f_min, f_max=f_max)
        y_utt = frame_labels(utt, hop, labelset, n_frames=f.shape[0])
        xs.append(stack_context(f, context))
        ys.append(y_utt)
        uids.append(np.full(len(y_utt), utt.uid, dtype=object))
    x, y, uid = np.concatenate(xs), np.concatenate(ys), np.concatenate(uids)

    out = score_t1(corpus, x, y, uid, labelset=labelset,
                   test_fraction=test_fraction, seed=seed, alpha=alpha,
                   offsets=offsets, n_folds=n_folds, c5_radius=c5_radius,
                   alignment_prediction=alignment_prediction)
    for k in ("_split", "_test_mask", "_y"):
        out.pop(k)

    out.update({
        "reference": "R2",
        "lambda_events_per_s": 0.0,
        "feature_bandwidth_bps": feature_bandwidth_bps(n_mels, hop,
                                                       bits_per_feature),
        "bandwidth_bits": {"per_feature": bits_per_feature,
                           "features_per_frame": n_mels,
                           "frames_per_s": 1.0 / hop},
        "featurisation": {"n_mels": n_mels, "frame": frame, "hop": hop,
                          "alignment": alignment, "context": context,
                          "window": "hamming"},
        "seconds": time.time() - t0,
    })
    return out


def _segment_masks(split, seg_uid):
    """Segments inherit the speaker-disjoint split of the utterance they sit in."""
    return (np.isin(seg_uid, np.asarray(split.train, dtype=object)),
            np.isin(seg_uid, np.asarray(split.test, dtype=object)))


def _score_segments(x, seg_label, train_mask, test_mask, n_classes, alpha):
    """Fit a segment-level probe and return its test accuracy.

    Same `LinearProbe` and same `alpha` as every other condition — C4 asks for
    identical decoding, and P1 compares a count condition against a temporal
    one, so a difference in the decoder would land squarely in equation (40).
    """
    keep_tr = train_mask & (seg_label != UNLABELLED)
    keep_te = test_mask & (seg_label != UNLABELLED)
    probe = LinearProbe(n_classes, alpha=alpha).fit(x[keep_tr],
                                                    seg_label[keep_tr])
    pred = probe.predict(x[keep_te])
    return float(np.mean(pred == seg_label[keep_te])), probe


def _score_frames_to_segments(x, y, uid, corpus, labelset, hop, offset,
                              train_mask, seg_label, seg_test_mask, alpha):
    """Fit the frame probe at `offset`, then majority-vote it onto segments.

    The label shift and the frame-to-segment attribution use the same offset,
    so a probe trained against the label at `(k + offset)*hop` has its vote
    counted towards the segment containing that same instant. Getting those two
    out of step would be a silent off-by-one of exactly the kind C5 exists for.
    """
    y_o = np.concatenate([shift_labels(y[uid == u.uid], offset)
                          for u in corpus])
    probe = LinearProbe(len(labelset), alpha=alpha).fit(x[train_mask],
                                                        y_o[train_mask])
    votes = segment_votes(probe.predict(x), uid, corpus, hop, len(labelset),
                          n_segments=len(seg_label), offset_frames=offset)
    keep = seg_test_mask & (seg_label != UNLABELLED) & (votes != UNLABELLED)
    return float(np.mean(votes[keep] == seg_label[keep]))


def mel_dataset(corpus, n_mels=40, frame=0.025, hop=0.010,
                alignment="causal", context=0, f_min=50.0, f_max=8000.0):
    """R2's features for the whole corpus, in corpus order.

    Hoisted out of `run_p1` because R2 does not depend on the encoder or on its
    rate parameter: the ceiling of equation (40) is the same at every budget
    point, and computing it once is both faster and safer than computing it six
    times and trusting the six to agree.
    """
    xs = []
    for utt in corpus:
        f = mel_features(utt, n_mels=n_mels, frame=frame, hop=hop,
                         alignment=alignment, f_min=f_min, f_max=f_max)
        xs.append(stack_context(f, context))
    return np.concatenate(xs)


def ceiling_accuracies(corpus, mel_x, *, labelset=None, hop=0.010,
                       offsets=(-2, -1, 0), test_fraction=0.3, seed=0,
                       alpha=1e-4, n_folds=3, c5_radius=2,
                       alignment_prediction=None):
    """Segment-level accuracy of the R2 ceiling, with its alignment selected.

    Equation (40)'s denominator. Separate from `run_p1` because R2 depends on
    neither the encoder nor its rate parameter, so a sweep computes this once
    per split seed rather than once per budget point — and because computing it
    six times and trusting the six to agree is a worse guarantee than computing
    it once.

    The ceiling has a free parameter of its own, its alignment, and D71 applies
    to it exactly as to the conditions it is the denominator for: chosen on
    folds inside the training split, never on test. Choosing the numerator
    honestly and the denominator on test would bias the index downwards, which
    is not the safe direction — it is simply a different wrong number.
    """
    labelset = labelset or LabelSet(corpus.labels)
    split = speaker_disjoint_split(corpus, test_fraction=test_fraction,
                                   seed=seed)
    speaker_of = {u.uid: u.speaker for u in corpus}
    folds = speaker_folds(split.train, speaker_of, n_folds=n_folds, seed=seed)
    seg_label, seg_uid, _, _, _ = segment_table(corpus, labelset)
    seg_train, seg_test = _segment_masks(split, seg_uid)

    _, y, uid = build_dataset({u.uid: None for u in corpus}, corpus, labelset,
                              0.005, hop, 0, labels_only=True)
    frame_train = np.isin(uid, np.asarray(split.train, dtype=object))
    offsets = tuple(int(o) for o in offsets)

    def evaluate(offset, fit_uids, val_uids):
        return _score_frames_to_segments(
            mel_x, y, uid, corpus, labelset, hop, int(offset),
            _uid_mask(uid, fit_uids), seg_label, _uid_mask(seg_uid, val_uids),
            alpha)

    chosen, grid = select_on_folds(offsets, folds, evaluate, key=str)
    chosen = int(chosen)
    test_profile = {str(o): _score_frames_to_segments(
        mel_x, y, uid, corpus, labelset, hop, o, frame_train, seg_label,
        seg_test, alpha) for o in offsets}
    return {
        "chosen_offset": chosen,
        "accuracy": test_profile[str(chosen)],
        "test_profile": test_profile,
        "selection": {"parameters": ["offset"], "chosen": {"offset": chosen},
                      "criterion": "segment accuracy",
                      "selected_on": "speaker-disjoint folds within the "
                                     "training split",
                      "n_folds": len(folds),
                      "folds": fold_sizes(folds, speaker_of),
                      "grid": grid, "candidates": list(offsets),
                      "predicted": alignment_prediction},
        "c5_alignment": {
            "validation": interior_maximum(profile_scores(grid), chosen,
                                           radius=c5_radius),
            "test": interior_maximum(test_profile, chosen, radius=c5_radius)},
    }


def run_p1(corpus, trains, *, labelset=None, tau=0.005, hop=0.010, context=0,
           test_fraction=0.3, seed=0, alpha=1e-4, offsets=(-2, -1, 0),
           n_folds=3, c5_radius=2, alignment_prediction=None,
           n_mels=40, frame=0.025, alignment="causal", f_min=50.0,
           f_max=8000.0, count_offset_control=0.020, mel_x=None,
           ceiling=None, taus=None):
    """Preliminary experiment P1 (proposal 7.1) on T1, at segment level.

    Four conditions on one speaker-disjoint split, all decoded by the same
    probe at the same `alpha`:

    - `count`   — per-channel event counts over the segment, no time axis.
    - `rate`    — the same divided by segment duration, so duration carries no
                  information (Q26).
    - `temporal`— the frame probe on equation (32), majority-voted to segments.
    - `ceiling` — R2's mel features, same probe, same vote.

    and the temporal information index of equation (40) built from them.

    **`tau_phi` and the alignment offset are one joint grid, selected together
    on folds inside the training split.** D69 puts them on the same footing and
    the reason is in that decision: holding the alignment at zero while
    sweeping `tau_phi` imposes a misalignment penalty that grows along the
    axis, then selects the `tau_phi` least harmed by it. Selecting the pair on
    test — which is what this function did until D71 — instead lets the index
    absorb whatever noise the test set happens to carry, in the numerator and
    the denominator separately.
    """
    labelset = labelset or LabelSet(corpus.labels)
    t0 = time.time()
    n_classes = len(labelset)

    split = speaker_disjoint_split(corpus, test_fraction=test_fraction,
                                   seed=seed)
    speaker_of = {u.uid: u.speaker for u in corpus}
    folds = speaker_folds(split.train, speaker_of, n_folds=n_folds, seed=seed)
    seg_label, seg_uid, _, _, _ = segment_table(corpus, labelset)
    seg_train, seg_test = _segment_masks(split, seg_uid)

    # --- the two count conditions, which have no frame grid at all ----------
    counts = segment_counts(trains, corpus, normalise=False)
    rates = segment_counts(trains, corpus, normalise=True)
    a_count, count_probe = _score_segments(counts, seg_label, seg_train,
                                           seg_test, n_classes, alpha)
    a_rate, _ = _score_segments(rates, seg_label, seg_train, seg_test,
                                n_classes, alpha)

    # C3 for the count condition — permuted training labels must return to the
    # floor here too, since the segment split is a different partition of the
    # data from the frame split and could leak where the frame one does not.
    rng = np.random.default_rng(seed + 991)
    shuffled = seg_label.copy()
    idx = np.flatnonzero(seg_train & (seg_label != UNLABELLED))
    shuffled[idx] = seg_label[rng.permutation(idx)]
    a_count_shuffled, _ = _score_segments(counts, shuffled, seg_train,
                                          seg_test, n_classes, alpha)

    # C5's segment-level analogue: slide the counting window off the segment.
    # A count that does not care where its window sits is not measuring the
    # segment, and the index would be built on nothing.
    shifted = segment_counts(trains, corpus, offset=count_offset_control)
    a_count_shifted, _ = _score_segments(shifted, seg_label, seg_train,
                                         seg_test, n_classes, alpha)

    # --- the two frame-based conditions -------------------------------------
    taus = tuple(taus) if taus else (tau,)
    offsets = tuple(int(o) for o in offsets)
    _, y, uid = build_dataset({u.uid: None for u in corpus}, corpus, labelset,
                              tau, hop, context, labels_only=True)
    frame_train = np.isin(uid, np.asarray(split.train, dtype=object))

    x_r2 = mel_dataset(corpus, n_mels=n_mels, frame=frame, hop=hop,
                       alignment=alignment, context=context, f_min=f_min,
                       f_max=f_max) if mel_x is None else mel_x

    # The featurisation is built once per tau_phi, not once per candidate: the
    # offset moves labels, not features.
    x_by_tau = {tv: build_dataset(trains, corpus, labelset, tv, hop,
                                  context)[0] for tv in taus}
    n_features_temporal = int(next(iter(x_by_tau.values())).shape[1])
    candidates = [(tv, o) for tv in taus for o in offsets]

    def key(c):
        return f"{c[0]}|{c[1]}"

    def evaluate(candidate, fit_uids, val_uids):
        tv, o = candidate
        return _score_frames_to_segments(
            x_by_tau[tv], y, uid, corpus, labelset, hop, int(o),
            _uid_mask(uid, fit_uids), seg_label, _uid_mask(seg_uid, val_uids),
            alpha)

    chosen, grid = select_on_folds(candidates, folds, evaluate, key=key)
    best_tv, best_o = chosen[0], int(chosen[1])

    temporal = {f"{tv}": {str(o): _score_frames_to_segments(
        x_by_tau[tv], y, uid, corpus, labelset, hop, o, frame_train,
        seg_label, seg_test, alpha) for o in offsets} for tv in taus}
    a_temporal = temporal[f"{best_tv}"][str(best_o)]

    if ceiling is None:
        ceiling = ceiling_accuracies(
            corpus, x_r2, labelset=labelset, hop=hop, offsets=offsets,
            test_fraction=test_fraction, seed=seed, alpha=alpha,
            n_folds=n_folds, c5_radius=c5_radius,
            alignment_prediction=alignment_prediction)
    a_ceiling = ceiling["accuracy"]

    # C5 for the temporal condition: the offset profile at the selected
    # tau_phi, on the validation folds that did the selecting and on test.
    val_at_best_tau = {str(o): grid[key((best_tv, o))]["score"]
                       for o in offsets}
    flat_test = {(tv, o): temporal[f"{tv}"][str(o)]
                 for tv in taus for o in offsets}
    test_best = max(flat_test, key=flat_test.get)

    zero_t = temporal[f"{taus[0]}"].get("0")
    zero_c = ceiling["test_profile"].get("0")
    n_test_seg = int(np.sum(seg_test & (seg_label != UNLABELLED)))
    floor = float(np.bincount(seg_label[seg_test & (seg_label != UNLABELLED)]
                              ).max() / max(1, n_test_seg))

    return {
        "level": "segment",
        "accuracy_count": a_count,
        "accuracy_rate": a_rate,
        "accuracy_temporal": temporal,
        "accuracy_ceiling": ceiling["test_profile"],
        "best_offset_temporal": best_o,
        "best_tau_temporal": best_tv,
        "best_accuracy_temporal": a_temporal,
        "best_offset_ceiling": ceiling["chosen_offset"],
        "selection": {                                        # D71
            "parameters": ["tau_phi", "offset"],
            "chosen": {"tau_phi": best_tv, "offset": best_o},
            "criterion": "segment accuracy",
            "selected_on": "speaker-disjoint folds within the training split",
            "n_folds": len(folds),
            "folds": fold_sizes(folds, speaker_of),
            "grid": grid,
            "candidates": [list(c) for c in candidates],
            "test_profile": {key(c): v for c, v in flat_test.items()},
            "test_argmax": {"tau_phi": test_best[0], "offset": test_best[1]},
            "test_score_at_selected": a_temporal,
            "test_score_at_argmax": flat_test[test_best],
            "selection_bias": flat_test[test_best] - a_temporal,
            "predicted": alignment_prediction,
            "ceiling": ceiling["selection"],
        },
        "c5_alignment": {                                     # C5, D70
            "temporal": {
                "validation": interior_maximum(val_at_best_tau, best_o,
                                               radius=c5_radius),
                "test": interior_maximum(temporal[f"{best_tv}"], best_o,
                                         radius=c5_radius)},
            "ceiling": ceiling["c5_alignment"],
        },
        # Equation (40) three ways: at the literal offset zero, at the selected
        # operating point, and at the test argmax the pre-D71 code reported.
        # The last is kept only so the size of that bias is on the record.
        "tii_at_zero": (temporal_information_index(zero_t, a_count, zero_c)
                        if zero_t is not None and zero_c is not None
                        else None),
        "tii_at_best": temporal_information_index(a_temporal, a_count,
                                                  a_ceiling),
        "tii_at_best_using_rate": temporal_information_index(
            a_temporal, a_rate, a_ceiling),
        "tii_at_test_argmax": temporal_information_index(
            flat_test[test_best], a_count,
            max(v for v in ceiling["test_profile"].values())),
        # Equation (40)'s denominator, reported because the index alone cannot
        # be judged without it: a thin denominator makes a large index that
        # reads as a strong result and is seed noise.
        "tii_denominator_at_zero": (zero_c - a_count if zero_c is not None
                                    else None),
        "tii_denominator_at_best": a_ceiling - a_count,
        "majority_floor": floor,                          # C2
        "chance": labelset.chance,                        # C2
        "count_shuffled_accuracy": a_count_shuffled,      # C3
        "count_window_shifted_accuracy": a_count_shifted,  # C5 analogue
        "count_window_shift_s": count_offset_control,
        "split": split.as_dict(),                         # C4
        "lambda_events_per_s": corpus_event_rate(trains, corpus),
        "n_segments_train": int(np.sum(seg_train & (seg_label != UNLABELLED))),
        "n_segments_test": n_test_seg,
        "n_features_count": int(counts.shape[1]),
        "n_features_temporal": n_features_temporal,
        "n_features_ceiling": int(x_r2.shape[1]),
        "probe_settings": count_probe.settings,           # C4
        "featurisation": {"taus": list(taus), "hop": hop, "context": context,
                          "n_mels": n_mels, "frame": frame,
                          "alignment": alignment},
        "seconds": time.time() - t0,
    }


def _per_utterance(values, uid, corpus):
    """Split a corpus-wide frame array back into per-utterance arrays."""
    return [values[uid == u.uid] for u in corpus]


def run_t3(corpus, trains, *, tau=0.005, hop=0.010, context=0,
           test_fraction=0.3, seed=0, alpha=1e-4, offsets=(-2, -1, 0),
           n_folds=3, c5_radius=2, alignment_prediction=None,
           tolerance=DEFAULT_TOLERANCE, label_tolerance_frames=1,
           min_separation=0.020, n_thresholds=49, n_thresholds_select=None,
           features=None):
    """T3, boundary detection (proposal 4.3), on one operating point.

    The probe is binary logistic regression per frame — 6.2's rule for T1 and
    T3 — and its boundary posterior is turned into instants by `pick_peaks`,
    matched to the reference by `match_boundaries`, and scored by
    `score_boundaries`.

    **Two free parameters, both chosen off the reported number.** The detection
    threshold is chosen on the fitting side and applied unchanged to the
    scoring side: F-score at a single operating point is meaningless without
    one, 4.3 names none, and choosing it on test would flatter every encoder by
    an amount depending on how peaked its posterior happened to be. The
    alignment offset is chosen the same way, on speaker-disjoint folds inside
    the training split (D71) — until that decision it was chosen by maximising
    the test F-score, which is the same fault the threshold rule was written to
    avoid, one level up.

    The threshold grid is taken from the posterior on the fitting utterances
    alone, not the whole corpus. Deriving even the *range* of the sweep from
    the scoring side is a small leak, and small leaks in a threshold are how a
    detector scores above what it can actually do.

    Inside the selection folds the threshold grid is deliberately coarser
    (`n_thresholds_select`, a quarter of the reported grid by default). The
    threshold is a nuisance parameter there: what a fold has to do is rank the
    offsets against each other, and it dominates the cost of the whole sweep
    because it re-runs the peak picker once per grid point per fold. The
    reported figure is always computed at the full grid.

    `features=None` builds the equation (32) featurisation; passing an array
    instead scores any other frame-wise representation on the same task, which
    is how the R2 ceiling is obtained for T3.
    """
    t0 = time.time()
    labelset = LabelSet(corpus.labels)
    split = speaker_disjoint_split(corpus, test_fraction=test_fraction,
                                   seed=seed)
    speaker_of = {u.uid: u.speaker for u in corpus}
    folds = speaker_folds(split.train, speaker_of, n_folds=n_folds, seed=seed)

    if features is None:
        x, _, uid = build_dataset(trains, corpus, labelset, tau, hop, context)
    else:
        x = features
        _, _, uid = build_dataset({u.uid: None for u in corpus}, corpus,
                                  labelset, tau, hop, context, labels_only=True)

    y = np.concatenate([
        boundary_labels(u, hop, tolerance_frames=label_tolerance_frames)
        for u in corpus])
    by_uid = {u.uid: u for u in corpus}
    offsets = tuple(int(o) for o in offsets)

    n_select = int(n_thresholds_select or max(9, n_thresholds // 4))

    def fit_and_score(y_all, offset, fit_uids, eval_uids, n_thr=None):
        """Fit on `fit_uids`, pick the threshold there, score on `eval_uids`."""
        y_o = np.concatenate([shift_labels(y_all[uid == u.uid], offset)
                              for u in corpus])
        fit_rows = _uid_mask(uid, fit_uids)
        keep = fit_rows & (y_o != UNLABELLED)
        probe = LinearProbe(2, alpha=alpha).fit(x[keep], y_o[keep])
        posterior = probe.predict_proba(x)[:, 1]
        by_utt = dict(zip([u.uid for u in corpus],
                          _per_utterance(posterior, uid, corpus)))
        fit_utts = [by_uid[u] for u in sorted(fit_uids)]
        eval_utts = [by_uid[u] for u in sorted(eval_uids)]

        # Threshold chosen on the fitting side, applied to the scoring side.
        # Swept over the posterior range observed there rather than [0, 1]: a
        # probe whose posterior never exceeds 0.3 would otherwise be scored
        # entirely at zero detections.
        fit_post = posterior[fit_rows]
        lo, hi = float(fit_post.min()), float(fit_post.max())
        grid = np.linspace(lo, hi, int(n_thr or n_thresholds))[:-1]
        best_thr, best_f = grid[0] if grid.size else 0.5, -1.0
        for thr in grid:
            pred = [pick_peaks(by_utt[u.uid], hop, thr, min_separation)
                    for u in fit_utts]
            f = score_boundaries(pred, [u.boundaries() for u in fit_utts],
                                 tolerance)["f_score"]
            if f > best_f:
                best_thr, best_f = float(thr), f

        pred_eval = [pick_peaks(by_utt[u.uid], hop, best_thr, min_separation)
                     for u in eval_utts]
        scored = score_boundaries(pred_eval,
                                  [u.boundaries() for u in eval_utts],
                                  tolerance)
        scored["threshold"] = best_thr
        scored["train_f_score"] = best_f
        # The probe on its own, before any threshold or peak picker touches it.
        eval_rows = _uid_mask(uid, eval_uids)
        valid = eval_rows & (y_o != UNLABELLED)
        scored["frame_auc"] = frame_auc(posterior[valid], y_o[valid])
        return scored

    def evaluate(offset, fit_uids, val_uids):
        return fit_and_score(y, int(offset), fit_uids, val_uids,
                             n_thr=n_select)["f_score"]

    chosen, grid = select_on_folds(offsets, folds, evaluate, key=str)
    chosen = int(chosen)

    by_offset = {str(o): fit_and_score(y, o, split.train, split.test)
                 for o in offsets}
    test_profile = {k: v["f_score"] for k, v in by_offset.items()}
    test_best = max(test_profile, key=test_profile.get)
    best = str(chosen)

    # C3 — permuted training labels. A detector fitted on shuffled boundaries
    # must not localise anything, and if it does the split leaks.
    rng = np.random.default_rng(seed + 991)
    y_shuffled = y.copy()
    idx = np.flatnonzero(_uid_mask(uid, split.train))
    y_shuffled[idx] = y[rng.permutation(idx)]
    shuffled = fit_and_score(y_shuffled, chosen, split.train, split.test)

    # C2 for a detection task — evenly spaced boundaries at the reference rate.
    # This is the strategy the R-value exists to penalise, so it is the floor
    # any reported F-score has to clear.
    test_utts = [by_uid[u] for u in sorted(split.test)]
    baseline = score_boundaries(
        uniform_baseline([u.duration for u in test_utts],
                         [len(u.boundaries()) for u in test_utts]),
        [u.boundaries() for u in test_utts], tolerance)

    return {
        "task": "T3",
        "by_offset": by_offset,
        "best_offset": chosen,
        "f_score": by_offset[best]["f_score"],
        "r_value": by_offset[best]["r_value"],
        "precision": by_offset[best]["precision"],
        "recall": by_offset[best]["recall"],
        "over_segmentation": by_offset[best]["over_segmentation"],
        # None when zero is not in the sweep; see run_t2.
        "f_score_at_zero": (by_offset["0"]["f_score"]
                            if "0" in by_offset else None),
        "frame_auc": by_offset[best]["frame_auc"],
        "frame_auc_at_zero": (by_offset["0"]["frame_auc"]
                              if "0" in by_offset else None),
        "selection": {                                         # D71
            "parameters": ["offset", "threshold"],
            "chosen": {"offset": chosen,
                       "threshold": by_offset[best]["threshold"]},
            "criterion": "boundary F-score",
            "selected_on": "speaker-disjoint folds within the training split; "
                           "threshold on the fitting side of each",
            "n_folds": len(folds),
            "folds": fold_sizes(folds, speaker_of),
            "grid": grid,
            "candidates": list(offsets),
            "test_profile": test_profile,
            "test_argmax_offset": int(test_best),
            "test_score_at_selected": test_profile[best],
            "test_score_at_argmax": test_profile[test_best],
            "selection_bias": test_profile[test_best] - test_profile[best],
            "predicted": alignment_prediction,
        },
        "c5_alignment": {                                      # C5, D70
            "validation": interior_maximum(profile_scores(grid), chosen,
                                           radius=c5_radius),
            "test": interior_maximum(test_profile, chosen, radius=c5_radius)},
        "shuffled_f_score": shuffled["f_score"],           # C3
        "shuffled_r_value": shuffled["r_value"],           # C3
        "shuffled_frame_auc": shuffled["frame_auc"],       # C3
        "uniform_baseline": baseline,                      # C2
        "split": split.as_dict(),                          # C4
        "lambda_events_per_s": (corpus_event_rate(trains, corpus)
                                if features is None else 0.0),
        "n_test_utterances": len(test_utts),
        "positive_frame_rate": float(np.mean(y[_uid_mask(uid, split.train)])),
        "settings": {"tolerance": tolerance,
                     "label_tolerance_frames": label_tolerance_frames,
                     "min_separation": min_separation,
                     "n_thresholds": n_thresholds,
                     "n_thresholds_select": n_select,
                     "tau": tau, "hop": hop, "context": context,
                     "threshold_selected_on": "fitting side"},
        "seconds": time.time() - t0,
    }


def _shift_indices(n, offset):
    """Frame k takes the target at frame k+offset; out of range is invalid.

    The same convention as `tasks.shift_labels` and
    `segments.frame_segment_index`, restated for float targets because
    `shift_labels` fills with an integer sentinel that has no meaning in a
    contour.
    """
    src = np.arange(n) + offset
    valid = (src >= 0) & (src < n)
    return np.clip(src, 0, max(n - 1, 0)), valid


def _per_utterance_pearson(pred, ref, utt_index, min_frames=5):
    """Mean within-utterance Pearson r — T2's headline (Q32).

    Computed per utterance and averaged rather than pooled over all voiced
    frames, because speakers differ in mean f0 far more than a contour moves
    within one utterance. A pooled correlation is therefore dominated by
    between-speaker variance, and a probe emitting one constant per utterance —
    in effect estimating voice height — scores well on it while tracking no
    contour at all. Proposal 4.2 puts T2 at the opposite corner of the demand
    space from T1 and grounds it in phase locking to the glottal cycle; a
    figure winnable by voice height would make it partly the speaker task D02
    removed from the battery.

    Utterances with fewer than `min_frames` voiced frames, or with no variance
    in either series, are excluded and counted rather than scored as zero.
    """
    values, excluded = [], 0
    for u in np.unique(utt_index):
        m = utt_index == u
        p, r = pred[m], ref[m]
        if p.size < min_frames or np.std(p) == 0.0 or np.std(r) == 0.0:
            excluded += 1
            continue
        values.append(float(np.corrcoef(p, r)[0, 1]))
    return (float(np.mean(values)) if values else float("nan"), excluded,
            len(values))


def run_t2(corpus, trains, *, tau=0.005, hop=0.010, context=0,
           test_fraction=0.3, seed=0, alpha=1e-4, ridge_alpha=1.0,
           ridge_alphas=None, offsets=(-2, -1, 0), n_folds=3, c5_radius=2,
           alignment_prediction=None, ref=SEMITONE_REF_HZ,
           features=None, min_frames=5):
    """T2, fundamental frequency contour (proposal 4.2), on one operating point.

    Ridge regression per frame on the voiced frames for the contour, and a
    separate binary probe for the voiced/unvoiced decision, which 4.2 asks be
    reported separately and which a regression cannot produce.

    Both the per-utterance and the pooled correlation are returned. The first
    is the headline; the gap between them is how much of the pooled figure is
    voice height rather than contour (Q32).

    **Two free parameters, one grid, two criteria.** The ridge penalty and the
    alignment offset are scored together on speaker-disjoint folds inside the
    training split, from one pass of fits, and then chosen in a nesting that
    respects what each is for. The penalty is chosen on validation RMSE,
    because D59's failure — a prediction 468 octaves wide — is invisible to a
    correlation, which is scale-free. The offset is then chosen on the
    per-utterance correlation, because that is the headline being reported and
    selecting an offset on RMSE would mean choosing for one quantity and
    reporting another. Both grids are recorded (D71).
    """
    t0 = time.time()
    labelset = LabelSet(corpus.labels)
    split = speaker_disjoint_split(corpus, test_fraction=test_fraction,
                                   seed=seed)
    speaker_of = {u.uid: u.speaker for u in corpus}
    folds = speaker_folds(split.train, speaker_of, n_folds=n_folds, seed=seed)

    if features is None:
        x, _, uid = build_dataset(trains, corpus, labelset, tau, hop, context)
    else:
        x = features
        _, _, uid = build_dataset({u.uid: None for u in corpus}, corpus,
                                  labelset, tau, hop, context, labels_only=True)
    train_mask = _uid_mask(uid, split.train)
    test_mask = _uid_mask(uid, split.test)

    contours, voiced_flags, utt_ids = [], [], []
    for u in corpus:
        s, v = f0_targets(u, hop, ref=ref)
        contours.append(s)
        voiced_flags.append(v)
        utt_ids.append(np.full(len(s), u.uid, dtype=object))
    contour = np.concatenate(contours)
    utt = np.concatenate(utt_ids)
    offsets = tuple(int(o) for o in offsets)
    alphas = [float(a) for a in (ridge_alphas if ridge_alphas
                                 else [ridge_alpha])]

    def targets_at(offset):
        s_out = np.full(len(contour), np.nan)
        v_out = np.zeros(len(contour), dtype=bool)
        ok = np.zeros(len(contour), dtype=bool)
        base = 0
        for u, c, v in zip(corpus, contours, voiced_flags):
            n = len(c)
            src, valid = _shift_indices(n, offset)
            sl = slice(base, base + n)
            s_out[sl] = np.where(valid, c[src], np.nan)
            v_out[sl] = np.where(valid, v[src], False)
            ok[sl] = valid
            base += n
        return s_out, v_out, ok

    def score_at(offset, ridge, fit_mask, eval_mask, shuffle=False):
        """Fit at one (offset, penalty) on `fit_mask`, score on `eval_mask`."""
        s, v, ok = targets_at(offset)
        fit_rows = fit_mask & ok & v & ~np.isnan(s)
        eval_rows = eval_mask & ok & v & ~np.isnan(s)
        if fit_rows.sum() < 2 or eval_rows.sum() < 2:
            return None
        y = s.copy()
        if shuffle:
            rng = np.random.default_rng(seed + 991)
            idx = np.flatnonzero(fit_rows)
            y[idx] = s[rng.permutation(idx)]

        probe = RidgeProbe(alpha=float(ridge)).fit(x[fit_rows], y[fit_rows])
        pred = probe.predict(x[eval_rows])
        truth = s[eval_rows]

        per_utt, excluded, n_scored = _per_utterance_pearson(
            pred, truth, utt[eval_rows], min_frames=min_frames)
        pooled = (float(np.corrcoef(pred, truth)[0, 1])
                  if pred.size > 1 and np.std(pred) > 0 else float("nan"))
        rmse = float(np.sqrt(np.mean((pred - truth) ** 2)))
        # The floor: predict the training mean for every frame. Its RMSE is the
        # test contour's spread about that mean, and any probe not beating it
        # has learned nothing about f0.
        floor_rmse = float(np.sqrt(np.mean((truth - probe.intercept) ** 2)))

        return {"pearson_per_utterance": per_utt, "pearson_pooled": pooled,
                "rmse_semitones": rmse, "floor_rmse_semitones": floor_rmse,
                "n_test_frames": int(eval_rows.sum()),
                "n_utterances_scored": n_scored,
                "n_utterances_excluded": excluded,
                "ridge_alpha_chosen": float(ridge),
                "probe_settings": probe.settings}

    candidates = [(o, a) for o in offsets for a in alphas]

    def key(c):
        return f"{int(c[0])}|{c[1]:g}"

    def evaluate(candidate, fit_uids, val_uids):
        o, a = candidate
        r = score_at(o, a, _uid_mask(uid, fit_uids), _uid_mask(uid, val_uids))
        if r is None:
            return None
        return {"pearson": r["pearson_per_utterance"],
                "rmse": r["rmse_semitones"]}

    def choose(grid):
        """Penalty on RMSE within each offset, then offset on correlation."""
        per_offset = {}
        for o in offsets:
            keys = [key((o, a)) for a in alphas]
            by_rmse = {k: grid[k]["scores"]["rmse"] for k in keys
                       if "rmse" in grid[k]["scores"]}
            if not by_rmse:
                continue
            k = min(by_rmse, key=by_rmse.get)
            if "pearson" in grid[k]["scores"]:
                per_offset[k] = grid[k]["scores"]["pearson"]
        if not per_offset:
            return key(candidates[0])
        return max(per_offset, key=per_offset.get)

    chosen, grid = select_on_folds(candidates, folds, evaluate, key=key,
                                   choose=choose)
    chosen_offset, chosen_alpha = int(chosen[0]), float(chosen[1])

    # Each offset's own validation-best penalty, so the test-side profile shows
    # what that offset would have reported had it been the one selected.
    alpha_for = {}
    for o in offsets:
        keys = [key((o, a)) for a in alphas]
        by_rmse = {k: grid[k]["scores"]["rmse"] for k in keys
                   if "rmse" in grid[k]["scores"]}
        alpha_for[o] = (float(min(by_rmse, key=by_rmse.get).split("|")[1])
                        if by_rmse else chosen_alpha)

    by_offset = {str(o): score_at(o, alpha_for[o], train_mask, test_mask)
                 for o in offsets}
    best = str(chosen_offset)
    test_profile = {k: (v["pearson_per_utterance"] if v else None)
                    for k, v in by_offset.items()}
    scored = {k: v for k, v in test_profile.items()
              if v is not None and not np.isnan(v)}
    test_best = max(scored, key=scored.get) if scored else best
    val_profile = {str(o): grid[key((o, alpha_for[o]))]["scores"].get("pearson")
                   for o in offsets}
    # Q38: the offset validation RMSE would have chosen, recorded beside the
    # one the headline correlation chose. On this corpus they disagree and the
    # correlation profile is nearly flat, so the alternative reading has to be
    # recoverable from the result file without re-running the sweep.
    val_rmse = {str(o): grid[key((o, alpha_for[o]))]["scores"].get("rmse")
                for o in offsets}
    scored_rmse = {k: v for k, v in val_rmse.items() if v is not None}
    rmse_offset = (int(min(scored_rmse, key=scored_rmse.get))
                   if scored_rmse else chosen_offset)

    shuffled = score_at(chosen_offset, chosen_alpha, train_mask, test_mask,
                        shuffle=True)

    # Voicing, reported separately per 4.2. All valid frames, not just voiced.
    s0, v0, ok0 = targets_at(chosen_offset)
    vp = LinearProbe(2, alpha=alpha).fit(x[train_mask & ok0],
                                         v0[train_mask & ok0].astype(np.int64))
    v_true = v0[test_mask & ok0].astype(np.int64)
    voicing_acc = float(np.mean(vp.predict(x[test_mask & ok0]) == v_true))
    voicing_floor = float(max(v_true.mean(), 1.0 - v_true.mean()))

    return {
        "task": "T2",
        "by_offset": by_offset,
        "best_offset": chosen_offset,
        "pearson_per_utterance": by_offset[best]["pearson_per_utterance"],
        "pearson_pooled": by_offset[best]["pearson_pooled"],
        "rmse_semitones": by_offset[best]["rmse_semitones"],
        "floor_rmse_semitones": by_offset[best]["floor_rmse_semitones"],
        # None when the offset sweep does not include zero, which happens
        # whenever a caller fixes the alignment rather than scanning it — P2
        # does. Indexing "0" unconditionally assumed a sweep shape that is not
        # guaranteed and raised a KeyError the first time one differed.
        "pearson_per_utterance_at_zero":
            (by_offset["0"]["pearson_per_utterance"]
             if by_offset.get("0") else None),
        "selection": {                                          # D71
            "parameters": ["offset", "ridge_alpha"],
            "chosen": {"offset": chosen_offset,
                       "ridge_alpha": chosen_alpha},
            "criterion": "ridge_alpha on validation RMSE within each offset, "
                         "then offset on mean within-utterance Pearson r",
            "selected_on": "speaker-disjoint folds within the training split",
            "n_folds": len(folds),
            "folds": fold_sizes(folds, speaker_of),
            "grid": grid,
            "candidates": [[o, a] for o, a in candidates],
            "ridge_alpha_by_offset": {str(o): alpha_for[o] for o in offsets},
            "validation_pearson_by_offset": val_profile,
            "validation_rmse_by_offset": val_rmse,
            "rmse_selected_offset": rmse_offset,                    # Q38
            "score_at_rmse_selected_offset": test_profile.get(str(rmse_offset)),
            "test_profile": test_profile,
            "test_argmax_offset": int(test_best),
            "test_score_at_selected": test_profile[best],
            "test_score_at_argmax": test_profile[test_best],
            "selection_bias": ((test_profile[test_best] - test_profile[best])
                               if test_profile[best] is not None
                               and test_profile[test_best] is not None
                               else None),
            "predicted": alignment_prediction,
        },
        "c5_alignment": {                                       # C5, D70
            "validation": interior_maximum(val_profile, chosen_offset,
                                           radius=c5_radius),
            "test": interior_maximum(test_profile, chosen_offset,
                                     radius=c5_radius)},
        "shuffled_pearson_per_utterance":
            (shuffled["pearson_per_utterance"] if shuffled else None),   # C3
        "shuffled_pearson_pooled":
            (shuffled["pearson_pooled"] if shuffled else None),          # C3
        "voicing_accuracy": voicing_acc,
        "voicing_floor": voicing_floor,                         # C2
        "split": split.as_dict(),                               # C4
        "lambda_events_per_s": (corpus_event_rate(trains, corpus)
                                if features is None else 0.0),
        "n_utterances_scored": by_offset[best]["n_utterances_scored"],
        "n_utterances_excluded": by_offset[best]["n_utterances_excluded"],
        "ridge_alpha_chosen": chosen_alpha,
        "settings": {"tau": tau, "hop": hop, "context": context,
                     "ridge_alpha": ridge_alpha,
                     "ridge_alphas": list(alphas),
                     "ridge_alpha_selected_on":
                         "speaker-disjoint folds within the training split",
                     "semitone_ref_hz": ref,
                     "min_frames_per_utterance": min_frames,
                     "headline": "pearson_per_utterance"},
        "seconds": time.time() - t0,
    }
