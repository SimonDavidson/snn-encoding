# Spike Encoding for a Joint Audio-Visual Event Dataset

**A comparative study of candidate encodings for the MANCHESTER Dataset**

*Simon Davidson and Oliver Rhodes | Version 2, incorporating the decisions of 20 August 2026*


---


## 1. Purpose and status of this document

This document sets out a proposed programme of work leading to (a) a justified choice of spike encoding for the audio component of the corpus that is to be released alongside the DVS event data, and (b) a journal paper describing how that choice was made. It is a proposal, not a plan of record. Its purpose is to let us agree the scope, the target tasks, the candidate encodings and the evaluation methodology before any implementation begins, so that the study we run is the study we both intended.

Version 1 of this document ended with fifteen open decisions. Those were put to Oliver and answered on 20 August 2026; Section 10 records the outcomes and the five items that remain outstanding. Four changes to the study follow from those answers and are noted where they occur: the probe battery has been reduced from four tasks to three, with speaker identification replaced by fundamental frequency estimation (Section 4.2); information-theoretic cost metrics have been added (Section 6.3); the Spiketrum encoder is marked provisional pending direct contact with its authors (Section 5.7); and the risk that speaker diversity in the corpus degrades forced alignment has been added to the stage two plan (Section 8.2).

The document is written to be self-contained. Terminology and acronyms are expanded on first use, algorithms are described from first principles, and a glossary is given in Appendix A. Where a claim rests on a paper that has not been read in full, this is stated explicitly rather than glossed over.


---


## 2. Background


### 2.1 The situation

The MANCHESTER Dataset comprises several hundred spoken sentences from over fifty speakers, recorded with a simultaneous visual record captured using a DVS (Dynamic Vision Sensor) event camera. Speakers are English-speaking but are not restricted by background or nationality, so the corpus carries considerably more accent variation than the standard read-speech benchmarks; some sentences are questions, so intonational variety is present. A DVS is a camera whose pixels report changes in log light intensity asynchronously, rather than sampling a full frame at a fixed rate; its output is a stream of events rather than a video. There is a contractual obligation to release this data in spike-encoded form as a project output. The two modalities are to be released together as a single set.

The choice of audio spike encoding is entirely open. Because the release is intended to serve a range of application developers whose requirements are not known in advance, the encoding must be broad enough, and carry enough information, to support applications we have not anticipated. There is no fixed release date, which means the encoding can be chosen on evidence rather than expedience.

The scientific objective, stated more sharply, is to determine whether spike-based representation offers any engineering advantage over conventional dense representations for speech, and to establish this either way. A result showing that spikes offer no advantage at matched cost is a legitimate and publishable outcome, provided the comparison is rigorous. This matters for the design below, because it means the study should be constructed so that it yields an interpretable result regardless of which way the numbers fall.


### 2.2 Why "maximise information content" is not yet a specification

The natural statement of the goal is that the encoding should maximise the audio information content it carries. As written this is not yet a specification, and it is worth being precise about why, because the resolution determines the entire evaluation design.

If information content is taken to mean mutual information between the spike train and the waveform, then the optimum is a lossless codec: the encoding that maximises it is the one that allows the audio to be reconstructed exactly. That encoding exists, it is uninteresting, and it spends the entire event budget on acoustic detail that no downstream application uses - room reverberation, microphone colouration, the precise phase of the carrier in high-frequency bands. It would also, incidentally, make the released spike data functionally equivalent to releasing the audio itself.

What is actually wanted is closer to a sufficient statistic: a representation that retains everything a downstream user needs to perform the tasks they care about, and as little as possible besides. This is a task-relative criterion, and it cannot be evaluated without naming the tasks. The difficulty is that the tasks are not known in advance.

The resolution proposed here is to evaluate not against a list of anticipated applications, which cannot be complete, but against a small battery of probe tasks chosen because they make opposing demands on the encoding. If an encoding serves tasks at opposite corners of the demand space, it is reasonable to argue that it serves the applications that lie between them. Breadth is then demonstrated by spanning rather than by enumeration, and the argument is one a reviewer can check. Section 4 develops this.


### 2.3 The source-filter model of speech

The choice of probe tasks below rests on a standard idealisation of speech production, which is worth stating because it is what makes the opposing-demands argument concrete rather than rhetorical.

In the source-filter model, speech is treated as the output of an excitation source passed through a linear filter. For voiced sounds - vowels, nasals, voiced consonants - the source is the quasi-periodic pulse train produced by the vibrating vocal folds, whose repetition rate is the fundamental frequency, written F~0~. For unvoiced sounds such as fricatives, the source is turbulent noise generated at a constriction. The filter is the acoustic transfer function of the vocal tract above the larynx, whose resonances are called formants and are conventionally numbered F~1~, F~2~, F~3~ in ascending frequency.

In the frequency domain the model is multiplicative, so on a log-magnitude axis it is additive:


> log |S(f)| = log |U(f)| + log |H(f)| + log |R(f)|   (1)

where U is the source spectrum, H the vocal tract transfer function and R the radiation characteristic at the lips. The practical consequence is that source and filter contributions occupy different parts of the representation and can, in principle, be separated.

Two further facts drive the argument. First, which phone is being produced is very largely a property of the filter: it is the formant pattern and its trajectory over time that distinguishes one vowel from another. Second, who is speaking is very largely a property of the source and of the overall scale of the tract. Treating the vocal tract as a uniform tube of length L closed at the glottis and open at the lips, the resonances fall at


> F~k~ = (2k - 1) c / (4L),   k = 1, 2, 3, ...   (2)

with c the speed of sound. Tract length therefore scales all formants by a common multiplicative factor, which is a uniform translation along a logarithmic frequency axis. A longer tract shifts the whole pattern down; a shorter one shifts it up. Since adult vocal tract lengths vary by roughly twenty-five per cent across a population, this is a large effect, and it is a principal carrier of speaker identity along with F~0~.

This yields a clean statement of the opposition. A representation good for identifying the phone should be invariant to translation along the log-frequency axis, because that translation is speaker change rather than phone change. A representation good for identifying the speaker should be sensitive to exactly that translation. No single set of readout channels can be simultaneously optimal for both.


### 2.4 The dissociation result, and its extension to phones

Earlier work in this project established the same opposition empirically for digit identity against speaker identity, and concluded that the two require near-opposite encoders. Restated briefly, and with the internal framework references removed:

- Digit (and by extension phone) identity is carried by formant trajectories; benefits from adaptation, which emphasises changes and suppresses sustained level; and calls for invariance to shift along the log-frequency axis.
- Speaker identity is carried by F~0~ and by vocal tract scaling; is harmed by adaptation, which suppresses precisely the sustained periodicity cues that identify a voice; requires sub-millisecond timing precision to represent phase locking to the glottal period; and calls for sensitivity, not invariance, to log-frequency shift.
The recommendation that followed was a factored encoder: separate channel groups for periodicity and for envelope, with task-specific selection of readout channels, so that the disentangling is done by the physics of production rather than learned from data. That recommendation carries over to the present problem without modification, because phone identity sits in the same class of quantity as digit identity. It also does useful work here beyond the science: a factored release format lets a downstream user select channel subsets rather than re-encode from audio they do not have, which is the only way one release can serve users with different requirements.


### 2.5 What a spike encoder is, and what has to be decided

For the purposes of this document, a spike encoder is a map from a sampled waveform to a set of discrete events. Each event is a tuple


> e~k~ = (c~k~, t~k~, p~k~)   (3)

where c~k~ identifies the channel that fired, t~k~ is the time of firing, and p~k~ is an optional polarity in {+1, -1}. There is no amplitude: an event either occurs or it does not. All information is carried by which channel fires, when, and with what sign.

Designing an encoder therefore requires four decisions, and the candidate schemes in Section 5 differ from one another along these axes rather than along any single dimension of quality:

