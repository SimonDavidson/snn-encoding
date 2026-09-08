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
from .probes import LinearProbe, RidgeProbe
from .boundaries import (DEFAULT_TOLERANCE, frame_auc, pick_peaks,
                         score_boundaries, uniform_baseline)
from .reference import feature_bandwidth_bps, mel_features
from .segments import (segment_counts, segment_table, segment_votes,
                       temporal_information_index)
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


def score_t1(corpus, x, y, uid, *, labelset=None, test_fraction=0.3, seed=0,
             alpha=1e-4, control_offsets=(-1, 1)):
    """Split, fit and run the Layer 2 controls on an already-built dataset.

    Factored out of `run_t1` so that the spiking conditions and the R2
    reference of proposal 5.9 go through *one* decoder path rather than two
    that are meant to match. C4 requires identical decoding — "same probe
    architectures, same optimiser, schedule, regularisation and stopping
    criterion across all encoders" — and two copies could drift while each
    still looked right on its own. This is the argument D30 made for E2 and E3
    sharing one lattice rule, applied to the decoder.

    Everything above the features is shared: the split, the probe, C2, C3, C5,
    and the confusion matrix feeding equation (38). What differs between a
    spiking condition and R2 is only what produced `x`.
    """
    labelset = labelset or LabelSet(corpus.labels)
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

    confusion = probe.confusion(x[test_mask], y[test_mask])
    return {
        "accuracy": accuracy,
        "majority_floor": majority_floor(y[test_mask]),   # C2
        "chance": labelset.chance,                        # C2
        "shuffled_label_accuracy": shuffled_accuracy,     # C3
        "misaligned_accuracy": misaligned,                # C5
        "split": split.as_dict(),                         # C4
        "decoded_information_bits": metrics.decoded_information(confusion),
        "confusion": confusion.tolist(),
        "n_frames_train": int(np.sum(train_mask & (y != UNLABELLED))),
        "n_frames_test": int(np.sum(test_mask & (y != UNLABELLED))),
        "n_features": int(x.shape[1]),
        "probe_settings": probe.settings,                 # C4 fairness
        "probe_converged": probe.converged_,
        "probe_iterations": probe.n_iter_,
        "_split": split,
        "_test_mask": test_mask,
        "_y": y,
    }


def run_t1(corpus, trains, *, labelset=None, tau=0.005, hop=0.010, context=0,
           test_fraction=0.3, seed=0, alpha=1e-4, control_offsets=(-1, 1),
           timestamp_bits=20, polarity_bits=1):
    """Score one spiking operating point on T1, with its budget and controls.

    Returns a dict of everything the manifest should carry for this point:
    the headline accuracy, both C2 floors, the C3 shuffled-label control, the
    C5 misalignment controls, the C6 cross-check, the C4 split description, the
    budget of equations (34)-(36), and the decoded information of equation (38).
    """
    labelset = labelset or LabelSet(corpus.labels)
    t0 = time.time()

    x, y, uid = build_dataset(trains, corpus, labelset, tau, hop, context)
    out = score_t1(corpus, x, y, uid, labelset=labelset,
                   test_fraction=test_fraction, seed=seed, alpha=alpha,
                   control_offsets=control_offsets)
    split, test_mask = out.pop("_split"), out.pop("_test_mask")
    out.pop("_y")

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
                     test_fraction=0.3, seed=0, alpha=1e-4,
                     control_offsets=(-1, 1), bits_per_feature=32,
                     f_min=50.0, f_max=8000.0):
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
                   control_offsets=control_offsets)
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
                       alpha=1e-4):
    """Segment-level accuracy of the R2 ceiling, at each offset.

    Equation (40)'s denominator. Separate from `run_p1` because R2 depends on
    neither the encoder nor its rate parameter, so a sweep computes this once
    per split seed rather than once per budget point — and because computing it
    six times and trusting the six to agree is a worse guarantee than computing
    it once.
    """
    labelset = labelset or LabelSet(corpus.labels)
    split = speaker_disjoint_split(corpus, test_fraction=test_fraction,
                                   seed=seed)
    seg_label, seg_uid, _, _, _ = segment_table(corpus, labelset)
    _, seg_test = _segment_masks(split, seg_uid)

    _, y, uid = build_dataset({u.uid: None for u in corpus}, corpus, labelset,
                              0.005, hop, 0, labels_only=True)
    frame_train = np.isin(uid, np.asarray(split.train, dtype=object))
    return {str(o): _score_frames_to_segments(
        mel_x, y, uid, corpus, labelset, hop, o, frame_train, seg_label,
        seg_test, alpha) for o in offsets}