1. Channel definition. How is the signal decomposed before events are generated? Almost universally this is a bank of bandpass filters, but the number of channels, their centre frequencies and their bandwidths are all free.
2. Event generation rule. Given a channel signal, what condition triggers an event? This is where the schemes genuinely diverge: integrate-and-fire, threshold crossing of an accumulated change, crossing of a temporally bandpassed derivative, phase locking to the carrier, or a sparse decomposition.
3. Rate control. Every encoder has at least one parameter that trades event count against fidelity. Identifying it explicitly is essential, because the comparison in Section 6 is conducted at matched event rate and is meaningless otherwise.
4. Timestamp resolution. Events must be stored with finite temporal precision. This is a format decision, but it is also an experimental variable, because encoders that carry information in precise timing benefit from finer resolution while rate-like encoders do not.

### 2.6 Relation to the DVS event model

A DVS pixel emits an event when the log intensity at that pixel has changed by more than a fixed contrast threshold since the last event at that pixel, with the polarity of the event giving the sign of the change. Events are transmitted in the Address-Event Representation (AER) format, in which each event is a tuple of address, timestamp and polarity - structurally identical to equation (3).

This creates an opportunity that is specific to this project. One of the candidate audio encoders below, the send-on-delta scheme (E2), is exactly the DVS pixel model applied to the log-compressed envelope of a filterbank channel rather than to the log intensity at a pixel. If that scheme lands anywhere near the Pareto front of the comparison, both modalities can be released under a single event abstraction, with one timestamp convention, one polarity convention and one file format. "One event model, two sensors, one library" is a materially stronger proposition for a dataset release than two unrelated formats bundled together, and it gives a principled reason to prefer E2 even at some measurable cost in task accuracy - a cost the study is designed to quantify rather than assume away.

How hard a constraint this should be is a decision for Oliver; it appears in Section 10.


### 2.7 Prior art and what would be new here

Comparative evaluations of spike encoding schemes exist. A benchmark of encoding techniques for time-varying signals has been published using the Free Spoken Digit dataset and a human-activity dataset, and a more recent comparative benchmark addresses environmental sound classification using Moving Window, Step Forward and Threshold Adaptive encodings applied to mel-spectrogram channels. Broader surveys of encoding techniques for signal processing in spiking networks are also available. These establish that the comparison genre is recognised and that several of our candidates have standard names in the literature, which we should adopt where they exist.

Closer to home, the Spiketrum encoder developed at Manchester by Alsakkal and Wijekoon is a general-purpose spike-coding algorithm with precisely controllable spike rate and demonstrated signal reconstruction, implemented on both FPGA and ASIC. It is directly relevant, it is in the same institution, and it should be in the comparison. A caveat is recorded in Section 5.7.

Against that background, the contribution claimed here would be the combination of four things, none of which is individually novel but which have not to our knowledge been brought together:

- Evaluation against a battery of tasks selected for opposing demands, rather than a single classification task, with breadth argued by spanning.
- Comparison strictly on Pareto fronts at matched event budget, rather than at single hand-chosen operating points.
- Separation of information present in a representation from information accessible in it, via paired linear and nonlinear probes.
- Application at the phone level, with the resulting choice carried through to an actual dataset release paired with a second, natively event-based modality.

---


## 3. What is being optimised: a working criterion

Collecting the argument of Section 2 into something implementable. Let E denote an encoder with rate parameter r, let T be the set of probe tasks defined in Section 4, and let A~T~(E, r) be the accuracy achieved on task T from the encoding produced by E at rate parameter r, using the fixed decoding protocol of Section 6. Let Λ(E, r) be the resulting mean event rate in events per second.

For each encoder and each task, sweeping r traces a curve in the plane of event rate against accuracy. The upper-left envelope of that curve is the Pareto front for that encoder and task: the set of operating points not dominated by any other point of the same encoder.

The criterion is then stated in three parts, in decreasing order of strength:

1. An encoder is preferred if its Pareto front dominates those of the alternatives on all tasks in T simultaneously. This is the clean outcome and may well not occur.
2. Failing that, the encoders are characterised by where and by how much they trade one task against another, and the choice for release is made explicitly against that trade-off, with the cost stated.
3. In either case a single parameter setting must be nominated for the release, because we release one encoding. The loss incurred by that single compromise setting relative to the per-task optima is itself a reportable quantity, and arguably the most useful number in the paper for anyone deciding whether to use the dataset.
Two further quantities are reported alongside accuracy rather than optimised. The first is the accessibility gap of Section 6.2, which distinguishes information that is present in a representation from information a user can actually get at with a simple readout. The second is coding efficiency in the information-theoretic sense of Section 6.3 - how much task-relevant information each event carries - which was added at Oliver's request in place of the hardware energy measurement now out of scope.


---


## 4. The probe battery

Three tasks are proposed. They are chosen not because they are the applications we expect users to build, but because they place demands on the encoding that pull in different directions. Each is defined below with its metric and the demand it imposes.

Version 1 of this document proposed four tasks, of which the second was speaker identification. That task has been replaced by fundamental frequency contour estimation, for reasons set out in Section 4.2, and the fourth prosodic task has been absorbed into it. The result is a smaller and cheaper battery that spans the same demand space.


### 4.1 T1 - Phone classification

Given the encoded audio, identify which phone is being produced. A phone is a single speech sound; a phoneme is the abstract category to which phones belong in a given language. TIMIT supplies hand-placed phone boundaries and labels, so on that corpus the task can be run in two forms: frame-level classification, in which every analysis frame is assigned a phone label, and segment-level classification, in which each labelled segment is classified as a whole.

Metric: frame-level accuracy, and phone error rate (PER) where a sequence decoder is used. PER is the phone-level analogue of word error rate - the reference and hypothesis phone sequences are aligned by minimum edit distance, and the total of substitutions, deletions and insertions is divided by the number of phones in the reference. Following near-universal convention on TIMIT, the 61-symbol label set is collapsed to 39 for scoring, and this must be stated whenever a figure is quoted.

Demand imposed: resolution of spectral shape, specifically the pattern and movement of formants; tolerance of translation along the log-frequency axis; benefit from adaptation. In the terms of Section 2.3, T1 probes the filter.


### 4.2 T2 - Fundamental frequency contour

Given the encoded audio, recover the fundamental frequency frame by frame, together with the voiced/unvoiced decision. The reference contour is extracted from the clean audio by a standard pitch tracker before encoding; the probe never sees the audio, only the events.

Metric: Pearson correlation between estimated and reference contour over voiced frames, and root-mean-square error in semitones, semitones rather than hertz because the perceptual and physiological scale is logarithmic and an error of 10 Hz means something quite different at 100 Hz and at 300 Hz. Voicing decision accuracy is reported separately, since an encoder may preserve periodicity well while representing its onset poorly.

Demand imposed: fidelity in the low-frequency channels where F~0~ and its low harmonics lie; sub-millisecond timing precision, since periodicity is carried by phase locking to the glottal cycle; sensitivity to absolute frequency scale rather than invariance to it; and active harm from the adaptation that helps T1, since adaptation suppresses exactly the sustained periodicity this task depends on. T2 probes the source, and sits at the opposite corner of the demand space from T1.

Why this task rather than speaker identification. The two probe the same property of an encoder - whether source information survives it - and in version 1 the role was filled by speaker identification. Fundamental frequency estimation is the better instrument for four reasons. It requires no labels, since the reference is extracted automatically, so it runs on TIMIT and on the MANCHESTER Dataset without additional annotation. It permits speaker-disjoint splits like every other task, removing the awkward asymmetry that speaker identification forced on the evaluation protocol. It is a regression rather than a closed-set classification, so its metric does not depend on how many speakers happen to be in the corpus and is therefore comparable across the two stages. And it bears directly on the intonation and prosody questions flagged as being of future interest, which the release must not foreclose.

One caveat requiring the same treatment as forced alignment in Section 8.2: an automatically extracted contour is a proxy reference, not ground truth. Pitch trackers make octave errors and disagree at voicing boundaries. Two trackers should be run and their disagreement quantified, giving a measured noise floor for the task before any encoder is judged against it.


### 4.3 T3 - Boundary and onset detection

Given the encoded audio, locate the instants at which one phone gives way to the next. On TIMIT the hand-placed boundaries provide ground truth directly. A simpler variant, voice activity detection - determining when speech is present at all - can be substituted or added if segment boundaries prove too demanding a first target.

Metric: precision, recall and F-score at a fixed tolerance, conventionally twenty milliseconds. The R-value, which penalises the trivial over-segmentation strategies that inflate F-score, should be reported alongside.

Demand imposed: temporal precision at the scale of tens of milliseconds; faithful representation of envelope transients; robustness of onset representation across the frequency range. This demand is largely orthogonal to both T1 and T2, since an encoder can resolve spectral shape or periodicity well while smearing the timing of changes, or the reverse.


### 4.4 The spanning argument

The three tasks divide the demand space along axes that are close to independent. In the terms of the source-filter model of Section 2.3, T1 probes the filter and T2 probes the source, and these are the two factors the model separates. T3 probes neither, being concerned with the timing of change rather than with the content of either factor.

Cutting the same set a different way: T1 requires invariance to translation along the log-frequency axis while T2 requires sensitivity to it. T1 benefits from adaptation while T2 is harmed by it. T2 requires timing precision below the millisecond, T3 at tens of milliseconds, and T1 integrates over the length of a phone. No single parameter setting is optimal for all three, which is precisely what makes the battery informative: an encoder that performs acceptably across all of them has been shown to preserve spectral detail, absolute frequency scale and fine timing simultaneously.

That is the substance of the claim that such an encoder is broad. It is not a proof that it serves every possible application, and the paper should not claim more, but it is a checkable argument and considerably stronger than asserting breadth from a list of anticipated use cases.

Whether the battery genuinely spans in this way is not assumed. Preliminary experiment P2 in Section 7.2 tests it directly, and constitutes a decision gate before the main study proceeds.


### 4.5 Speaker identity as an optional diagnostic

Speaker identification is not a target application for the MANCHESTER Dataset and is not a probe task here. It remains available as a diagnostic at almost no cost, since it requires only an additional readout trained on event data that has already been encoded for the other tasks.

It is worth running at least once, for two reasons. It is the natural check on whether an encoding chosen for T1 has in fact achieved the log-frequency shift invariance that phone identity wants, since an encoder that has genuinely discarded vocal tract scale will support speaker identification poorly. And the release is irreversible: the MANCHESTER Dataset comprises over fifty identifiable speakers recorded with synchronised video of their faces, so knowing how much speaker information the released encoding retains is worth the hour it costs, whether or not the figure appears in the paper. If it does appear, the factored channel-group structure of Section 2.4 is the natural response, since it allows a user to select channel subsets rather than requiring us to re-encode.


---


## 5. Candidate encoding schemes

Six candidate encoders are proposed for evaluation, together with one third-party encoder and two reference points that are not candidates but fix the scale of the results. They are ordered along a rough axis from rate-like to timing-like: early schemes carry information mainly in how many events occur, later ones mainly in when they occur. That ordering is deliberate, because it is the axis that preliminary experiment P1 is designed to probe.

One class of encoder is deliberately excluded: encoders whose parameters are trained end to end against a task objective. Such encoders would very likely win a phone-classification comparison, and there is recent work demonstrating exactly that. But they bake a particular task into the release, which is the opposite of what a general-purpose library requires, and they make the resulting format dependent on a training run rather than on a specification. This exclusion is a decision open to challenge and appears in Section 10.


### 5.0 The common front end

All candidates except E7 share a common first stage, so that differences between them are attributable to the event generation rule rather than to incidental differences in filtering. The stage is a gammatone filterbank, the standard computational approximation to the frequency selectivity of the basilar membrane. Channel c has impulse response


> g~c~(t) = a t^n-1^ exp(-2 π b~c~ t) cos(2 π f~c~ t + φ~c~),   t ≥ 0   (4)

with order n = 4 and bandwidth parameter b~c~ = 1.019 ERB(f~c~), where the equivalent rectangular bandwidth of a filter centred at f hertz is given by the Glasberg and Moore formula


> ERB(f) = 24.7 (0.00437 f + 1)   (5)

Centre frequencies are placed equally along the ERB-rate scale


> E(f) = 21.4 log~10~(0.00437 f + 1)   (6)

between f~min~ and f~max~, which for 16 kHz audio would conventionally be 50 Hz and 8000 Hz. The number of channels N~ch~, the frequency limits, and the choice of ERB against mel against linear spacing are all swept parameters rather than fixed choices; see Section 6.6.

The subband signal in channel c is the convolution


> x~c~(t) = (g~c~ * x)(t)   (7)

and its envelope is obtained either from the magnitude of the analytic signal, using the Hilbert transform H,


> e~c~(t) = | x~c~(t) + j H{x~c~}(t) |   (8)

or, more cheaply and more plausibly as a model of hair cell transduction, by half-wave rectification followed by lowpass filtering:


> e~c~(t) = LPF~fcut~ ( max(x~c~(t), 0) )   (9)

A compressive nonlinearity is then applied, reflecting the roughly logarithmic relation between physical intensity and perceived loudness and the very wide dynamic range of speech:


> u~c~(t) = log(e~c~(t) + ε)     or     u~c~(t) = e~c~(t)^0.3^   (10)

with ε a small constant preventing a singularity in silence. The choice between logarithmic and power-law compression is a swept parameter. Note that E5 alone operates on the subband waveform x~c~(t) rather than on the envelope, since its entire purpose is to represent the carrier that the envelope discards.


### 5.1 E1 - Leaky integrate-and-fire (the rate-like anchor)

The most widely used spike encoder, and the one against which the others should be understood. Each channel drives a leaky integrate-and-fire (LIF) neuron. The membrane potential V~c~ integrates the input and decays exponentially toward rest; when it reaches a threshold the neuron emits an event and the potential is reset:


> τ~m~ dV~c~/dt = -(V~c~(t) - V~rest~) + R I~c~(t),    I~c~(t) = g u~c~(t)   (11)

In discrete time with step Δ t, writing β = exp(-Δ t / τ~m~) and using Θ for the Heaviside step function, the update is


> V~c~[n] = β V~c~[n-1] (1 - s~c~[n-1]) + (1 - β) g u~c~[n]   (12)


> s~c~[n] = Θ( V~c~[n] - θ )   (13)

where s~c~[n] is one if an event occurs at step n and zero otherwise. Equation (12) implements a hard reset to zero after an event; a soft reset, subtracting θ rather than zeroing, is the alternative and preserves information about how far the potential overshot. A refractory period Δ~ref~ imposes a minimum interval between successive events in a channel and hence a hard ceiling on channel firing rate.

For a constant input the firing rate is approximately proportional to input amplitude above threshold, so the code is close to a rate code: information resides principally in how many events a channel produces, only weakly in exactly when. All events have the same polarity, so no polarity bit is required.

Rate parameter: θ. Increasing the threshold reduces the event rate approximately in inverse proportion. Secondary parameters τ~m~ and Δ~ref~.

Predicted behaviour: solid on T1, since spectral shape survives a rate code well; poor on T2, since phase information is discarded at the envelope stage; poor on T3 relative to the change-based encoders, since onsets are not privileged over sustained regions. Included principally because it is the standard against which any claim of temporal coding must be made.


### 5.2 E2 - Send-on-delta (the DVS-symmetric scheme)

Rather than integrating the signal, this scheme tracks it. A reference level r~c~ is maintained per channel, and an event is emitted whenever the compressed envelope has moved a fixed distance C from that reference, with the reference then advanced by C in the direction of travel:


> if u~c~(t) - r~c~ ≥ C :  emit (c, t, +1),  r~c~ ← r~c~ + C   (14)


> if r~c~ - u~c~(t) ≥ C :  emit (c, t, -1),  r~c~ ← r~c~ - C   (15)

This is delta modulation, and it is known in the spiking literature as Step Forward encoding. Because u~c~ is a log-compressed quantity, the condition is a fixed-contrast condition: an event marks a fixed multiplicative change in envelope amplitude, not a fixed additive one. That is precisely the DVS pixel rule with log intensity replaced by log subband envelope, which is what makes this scheme the candidate for format unification with the visual modality.

Two properties make it attractive independently of that. First, the reference is a running reconstruction of the signal, and the reconstruction error is bounded by construction:


> | u~c~(t) - r~c~(t) | < C   for all t   (16)

Second, the number of events produced over an interval has a closed form in terms of the total variation of the compressed envelope:


> N~c~ = (1/C) ∫ | du~c~/dt | dt   (17)

so the rate parameter has an exact and monotonic relationship to event count, which makes matched-budget comparison straightforward to arrange. Note that these two properties are in tension with the privacy considerations of Section 3: a scheme with a guaranteed reconstruction bound is, by that very guarantee, one from which the audio can be substantially recovered.

An implementation choice deserves flagging. Advancing the reference by exactly C, as written above, keeps all reference values on a fixed lattice and makes reconstruction exact to within one quantisation step; setting the reference to the current signal value instead lets it drift off the lattice but tracks fast transients more responsively. The DVS convention is closer to the latter. Both variants should be implemented and the choice treated as a swept parameter.

Rate parameter: the contrast threshold C, with event rate proportional to 1/C by equation (17). Secondary parameter Δ~ref~.

Predicted behaviour: strong on T3, since events are generated exactly where the signal changes; adequate on T1; poor on T2. Its principal claim is format symmetry with the DVS data, not peak accuracy on any task.


### 5.3 E3 - Temporal contrast with onset and offset channels

A change-based scheme like E2, but bandpass rather than integrating in its response to change. Two exponential lowpass filters with different time constants are applied to the compressed envelope, and their difference taken:


> y~c~^fast^[n] = α~f~ y~c~^fast^[n-1] + (1 - α~f~) u~c~[n]   (18)


> y~c~^slow^[n] = α~s~ y~c~^slow^[n-1] + (1 - α~s~) u~c~[n]   (19)


> d~c~[n] = y~c~^fast^[n] - y~c~^slow^[n]   (20)

with α~f~ = exp(-Δ t / τ~f~), α~s~ = exp(-Δ t / τ~s~) and τ~s~ > τ~f~. This is a difference of exponentials in time, the temporal analogue of a difference-of-Gaussians in space. Events are emitted on threshold crossings of d~c~, separately for the two signs, subject to a refractory period:


> ON event if d~c~[n] ≥ θ~+~ ;   OFF event if d~c~[n] ≤ -θ~-~   (21)

The difference from E2 is worth being precise about, because the two are easily conflated. E2 accumulates: a slow ramp of sufficient total extent will eventually generate events no matter how gradual it is. E3 is bandpass: a ramp slower than τ~s~ produces no response at all, because both filters track it equally and their difference stays near zero. E3 is therefore silent during steady state regardless of level, and responds only to changes fast relative to its slow time constant. This makes it a closer model of the onset-sensitive cells found in the cochlear nucleus, and it produces markedly sparser output on sustained sounds.

Separate ON and OFF channels can be exposed to downstream users as distinct channel indices rather than as a polarity bit; this doubles the channel count but removes the need for a polarity field and lets a user select only onsets if that is all they need.

Rate parameter: θ = θ~+~ = θ~-~, with the asymmetric case available as a secondary axis. Secondary parameters τ~f~, τ~s~, Δ~ref~.

Predicted behaviour: strongest of the candidates on T3; competitive on T1, since phone changes are exactly transitions; poor on T2, possibly very poor, since a scheme that is silent during steady state discards precisely the sustained periodicity that F~0~ estimation depends on. If that prediction holds it is a clean demonstration that the battery spans.


### 5.4 E4 - Adaptive-threshold LIF

E1 augmented with spike-frequency adaptation, the mechanism by which real neurons reduce their firing rate under sustained stimulation. The threshold is made dynamic: each event raises it by a fixed increment, and it decays back toward baseline with its own time constant.


> θ~c~[n] = θ~0~ + a~c~[n]   (22)


> a~c~[n] = ρ a~c~[n-1] + Δ~a~ s~c~[n-1],    ρ = exp(-Δ t / τ~a~)   (23)

with equations (12) and (13) otherwise unchanged, substituting θ~c~[n] for the fixed θ. This is the adaptive LIF, or ALIF, neuron used by Bittar and Garner and by Yin and colleagues, and it is the mechanism most often credited when spiking networks outperform their non-adaptive counterparts on speech.

Its functional effect is a first-order highpass applied to the firing rate: transients pass, sustained drive is progressively suppressed. This is an implicit form of the invariance T1 wants, since a speaker-dependent sustained level is attenuated while the phone-dependent transitions are preserved. By the same token it is expected to be actively harmful for T2. E4 is thus the sharpest test in the set of the claimed dissociation, and the encoder for which the predicted results are most specific.

Rate parameter: θ~0~. The adaptation strength Δ~a~ and time constant τ~a~ are swept as a separate axis rather than folded into the rate parameter, since the interesting result is how accuracy on T1 and T2 moves in opposite directions as adaptation strength increases.


### 5.5 E5 - Phase-locked fine structure

The only candidate that represents the carrier rather than the envelope. Below roughly one to four kilohertz, auditory nerve fibres fire at a preferred phase of the stimulus waveform; this phase locking is the principal mechanism by which the auditory system represents periodicity, and hence F~0~.

The scheme operates on the subband waveform x~c~(t). Half-wave rectification and compression give an instantaneous drive


> z~c~(t) = [ max(x~c~(t), 0) ]^γ^   (24)

from which events are generated either stochastically, as an inhomogeneous Poisson process with saturating intensity


> λ~c~(t) = λ~max~ z~c~(t) / (z~c~(t) + z~0~)   (25)

or deterministically, by emitting an event at each upward zero crossing of x~c~(t) for which the envelope exceeds a threshold, subject to a refractory period. The stochastic form is the more faithful model; the deterministic form is cheaper and gives more reproducible event counts, which is convenient for budget matching.

The fidelity of phase locking is quantified by vector strength, defined over the N event times in a channel as


> VS~c~ = (1/N) | Σ~k~ exp( j 2 π f~c~ t~k~ ) |   (26)

which is one for perfect locking and zero for events uniformly distributed in phase. Vector strength should be reported as a diagnostic for this encoder, since it directly measures the property the scheme exists to preserve, and its degradation under the jitter operator of Section 7.2 makes an interpretable check on timestamp resolution.

Biological phase locking degrades above a few kilohertz, and this should be modelled: above a cutoff f~lock~, channels revert to envelope-driven behaviour as in E1. The value of f~lock~ is a swept parameter, and the sweep is informative in itself, since it directly controls how much speaker information the encoding retains.

Rate parameter: λ~max~ in the stochastic form, or the envelope threshold in the deterministic form. Secondary parameters γ, Δ~ref~, f~lock~.

Predicted behaviour: much the strongest on T2, by a wide margin; not obviously better than E1 on T1, since it adds carrier detail that phone identity does not need; expensive, since phase locking at kilohertz rates implies high event counts in exactly the channels where events are cheapest to generate. This makes it the encoder most likely to be dominated at matched budget despite carrying the most information - an outcome worth stating clearly if it occurs, since it is a concrete illustration of why information content alone is the wrong criterion.