def run_p1(corpus, trains, *, labelset=None, tau=0.005, hop=0.010, context=0,
           test_fraction=0.3, seed=0, alpha=1e-4, offsets=(-2, -1, 0),
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

    and the temporal information index of equation (40) built from them. The
    two frame-based conditions are scored at every offset in `offsets`, because
    Q24 established that offset zero is not their best alignment and an index
    computed there would understate the numerator and the denominator by
    different amounts.
    """
    labelset = labelset or LabelSet(corpus.labels)
    t0 = time.time()
    n_classes = len(labelset)

    split = speaker_disjoint_split(corpus, test_fraction=test_fraction,
                                   seed=seed)
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
    _, y, uid = build_dataset({u.uid: None for u in corpus}, corpus, labelset,
                              tau, hop, context, labels_only=True)
    frame_train = np.isin(uid, np.asarray(split.train, dtype=object))

    x_r2 = mel_dataset(corpus, n_mels=n_mels, frame=frame, hop=hop,
                       alignment=alignment, context=context, f_min=f_min,
                       f_max=f_max) if mel_x is None else mel_x

    temporal, n_features_temporal = {}, 0
    for tv in taus:
        x_t, _, _ = build_dataset(trains, corpus, labelset, tv, hop, context)
        n_features_temporal = x_t.shape[1]
        temporal[f"{tv}"] = {str(o): _score_frames_to_segments(
            x_t, y, uid, corpus, labelset, hop, o, frame_train, seg_label,
            seg_test, alpha) for o in offsets}
    if ceiling is None:
        ceiling = {str(o): _score_frames_to_segments(
            x_r2, y, uid, corpus, labelset, hop, o, frame_train, seg_label,
            seg_test, alpha) for o in offsets}

    flat_t = {(tv, o): a for tv, byoff in temporal.items()
              for o, a in byoff.items()}
    best_tv, best_t = max(flat_t, key=flat_t.get)
    best_c = max(ceiling, key=ceiling.get)
    # The literal offset-zero reading, at the first tau in the sweep, kept so
    # the strict version of equation (40) is still recoverable. None when zero
    # is not in the sweep; see run_t2.
    zero_t = temporal[f"{taus[0]}"].get("0")
    n_test_seg = int(np.sum(seg_test & (seg_label != UNLABELLED)))
    floor = float(np.bincount(seg_label[seg_test & (seg_label != UNLABELLED)]
                              ).max() / max(1, n_test_seg))

    return {
        "level": "segment",
        "accuracy_count": a_count,
        "accuracy_rate": a_rate,
        "accuracy_temporal": temporal,
        "accuracy_ceiling": ceiling,
        "best_offset_temporal": best_t,
        "best_tau_temporal": best_tv,
        "best_accuracy_temporal": flat_t[(best_tv, best_t)],
        "best_offset_ceiling": best_c,
        # Equation (40) two ways: at the literal offset zero, and with each
        # frame-based condition at its own best alignment. Reported together
        # because Q24 is open and the two readings differ.
        "tii_at_zero": (temporal_information_index(zero_t, a_count,
                                                   ceiling["0"])
                        if zero_t is not None and "0" in ceiling else None),
        "tii_at_best": temporal_information_index(
            flat_t[(best_tv, best_t)], a_count, ceiling[best_c]),
        "tii_at_best_using_rate": temporal_information_index(
            flat_t[(best_tv, best_t)], a_rate, ceiling[best_c]),
        # Equation (40)'s denominator, reported because the index alone cannot
        # be judged without it: a thin denominator makes a large index that
        # reads as a strong result and is seed noise.
        "tii_denominator_at_zero": (ceiling["0"] - a_count
                                    if "0" in ceiling else None),
        "tii_denominator_at_best": ceiling[best_c] - a_count,
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
        "n_features_temporal": int(n_features_temporal),
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
           tolerance=DEFAULT_TOLERANCE, label_tolerance_frames=1,
           min_separation=0.020, n_thresholds=49, features=None):
    """T3, boundary detection (proposal 4.3), on one operating point.

    The probe is binary logistic regression per frame — 6.2's rule for T1 and
    T3 — and its boundary posterior is turned into instants by `pick_peaks`,
    matched to the reference by `match_boundaries`, and scored by
    `score_boundaries`.

    **The detection threshold is chosen on the training split and applied
    unchanged to test.** It has to be chosen somehow: F-score at a single
    operating point is meaningless without one, and 4.3 does not name it.
    Choosing it on test would tune a free parameter against the number being
    reported, which is the thing C5 and the fairness constraints exist to
    prevent, and it would flatter every encoder by an amount depending on how
    peaked its posterior happened to be.

    `features=None` builds the equation (32) featurisation; passing an array
    instead scores any other frame-wise representation on the same task, which
    is how the R2 ceiling is obtained for T3.
    """
    t0 = time.time()
    labelset = LabelSet(corpus.labels)
    split = speaker_disjoint_split(corpus, test_fraction=test_fraction,
                                   seed=seed)

    if features is None:
        x, _, uid = build_dataset(trains, corpus, labelset, tau, hop, context)
    else:
        x = features
        _, _, uid = build_dataset({u.uid: None for u in corpus}, corpus,
                                  labelset, tau, hop, context, labels_only=True)
    train_mask = np.isin(uid, np.asarray(split.train, dtype=object))

    y = np.concatenate([
        boundary_labels(u, hop, tolerance_frames=label_tolerance_frames)
        for u in corpus])

    train_utts = [u for u in corpus if u.uid in set(split.train)]
    test_utts = [u for u in corpus if u.uid in set(split.test)]

    def fit_and_score(y_all, offset):
        y_o = np.concatenate([shift_labels(y_all[uid == u.uid], offset)
                              for u in corpus])
        keep = train_mask & (y_o != UNLABELLED)
        probe = LinearProbe(2, alpha=alpha).fit(x[keep], y_o[keep])
        posterior = probe.predict_proba(x)[:, 1]
        by_utt = dict(zip([u.uid for u in corpus],
                          _per_utterance(posterior, uid, corpus)))

        # Threshold chosen on train, applied to test. Swept over the observed
        # posterior range rather than [0, 1]: a probe whose posterior never
        # exceeds 0.3 would otherwise be scored entirely at zero detections.
        lo, hi = float(posterior.min()), float(posterior.max())
        grid = np.linspace(lo, hi, n_thresholds)[:-1]
        best_thr, best_f = grid[0] if grid.size else 0.5, -1.0
        for thr in grid:
            pred = [pick_peaks(by_utt[u.uid], hop, thr, min_separation)
                    for u in train_utts]
            f = score_boundaries(pred, [u.boundaries() for u in train_utts],
                                 tolerance)["f_score"]
            if f > best_f:
                best_thr, best_f = float(thr), f

        pred_test = [pick_peaks(by_utt[u.uid], hop, best_thr, min_separation)
                     for u in test_utts]
        scored = score_boundaries(pred_test,
                                  [u.boundaries() for u in test_utts],
                                  tolerance)
        scored["threshold"] = best_thr
        scored["train_f_score"] = best_f
        # The probe on its own, before any threshold or peak picker touches it.
        test_mask = np.isin(uid, np.asarray(split.test, dtype=object))
        valid = test_mask & (y_o != UNLABELLED)
        scored["frame_auc"] = frame_auc(posterior[valid], y_o[valid])
        return scored

    by_offset = {str(o): fit_and_score(y, o) for o in offsets}
    best = max(by_offset, key=lambda k: by_offset[k]["f_score"])

    # C3 — permuted training labels. A detector fitted on shuffled boundaries
    # must not localise anything, and if it does the split leaks.
    rng = np.random.default_rng(seed + 991)
    y_shuffled = y.copy()
    idx = np.flatnonzero(train_mask)
    y_shuffled[idx] = y[rng.permutation(idx)]
    shuffled = fit_and_score(y_shuffled, int(best))

    # C2 for a detection task — evenly spaced boundaries at the reference rate.
    # This is the strategy the R-value exists to penalise, so it is the floor
    # any reported F-score has to clear.
    baseline = score_boundaries(
        uniform_baseline([u.duration for u in test_utts],
                         [len(u.boundaries()) for u in test_utts]),
        [u.boundaries() for u in test_utts], tolerance)

    return {
        "task": "T3",
        "by_offset": by_offset,
        "best_offset": best,
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
        "shuffled_f_score": shuffled["f_score"],           # C3
        "shuffled_r_value": shuffled["r_value"],           # C3
        "shuffled_frame_auc": shuffled["frame_auc"],       # C3
        "uniform_baseline": baseline,                      # C2
        "split": split.as_dict(),                          # C4
        "lambda_events_per_s": (corpus_event_rate(trains, corpus)
                                if features is None else 0.0),
        "n_test_utterances": len(test_utts),
        "positive_frame_rate": float(np.mean(y[train_mask])),
        "settings": {"tolerance": tolerance,
                     "label_tolerance_frames": label_tolerance_frames,
                     "min_separation": min_separation,
                     "n_thresholds": n_thresholds,
                     "tau": tau, "hop": hop, "context": context,
                     "threshold_selected_on": "train"},
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


def _select_ridge_alpha(x, y, groups, alphas, seed):
    """Choose the ridge penalty on a speaker-disjoint split *inside* training.

    A single fixed penalty cannot serve every operating point. At the lowest
    budgets events are sparse, so many features have tiny variance,
    standardisation turns them into large spikes, and the context-stacked
    copies of them are near-collinear; a penalty negligible against a Gram
    diagonal of order n then leaves the small eigendirections unregularised and
    the predictions land hundreds of octaves out. Correlation survives that,
    being scale-free, which is exactly why RMSE has to be watched alongside it.

    Selected on held-out speakers within the training set, never on test:
    tuning a penalty against the reported number is the thing C5 and the
    fairness constraints exist to stop. Every condition is offered the same
    grid, which is what C4's "identical regularisation" requires — identical
    procedure, not identical value.
    """
    speakers = np.unique(groups)
    if len(speakers) < 2 or len(alphas) == 1:
        return float(alphas[0]), {}
    rng = np.random.default_rng(seed + 17)
    held = set(rng.permutation(speakers)[:max(1, len(speakers) // 3)].tolist())
    val = np.array([g in held for g in groups])
    if val.all() or not val.any():
        return float(alphas[0]), {}

    scores = {}
    for a in alphas:
        probe = RidgeProbe(alpha=float(a)).fit(x[~val], y[~val])
        err = probe.predict(x[val]) - y[val]
        scores[str(a)] = float(np.sqrt(np.mean(err ** 2)))
    best = min(scores, key=scores.get)
    return float(best), scores


def run_t2(corpus, trains, *, tau=0.005, hop=0.010, context=0,
           test_fraction=0.3, seed=0, alpha=1e-4, ridge_alpha=1.0,
           ridge_alphas=None, offsets=(-2, -1, 0), ref=SEMITONE_REF_HZ,
           features=None, min_frames=5):
    """T2, fundamental frequency contour (proposal 4.2), on one operating point.

    Ridge regression per frame on the voiced frames for the contour, and a
    separate binary probe for the voiced/unvoiced decision, which 4.2 asks be
    reported separately and which a regression cannot produce.

    Both the per-utterance and the pooled correlation are returned. The first
    is the headline; the gap between them is how much of the pooled figure is
    voice height rather than contour (Q32).
    """
    t0 = time.time()
    labelset = LabelSet(corpus.labels)
    split = speaker_disjoint_split(corpus, test_fraction=test_fraction,
                                   seed=seed)

    if features is None:
        x, _, uid = build_dataset(trains, corpus, labelset, tau, hop, context)
    else:
        x = features
        _, _, uid = build_dataset({u.uid: None for u in corpus}, corpus,
                                  labelset, tau, hop, context, labels_only=True)
    train_mask = np.isin(uid, np.asarray(split.train, dtype=object))
    test_mask = np.isin(uid, np.asarray(split.test, dtype=object))

    speaker_of = {u.uid: u.speaker for u in corpus}
    contours, voiced_flags, utt_ids = [], [], []
    for u in corpus:
        s, v = f0_targets(u, hop, ref=ref)
        contours.append(s)
        voiced_flags.append(v)
        utt_ids.append(np.full(len(s), u.uid, dtype=object))
    contour = np.concatenate(contours)
    voiced = np.concatenate(voiced_flags)
    utt = np.concatenate(utt_ids)

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

    def evaluate(offset, shuffle=False):
        s, v, ok = targets_at(offset)
        fit_rows = train_mask & ok & v & ~np.isnan(s)
        test_rows = test_mask & ok & v & ~np.isnan(s)
        y = s.copy()
        if shuffle:
            rng = np.random.default_rng(seed + 991)
            idx = np.flatnonzero(fit_rows)
            y[idx] = s[rng.permutation(idx)]

        chosen, alpha_scores = (
            _select_ridge_alpha(x[fit_rows], y[fit_rows],
                                np.array([speaker_of[u] for u in utt[fit_rows]]),
                                ridge_alphas, seed)
            if ridge_alphas else (ridge_alpha, {}))
        probe = RidgeProbe(alpha=chosen).fit(x[fit_rows], y[fit_rows])
        pred = probe.predict(x[test_rows])
        truth = s[test_rows]

        per_utt, excluded, n_scored = _per_utterance_pearson(
            pred, truth, utt[test_rows], min_frames=min_frames)
        pooled = (float(np.corrcoef(pred, truth)[0, 1])
                  if pred.size > 1 and np.std(pred) > 0 else float("nan"))
        rmse = float(np.sqrt(np.mean((pred - truth) ** 2)))
        # The floor: predict the training mean for every frame. Its RMSE is the
        # test contour's spread about that mean, and any probe not beating it
        # has learned nothing about f0.
        floor_rmse = float(np.sqrt(np.mean((truth - probe.intercept) ** 2)))

        return {"pearson_per_utterance": per_utt, "pearson_pooled": pooled,
                "rmse_semitones": rmse, "floor_rmse_semitones": floor_rmse,
                "n_test_frames": int(test_rows.sum()),
                "n_utterances_scored": n_scored,
                "n_utterances_excluded": excluded,
                "ridge_alpha_chosen": chosen,
                "ridge_alpha_validation_rmse": alpha_scores,
                "probe_settings": probe.settings}

    by_offset = {str(o): evaluate(o) for o in offsets}
    best = max(by_offset,
               key=lambda k: (by_offset[k]["pearson_per_utterance"]
                              if not np.isnan(
                                  by_offset[k]["pearson_per_utterance"])
                              else -np.inf))
    shuffled = evaluate(int(best), shuffle=True)

    # Voicing, reported separately per 4.2. All valid frames, not just voiced.
    s0, v0, ok0 = targets_at(int(best))
    vp = LinearProbe(2, alpha=alpha).fit(x[train_mask & ok0],
                                         v0[train_mask & ok0].astype(np.int64))
    v_true = v0[test_mask & ok0].astype(np.int64)
    voicing_acc = float(np.mean(vp.predict(x[test_mask & ok0]) == v_true))
    voicing_floor = float(max(v_true.mean(), 1.0 - v_true.mean()))

    return {
        "task": "T2",
        "by_offset": by_offset,
        "best_offset": best,
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
             if "0" in by_offset else None),
        "shuffled_pearson_per_utterance":
            shuffled["pearson_per_utterance"],                  # C3
        "shuffled_pearson_pooled": shuffled["pearson_pooled"],  # C3
        "voicing_accuracy": voicing_acc,
        "voicing_floor": voicing_floor,                         # C2
        "split": split.as_dict(),                               # C4
        "lambda_events_per_s": (corpus_event_rate(trains, corpus)
                                if features is None else 0.0),
        "n_utterances_scored": by_offset[best]["n_utterances_scored"],
        "n_utterances_excluded": by_offset[best]["n_utterances_excluded"],
        "ridge_alpha_chosen": by_offset[best]["ridge_alpha_chosen"],
        "settings": {"tau": tau, "hop": hop, "context": context,
                     "ridge_alpha": ridge_alpha,
                     "ridge_alphas": list(ridge_alphas) if ridge_alphas else None,
                     "ridge_alpha_selected_on": "held-out speakers within train",
                     "semitone_ref_hz": ref,
                     "min_frames_per_utterance": min_frames,
                     "headline": "pearson_per_utterance"},
        "seconds": time.time() - t0,
    }