E5 is also the encoder that most concerns the dissemination question. If it wins on breadth, the release will retain a great deal of speaker information, and the factored channel-group structure of Section 2.4 becomes necessary rather than merely desirable.


### 5.6 E6 - Time-to-first-spike

The extreme temporal case, and the sparsest scheme in the set. The signal is divided into frames of length T~f~ with hop H. Within each frame, each channel emits at most one event, at a latency that decreases with channel energy. Taking the energy in frame m as


> E~c~[m] = ∫ e~c~(t)^2^ dt   over frame m   (27)

the event time may be set by a direct logarithmic mapping


> t~c~[m] = m H + T~f~ ( 1 - (log E~c~[m] - log E~min~) / (log E~max~ - log E~min~) )   (28)

clipped to the frame, or, more principled, by the latency of a LIF neuron under constant current I proportional to E~c~[m], which has the closed form


> t~c~ = τ~m~ log( I / (I - θ) )   for I > θ   (29)

Channels whose energy falls below E~min~ emit nothing, which is the mechanism by which the scheme is sparsified. The event budget is bounded exactly at N~ch~/H events per second, which makes E6 uniquely predictable in cost - a genuine practical virtue for a released format.

All information resides in timing: the code is the exact inverse of E1, carrying nothing in event count. This makes the pair (E1, E6) the cleanest available test of whether timing buys anything at matched budget, which is the central engineering question of the project.

Rate parameter: E~min~, and secondarily the hop H.

Predicted behaviour: competitive on T1 at very low event rates, since a frame-wise spectral snapshot is close to what a conventional filterbank feature vector provides; poor on T3, since temporal resolution is quantised to the frame; poor on T2. Its interest lies in the low-rate end of the Pareto front, where it may dominate everything else.


### 5.7 E7 - Spiketrum (third-party)

Spiketrum is a general-purpose spike-coding algorithm developed at Manchester by Alsakkal and Wijekoon, with published FPGA and ASIC implementations and reported application to auditory perception tasks. From the published abstracts it is a sparse decomposition method in the matching pursuit family: the signal is approximated by iteratively selecting, from a time-frequency dictionary of atoms, the atom best correlated with the current residual, emitting an event identifying that atom and its time, and subtracting its contribution. Generically,


> (c~k~, t~k~) = argmax | ⟨ r^(k-1)^ , g~c,t~ ⟩ |   (30)


> r^(k)^ = r^(k-1)^ − ⟨ r^(k-1)^ , g~ck,tk~ ⟩ g~ck,tk~   (31)

starting from r^(0)^ = x. The event train is the sequence of selected atom indices and times, and the number of atoms retained per unit time is a directly controllable rate parameter. The reported properties - precisely controllable spike rate, robustness to spike loss, and signal reconstruction - follow naturally from this structure.

Two observations. First, its reconstruction capability is exactly the tension noted for E2, in sharper form: an encoder that optimises reconstruction fidelity is optimising the criterion Section 2.2 argues is the wrong one, and is by construction the worst case for retained speaker information. That is not a criticism of Spiketrum, which was designed for a different purpose, but it makes the encoder an informative extreme point in our comparison and a useful upper reference for the privacy axis. Second, it comes with hardware implementations, which is directly relevant if any measured energy claim is later attempted.

Caveat requiring action. The description above is reconstructed from published abstracts and citation records; the Spiketrum papers have not been read in full. Before this encoder is described in a paper or implemented against, the primary sources should be obtained - principally the TETCI article on neuromorphic auditory perception by neural spiketrum, the TCSI article on the FPGA cochlea, and the evaluation paper on the encoder. Oliver and Simon will approach the authors directly (decision D9); E7 will not be implemented from published description. Until that conversation has taken place, this encoder is provisional and is excluded from the critical path of the schedule in Section 9.


### 5.8 R1 - Lauscher / Heidelberg reference point

Not a candidate but a fixed reference. The Spiking Heidelberg Digits dataset was produced using an artificial cochlea model with seven hundred output channels, comprising a hydrodynamic basilar membrane model, a transmitter-pool hair cell stage and a bushy cell layer. Including it costs little and buys two things: interoperability, since a substantial body of existing spiking network tooling reads data in that channel format, and a familiar coordinate for readers who know the SHD benchmark. Whether seven hundred channels should be a target for our own release, for the same interoperability reason, appears in Section 10.


### 5.9 R2 - Non-spiking upper bound

The essential control. Forty mel-scale filterbank features computed over twenty-five millisecond windows at ten millisecond hop, fed to the same decoder architecture as every spiking condition. This is the standard front end used by Wu and colleagues and by Bittar and Garner, so results are directly comparable to the published literature as well as internally.

Every accuracy in the study should be reported as a gap to this bound rather than in isolation. Without it, a phone accuracy figure means nothing: the reader cannot tell whether a shortfall reflects the encoding, the decoder, the corpus or the task definition. With it, the central engineering question of the project has a direct numerical answer - what accuracy is given up, at what saving in operations, by representing the audio as events.


---


## 6. Evaluation methodology

The comparison is only as good as its controls. This section sets out how encoded data is presented to a task, how tasks are scored, how cost is accounted for, and what must be held constant for the comparison to mean anything. The constraints in Section 6.5 are the part most likely to attract reviewer attention and the part most likely to be got wrong through inattention rather than disagreement.


### 6.1 Featurisation: the interface between encoder and probe

Probes cannot consume raw event sets directly, so events must be converted to a numerical array. This conversion is a decoding-side choice, and it must be identical across encoders or it silently becomes part of what is being compared. Each channel's event set is convolved with a fixed exponential kernel and sampled at a fixed frame rate:


> φ~c~(t) = Σ~k~ κ(t - t~k~),    κ(u) = exp(-u / τ~φ~) for u ≥ 0, else 0   (32)

For encoders producing polarity, ON and OFF events are accumulated into separate feature channels rather than summed, since cancelling them would discard the distinction the encoder went to the trouble of making.

One caveat requires handling rather than noting. A single fixed τ~φ~ favours encoders whose natural timescale happens to match it. The mitigation is to treat τ~φ~ as a shared swept axis, evaluating every encoder at every value in a set such as {2, 5, 20} milliseconds and reporting each encoder at its own best value. This is fair because the axis is available to all encoders equally, and it is honest because the chosen value is reported.


### 6.2 Paired probes and the accessibility gap

Every task is run with two decoders of very different capacity.

The linear probe is multinomial logistic regression on the featurisation of equation (32), applied per frame for T1 and T3, and as ridge regression per frame for the F~0~ contour of T2. It measures whether the relevant information is linearly accessible.

The nonlinear probe is a small recurrent network of fixed architecture - a two-layer bidirectional gated recurrent unit with a fixed hidden size, identical across every encoder, with only the input projection resized to accommodate differing channel counts. It measures whether the information is present at all, given a decoder able to compute with it.

The difference between the two is reported as an explicit quantity:


> Δ~T~(E) = A~T~^nonlinear^(E) - A~T~^linear^(E)   (33)

This gap is argued here to be among the most useful numbers the study can produce, and it does not appear in the comparison literature we are aware of. A downstream user of the released dataset cares about accessible information, not latent information: an encoding that hides phone identity behind a nonlinearity has not solved a problem, it has moved that problem to every user of the library. Two encoders with equal nonlinear accuracy but very different gaps are not equally good choices for a release, and only the paired design reveals that.


### 6.3 Budget accounting

Four quantities are reported for every operating point. Mean event rate per channel, in events per second per channel, over total duration D and N~ch~ channels:


> R = N~events~ / (N~ch~ D)   (34)

Total event rate, which is the primary budget variable because it determines both file size and downstream computational load:


> Λ = N~events~ / D   (35)

Bandwidth, given b~t~ bits of timestamp and b~p~ bits of polarity per event:


> B = Λ ( log~2~ N~ch~ + b~t~ + b~p~ )   bits per second   (36)

And readout cost, counted as accumulate operations, since an event arriving at a unit with N~hidden~ downstream targets triggers N~hidden~ additions and no multiplications - which is the entire computational argument for event-based processing:


> Ops = N~events~ N~hidden~   accumulates   (37)

To these is added a measure of coding efficiency: how much task-relevant information each event carries. Mutual information between a spike train and the acoustic stimulus is not estimable here, since the direct method requires repeated presentations of identical stimuli and every utterance in both corpora is unique. What is estimable, cheaply and defensibly, is decoded information. From the joint distribution of true label Y and predicted label Y-hat over the test set - that is, from the probe's confusion matrix - compute


> I(Y ; Y-hat) = Σ p(y, y-hat) log~2~ [ p(y, y-hat) / (p(y) p(y-hat)) ]   (38)

By the data processing inequality this lower-bounds the information the encoding carries about the task, since the probe cannot manufacture information the representation does not contain. Two derived quantities are then reported:


> bits per event = I(Y ; Y-hat) / n,     bits per second = I(Y ; Y-hat) / Δt~frame~   (39)

with n the mean number of events per classified unit. For the regression formulation of T2, the corresponding quantity is derived from the correlation via I = -(1/2) log~2~(1 - r^2^), which is exact for jointly Gaussian variables and serviceable as an approximation otherwise, provided the approximation is declared.

A caveat governs the use of these figures wherever they appear. Bits per event is trivially maximised at very low event rates: a single well-placed event carrying one bit scores better than a thousand events carrying five. Reported as a scalar to be maximised it would hand victory to the sparsest encoder by construction, and would say nothing about whether that encoder is useful. It is therefore reported as a curve against event rate, alongside the accuracy fronts rather than in place of them, and the paper should state this explicitly rather than leaving a reader to notice it.

Two rules matter more than the formulae. First, the encoder's own computational cost - filterbank convolutions, envelope extraction, threshold logic - is reported and charged to the spiking condition, not hidden. An encoding that is cheap downstream but expensive to produce has not saved anything, and this is the single most common weakness in published energy claims for spiking systems. Second, comparison is at matched Λ rather than matched R whenever channel counts differ, because Λ is what a user pays.


### 6.4 Sweeps and Pareto fronts

No encoder is ever compared to another at a single operating point. For each encoder and task, the rate parameter is swept across at least six values spanning roughly two orders of magnitude in Λ, and the non-dominated points form the Pareto front in the plane of event rate against accuracy. Encoders are compared by the relative position of their fronts, and the headline figure of the paper should be a panel of four such plots, one per task, with the non-spiking bound R2 drawn as a horizontal line on each.

This is not a stylistic preference. Encodings that emit more events perform better on every task, trivially and almost without exception. A table of single-point results therefore measures event rate rather than encoding quality, and any comparison presented that way can be reversed by retuning. Insisting on fronts is what makes the study's conclusion robust.


### 6.5 Fairness constraints

The following are binding on every condition and should be stated explicitly in the paper's methods section.

- **C1 - Identical source audio.** Same recordings, same sample rate, same normalisation. No per-encoder audio preprocessing beyond the stages declared as part of that encoder.
- **C2 - Identical timestamp quantisation.** All encoders write events at the same temporal resolution, declared in the paper. Resolution is additionally swept as a shared axis, because timing-based encoders such as E5 and E6 gain from finer resolution while rate-like encoders do not, and an undeclared difference here would invisibly determine the result.
- **C3 - Matched budget.** Comparison on Pareto fronts over total event rate, never at single points. See Section 6.4.
- **C4 - Identical decoding.** Same featurisation (Section 6.1), same probe architectures, same optimiser, schedule, regularisation and stopping criterion across all encoders.
- **C5 - Equal tuning budget.** A fixed number of hyperparameter trials per encoder, drawn by the same search strategy, with the number stated. A carefully tuned favourite compared against defaults is the standard and fatal criticism of studies of this kind, and equalising effort is the only defence.
- **C6 - Declared splits.** Identical splits across encoders, speaker-disjoint between train and test for all three tasks. The replacement of speaker identification by F~0~ estimation in version 2 removes the split asymmetry that version 1 had to carry, and with it a standing risk of confusing leakage with genuine performance.
- **C7 - Encoder cost charged.** Per Section 6.3.
- **C8 - Repeated runs.** At least three seeds per condition, reporting mean and spread. Where error rates are reported, credible intervals computed on the binomial posterior, following the practice of Bittar and Garner, whose TIMIT phone error rates carry intervals of roughly ± 0.85 per cent on a test set of around seven thousand phones. Differences smaller than this are not differences.
- **C9 - Channel count.** Matched across encoders where the scheme permits. Where it does not, channel count is swept and reported as a separate axis.
- **C10 - Single release setting.** One parameter setting per encoder is nominated as the candidate release configuration, chosen without reference to any single task, and its per-task performance reported alongside the per-task optima. The loss incurred by the compromise is a headline result, not a footnote, because it is what a user of the release actually experiences.

### 6.6 Parameter axes

The following are swept rather than fixed. The full grid is not exhaustively explored; a coarse screen (Section 9) identifies which axes matter before effort is committed.

- Channel count N~ch~, over {32, 64, 128, 256, 700}.
- Frequency range and spacing: ERB, mel or linear.
- Compression: logarithmic, power-law with exponent 0.3, or none.
- Membrane and refractory constants τ~m~, Δ~ref~.
- Adaptation strength and time constant Δ~a~, τ~a~ (E4 only).
- Phase-locking cutoff f~lock~ (E5 only).
- Encoder-specific rate parameter, at least six values.
- Timestamp resolution (shared, per C2).
- Featurisation time constant τ~φ~ (shared, per Section 6.1).
It is worth anticipating that parameters will matter more than schemes. Two instances of the same encoder at 32 and 700 channels will very likely differ more than two different encoders at matched channel count. If that proves true it is a finding in its own right, and it argues for a paper organised around design axes rather than around a horse race between named algorithms.


---


## 7. Preliminary experiments

Two experiments precede the main study. Both concern the validity of the probe battery rather than the encoders, and both are run on E1 alone. Each constitutes a decision gate: if the outcome is not as predicted, the battery is revised before any effort is spent on the full comparison. They are cheap, and running them first is what prevents the main study from being three months of well-executed work on a badly posed question.


### 7.1 P1 - The count-only baseline

Question: how much of each task is solvable from event counts alone, with all timing discarded?

Method: featurise each utterance or segment as the vector of per-channel event counts n~c~, discarding event times entirely, and run the same probes. Compare against the full temporal featurisation of equation (32). Define a temporal information index per task:


> TII~T~ = ( A~T~^temporal^ - A~T~^count^ ) / ( A~T~^ceiling^ - A~T~^count^ )   (40)

with the ceiling taken from the non-spiking bound R2.

Interpretation: a task with TII near zero is not testing temporal coding at all - it is a spectral profile task wearing a spiking costume, and including it in the battery would let a pure rate code appear to succeed at something it is not doing. Expected outcome is a moderate index for T1, since phone segments are short and counts carry much of the spectral shape, and a high index for T2 and T3, both of which depend on timing that counts discard entirely. Any task returning a near-zero index is either reformulated or dropped.

This experiment also delivers something practically valuable: a defensible statement, early and cheaply, about how much of the phone task is a rate problem. That is worth knowing before committing to the timing-based encoders.


### 7.2 P2 - Corruption and dissociation

Question: do the three tasks in fact degrade under different corruptions, as the spanning argument of Section 4.4 requires?

Method: apply four corruption operators to encoded event trains and measure accuracy degradation on each task.

- Temporal jitter. Each event time is perturbed independently, t~k~ → t~k~ + η~k~ with η~k~ drawn from a zero-mean normal distribution of standard deviation σ, swept over {0.1, 0.5, 2, 10, 50} milliseconds.
- Channel shift. All channel indices are translated by a constant, c → c + Δ, for Δ in {± 1, 2, 4} channels. On an ERB-spaced bank this approximates the log-frequency translation produced by a change in vocal tract length.
- Random deletion. Each event is retained independently with probability 1 - p, for p in {0.1, 0.3, 0.5}.
- Count-preserving randomisation. Event times are resampled uniformly within each segment while preserving per-channel counts, destroying timing while leaving rate intact.
Predicted signature, following directly from Section 2.3: T1 robust to jitter and to channel shift, sensitive to deletion. T2 sensitive to jitter, since periodicity is carried in fine timing, and sensitive to channel shift, since it is the absolute frequency scale that is being estimated - the mirror image of T1 on both axes. T3 sensitive to jitter but robust to channel shift, since a boundary is a boundary wherever in the spectrum it appears.

Interpretation: if the degradation profiles across tasks turn out to be similar rather than distinct, the battery does not span the demand space and the central methodological claim of the paper fails. That would be uncomfortable but it is far better discovered in week four than in month three, and the finding would itself be worth reporting - it would mean the opposing-demands framing, which is widely assumed in this literature, does not survive contact with a spiking front end.


---


## 8. Dataset strategy

Oliver's proposal to begin on TIMIT and move to our own corpus afterwards is endorsed, and the reasoning should be stated in the paper because it is a design decision reviewers will probe.


### 8.1 Stage one: TIMIT

TIMIT is the standard corpus for phone-level work: around four hours of read sentences from 630 American English speakers, distributed with hand-placed phone boundaries and labels. Four reasons make it the right starting point.

1. Hand-placed labels remove the forced-alignment dependency during methodology development, so encoder quality is never confounded with label noise. This applies with equal force to T3, whose ground truth is those boundaries.
2. 630 speakers with standard splits make T2 workable without additional preparation.
3. All three papers already in the project folder - Wu and colleagues, Ponghiran and Roy, Bittar and Garner - report TIMIT phone results, giving direct anchors. Bittar and Garner in particular report 15.77 per cent phone error rate for an LSTM baseline against 17.63 per cent for a fully spiking recurrent encoder, which establishes that the spiking penalty on this task is under two points and gives us a target to beat or to explain.
4. Anyone can reproduce the comparison. This is what makes the study a methods contribution rather than a report about private data, and it is what allows the encoding choice to be defended independently of the corpus it will be applied to.
Two caveats belong in the paper. TIMIT is read, clean, US English at 16 kHz, so parameters tuned on it may not transfer to our recording conditions - which is exactly why stage two exists. And its read sentences carry limited intonational variety, so the F~0~ range exercised will be narrower than in the MANCHESTER Dataset, which contains questions. T2 remains workable on TIMIT - every voiced frame has a fundamental frequency whether or not the sentence is intonationally interesting - but the transfer test at stage two is where the wider range gets exercised.

Action required: TIMIT is distributed under licence by the Linguistic Data Consortium, to members and non-members alike, and academic purpose does not exempt a user from licensing. Whether Manchester holds current LDC membership is being established; if it does, access is administrative, and if not a non-member licence must be purchased. See Section 10.2 for the position and the fallback.


### 8.2 Stage two: the recorded corpus

The chosen encoding, and a small number of near-competitors, are then applied to our own recordings. This is a transfer test rather than a repeat of the study: the question is whether the ranking established on TIMIT survives a change of speakers, accents and recording conditions. If it does, the release is justified. If it does not, that is a reportable and interesting finding about how corpus-dependent encoding choices are, and it belongs in the paper rather than being quietly resolved.

Phone labels will be needed. Since the corpus consists of read sentences with known text, the required operation is forced alignment, not phone recognition - and the distinction is important. Free phone recognition on unconstrained audio runs at error rates in the tens of per cent; forced alignment, which is given the word sequence and need only determine when each phone occurred subject to a pronunciation dictionary, places boundaries to within tens of milliseconds. The Montreal Forced Aligner is the standard tool, built on Kaldi, with pretrained English acoustic models and the ability to adapt to a speaker set. Charsiu is a neural alternative that returns frame-level posteriors rather than hard boundaries, which is useful if training is to be weighted by label confidence.

One risk specific to this corpus needs planning for rather than discovering. Pretrained English acoustic models are built predominantly on native speech, and forced alignment degrades on accented and second-language speech - which is precisely what a corpus of English speakers unrestricted by background will contain. Since alignment quality caps the ground truth for both T1 and T3 at stage two, this is a material threat to the transfer test rather than a detail. Three mitigations are available and are not exclusive: adapt the MFA acoustic model on the corpus itself, which is supported and inexpensive; measure alignment agreement separately by speaker group so that any degradation is visible rather than averaged away; or restrict the stage two evaluation to a subset for which alignment quality is demonstrably adequate. Which is adopted depends on the corpus specifics still outstanding and on the measured agreement figures.

Label quality caps everything downstream, so it should be measured rather than assumed. Two cheap checks: run both aligners and quantify boundary disagreement as a proxy for uncertainty, and validate both against TIMIT's hand labels first, which gives a calibration figure before either is trusted on our audio.


---


## 9. Indicative schedule

Twelve weeks, with Simon implementing. This is indicative and intended to convey the shape and relative weight of the work rather than to be held to. The two decision gates are the parts of the sequence that matter; the week numbers are not.

- **Weeks 1-2** — Infrastructure. Data pipeline, common front end (Section 5.0), featurisation, probe harness, budget and information accounting, experiment tracking. Deliverable: E1 running end to end on TIMIT with a T1 linear probe producing a sensible phone accuracy. Concurrently: resolve the TIMIT licence question.
- **Week 3** — Preliminary P1, count-only baseline across all three tasks on E1.
- **Week 4** — Preliminary P2, corruption and dissociation. DECISION GATE: battery confirmed, or revised before proceeding.
- **Weeks 5-7** — Implement E2 to E6, plus references R1 and R2, and E7 if the Spiketrum sources and any available code have been obtained. Unit tests per encoder: verify the reconstruction bound of equation (16) for E2, verify monotonic rate control for all, verify vector strength behaves as expected for E5.
- **Week 8** — Coarse screening sweep. T1 and T2 only, linear probe only, wide rate sweep, coarse parameter grid. DECISION GATE: drop clearly dominated encoders and identify which parameter axes matter.
- **Weeks 9-10** — Full sweep on surviving encoders. All three tasks, both probes, refined parameter grid, three seeds. Reduced from four tasks in version 1, which buys back roughly a week of margin.
- **Week 11** — Transfer to the recorded corpus. Forced alignment and its validation, then rerun of the leading encoders at their chosen operating points.
- **Week 12** — Analysis. Pareto figures, accessibility gaps, selection of the single release configuration under C10, and the quantified cost of that compromise.
Journal paper written thereafter. Principal risks, in rough order of likelihood: delay in obtaining a TIMIT licence, which is why it is week one work; alignment quality on our corpus falling short of what T1 and T3 need at stage two; compute cost of the full sweep exceeding what is available, mitigated by the week eight screen; and the E7 dependency on external code and on the availability of its authors.


---


## 10. Decisions taken and items still open

The open decisions of version 1 were put to Oliver and answered on 20 August 2026. This section records the outcomes and the consequences that follow, then lists what remains outstanding.


### 10.1 Settled

- **D1 Scope.** Audio only, with the vision side kept in mind for future work. The DVS event model remains a design consideration on the audio format, per Section 2.6.
- **D4 Speaker identity.** Not a target of the multimodal dataset and not a priority for this work. Consequence: speaker identification has been removed as a probe task and replaced by F~0~ contour estimation, which probes the same encoder property without being a speaker-identification system. It is retained as an optional diagnostic per Section 4.5.
- **D5 Venue.** Neuromorphic Computing and Engineering (IOP, ISSN 2634-4386). Consequences in Section 10.3.
- **D6 Prosody.** Interesting but not an immediate priority. Consequence: absorbed into T2, which now carries the periodicity and intonation axis at no extra cost.
- **D7 DVS symmetry.** Shared representations are expected to be a feature of the subsequent multimodal pipeline, in which the audio encoding will be used alongside time-aligned vision data. Consequence: format symmetry is a forward-looking preference rather than a hard constraint on this study, but it raises the value of E2 and makes timestamp conventions and temporal resolution decisions that should be taken with the vision data in view.
- **D8 Channel count.** A free parameter. Swept per Section 6.6; no obligation to match the 700-channel SHD format.
- **D9 Spiketrum.** Oliver and Simon will approach Wijekoon directly. Consequence: E7 is provisional in this document and will not be implemented from published description; see Section 5.7.
- **D10 Learned encoders.** Excluded, for now.
- **D11 Dataset name.** The MANCHESTER Dataset, used throughout.
- **D12 Start.** Now, in parallel with resolving the TIMIT licence question.
- **D13 Release engineering.** Proceeds in parallel but is not the fundamental research. Format and metadata decisions follow the encoding decision rather than preceding it.
- **D14 Cost metrics.** Measured energy on neuromorphic hardware is out of scope at this stage. Total spikes, information per spike and related measures are in scope now. Consequence: the information-theoretic metrics of Section 6.3 have been added, with the caveat recorded there about how they must be reported.
- **D15 Authorship.** Simon Davidson and Oliver Rhodes, with further co-authors added if appropriate.

### 10.2 The TIMIT licence position

D2 asked whether a licence is genuinely required or whether academic research use suffices. It is required: TIMIT is distributed by the Linguistic Data Consortium and is licensed to Consortium members and non-members alike, the distinction being the fee rather than whether a licence exists. Academic purpose does not exempt a user.

The route that usually applies is institutional. Many universities hold LDC membership, in which case the corpus is already available internally under terms that permit research use but prohibit redistribution. The question for us is therefore whether Manchester holds current membership, which the library or research computing will know. If it does, this is administrative. If not, a non-member licence must be purchased and a procurement cycle allowed for.

Copies of TIMIT circulate on public repositories. These are not licence-compliant sources, and since this project will publish a paper and release a dataset with accompanying code, provenance should be clean. If no licence proves obtainable, the fallback is a freely available corpus such as LibriSpeech, accepting that it lacks hand-placed phone labels and therefore reintroduces at stage one the forced-alignment dependency that TIMIT exists to avoid.


### 10.3 Consequences of the venue decision

Neuromorphic Computing and Engineering accepts Papers of unlimited length, so the full study can be submitted without compression; Letters are capped at roughly eight pages and are not the right vehicle here. The journal is fully open access and explicitly encourages authors to share data and code, which aligns exactly with the provenance requirements of the validation protocol - the public repository and the regeneration test become expectations of the venue rather than merely good practice.

Two practical points. There will be an article processing charge, so it is worth establishing early whether Manchester holds a read-and-publish agreement covering IOP titles. And review times average around four months, which means that against a funding deadline the realistic milestone is submission rather than publication.

One point of framing. IOP guidance notes that incremental advances on previous work are usually insufficient. This reinforces the position taken in Section 2.7: the contribution is the methodology - a battery selected for opposing demands, comparison strictly at matched budget, and the separation of present from accessible information - rather than the fact of having compared several encoders. The readership will be well equipped to challenge the case for spikes, so the cost accounting of Section 6.3 needs to be unusually careful.


### 10.4 Still open

- **O1 Corpus specifics.** Sample rate, recording environment, microphone, sentences per speaker, total duration, and the form the transcripts take. Needed before stage two can be planned in detail; not blocking for stage one.
- **O2 LDC membership.** Whether Manchester holds current LDC membership. Being pursued.
- **O3 Spiketrum inclusion.** Pending the conversation with Wijekoon. Determines whether E7 enters the comparison and on what terms.
- **O4 Publication charge.** Whether an IOP read-and-publish agreement applies.
- **O5 Alignment strategy for accented speech.** See Section 8.2. Which mitigation is adopted depends on O1 and on measured alignment quality.

---


## Appendix A. Glossary

Terms and acronyms used above, in alphabetical order.

- **AER** — Address-Event Representation. The standard transport format for event-based sensor data: each event is a tuple of address, timestamp and polarity.
- **ALIF** — Adaptive leaky integrate-and-fire. A LIF neuron whose firing threshold rises after each event and decays back toward baseline, producing spike-frequency adaptation.
- **ANN** — Artificial neural network. Used here for conventional non-spiking networks, in contrast to SNN.
- **CTC** — Connectionist temporal classification. A loss function for sequence labelling that marginalises over all alignments between input frames and output labels, removing the need for explicit frame-level alignment.
- **DVS** — Dynamic Vision Sensor. An event camera whose pixels report changes in log intensity asynchronously rather than sampling frames.
- **ERB** — Equivalent rectangular bandwidth. A measure of auditory filter bandwidth; the ERB-rate scale derived from it is the standard axis for placing filterbank centre frequencies.
- **F~0~** — Fundamental frequency. The repetition rate of vocal fold vibration; the acoustic correlate of pitch.
- **F~1~, F~2~, F~3~** — The first three formants: resonances of the vocal tract, numbered in ascending frequency.
- **Forced alignment** — Determining the time boundaries of each phone in an utterance given the known word sequence. Distinct from, and far more accurate than, phone recognition.
- **Gammatone** — A filter whose impulse response is a γ envelope multiplying a sinusoidal carrier; the standard computational approximation to cochlear frequency selectivity.
- **GRU** — Gated recurrent unit. A recurrent network cell, used here as the fixed nonlinear probe.
- **LIF** — Leaky integrate-and-fire. The standard simplified spiking neuron model.
- **MFA** — Montreal Forced Aligner. Open-source forced alignment tool built on the Kaldi speech toolkit.
- **Matching pursuit** — A greedy sparse decomposition algorithm that repeatedly subtracts the dictionary atom best correlated with the current residual.
- **Decoded information** — Mutual information between true and predicted labels, computed from a classifier's confusion matrix. Lower-bounds the task information carried by the representation.
- **Pareto front** — The set of operating points not dominated by any other point of the same system; here, the upper-left envelope in the plane of event rate against accuracy.
- **PER** — Phone error rate. Edit distance between reference and hypothesis phone sequences, as a fraction of reference length. Conventionally scored on a 39-symbol collapsed label set on TIMIT.
- **Phone / phoneme** — A phone is a single speech sound as physically produced; a phoneme is the abstract category to which phones belong in a given language.
- **Semitone** — A logarithmic unit of frequency ratio; one twelfth of an octave. The natural unit for reporting F~0~ error.
- **SFA** — Spike-frequency adaptation. Reduction of firing rate under sustained stimulation.
- **SHD** — Spiking Heidelberg Digits. A benchmark dataset of spoken digits encoded through an artificial cochlea model into 700 channels.
- **SNN** — Spiking neural network.
- **Send-on-delta** — An encoding rule emitting an event whenever a signal has moved a fixed distance from a tracked reference. Known in the spiking literature as Step Forward encoding.
- **Source-filter model** — The standard idealisation of speech production as an excitation source passed through the acoustic filter of the vocal tract.
- **TIMIT** — A standard read-speech corpus with hand-placed phone labels, distributed under licence by the Linguistic Data Consortium.
- **TTFS** — Time-to-first-spike. An encoding in which magnitude is represented by the latency of a single event within a window.
- **VAD** — Voice activity detection. Determining when speech is present.
- **Vector strength** — A measure of how tightly events cluster at a preferred phase of a periodic stimulus; one for perfect phase locking, zero for none.
- **VTL** — Vocal tract length. Scales all formants multiplicatively, hence uniformly along a log-frequency axis.