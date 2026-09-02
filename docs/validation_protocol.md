# Validation Protocol for the Spike Encoding Study

**How results produced with AI assistance are checked before anyone puts their name to them**

*Companion to the study proposal | Draft for comment*


---


## 1. Purpose

The implementation for this study will be written largely with AI assistance. That creates a specific risk: that results are generated, analysed and written up by a process neither author fully inspected, and that an error introduced anywhere along the chain reaches publication under their names. The concern is legitimate and this document is the response to it.

The protocol below is not a general statement of good practice. It is built around the particular ways this kind of assistance fails, and around the fact that several of the encoders in this study have analytically provable properties that can be tested against theory rather than against anyone's judgement. That second point is the reason a strong protocol is achievable here at reasonable cost.

The governing principle is stated once and everything else follows from it: every result must be reconstructible without the assistant. Not reviewable - reconstructible. If the only way to establish that a number is correct is to read the code that produced it and find it convincing, the protocol has failed.


---


## 2. What is being defended against

Being specific about the failure modes is what makes the countermeasures targeted rather than ceremonial. Four matter here.


### 2.1 Plausible error, not obvious error

AI-generated code rarely crashes and rarely returns absurd numbers. It fails by being quietly wrong while running cleanly and producing output in a believable range: an off-by-one in frame indexing, labels offset by one frame against features, a reduction taken over the wrong array axis, a normalisation applied twice, a split that leaks a speaker between train and test. These survive casual inspection precisely because nothing looks wrong. Conventional code review - reading it and finding it reasonable - is close to useless against this class of bug, because the code does read as reasonable. Only tests with independently known answers catch it reliably.


### 2.2 Confabulation

The assistant will, occasionally and with complete fluency, produce a citation, a parameter value, an equation or a claim about standard practice that is plausible and false. It does not signal when this happens, because from the inside it is indistinguishable from recall. The Spiketrum description in the proposal is flagged for exactly this reason. Any factual claim that matters - a published figure, a tool's behaviour, a convention - must be traced to a primary source before it enters the paper.


### 2.3 No memory across sessions

The assistant retains nothing between conversations beyond what is in the project files. It can therefore contradict a decision taken three weeks earlier with complete confidence, and will not know it has done so. The decisions log and the versioned README are the source of truth. Where the assistant and the log disagree, the log wins, without discussion.


### 2.4 Pull toward the expected result

The proposal makes specific directional predictions - adaptation helps T1 and hurts T2, E3 is near-useless on T4, E6 dominates at low event rates. If the same process both runs the sweeps and writes the analysis, a large number of small choices about parameter ranges, seeds, plot limits and which runs to repeat will tend to favour those predictions. No dishonesty is required for this; it is the ordinary mechanism by which analysis drifts toward its hypothesis, and an assistant that has read the proposal is if anything more susceptible than a person, not less. Section 7 addresses it directly.


---


## 3. Layer 1: Known-answer tests

The highest-value defence, and the one this study is unusually well placed to use. Several encoders have properties that follow from their definitions as mathematical facts. Where an expected value can be derived from an equation, the test does not depend on trusting any implementation - the answer comes from the maths.

Two rules govern this layer. First, tests are specified from the equations in the proposal before the corresponding code is written. Second, wherever practical, Simon writes the test and the assistant writes the implementation. If the assistant writes both, it will write tests that pass against its own misunderstanding, and the exercise becomes decorative.


### 3.1 Tests applying to every encoder

- **G1 Determinism.** Identical input and seed produce an identical event set. Compare sorted event lists for exact equality.
- **G2 Silence.** Zero input produces zero events. Any encoder with a spontaneous rate must declare it and the expected rate is asserted instead.
- **G3 Monotone rate control.** Sweeping the rate parameter produces strictly monotonic total event rate Λ across the whole swept grid. Non-monotonicity anywhere invalidates the matched-budget comparison and must be resolved before that encoder is used.
- **G4 Time-shift equivariance.** Delaying the input by Δ delays every event by Δ, to within timestamp quantisation. This is the cheapest available catch for framing and indexing errors.
- **G5 Class separation under amplitude scaling.** Scaling the input by a constant shifts the log-compressed envelope by a constant. Change-based encoders (E2, E3) must therefore show near-invariant event counts, while level-based encoders (E1, E4, E6) must show increased counts. An encoder behaving like the wrong class has a compression or reference bug.
- **G6 Channel localisation.** A tone at f~c~ produces events overwhelmingly in channel c, with leakage into neighbours consistent with the filter skirts. Catches transposed axes and misaligned channel indexing.
- **G7 Event validity.** No event outside the signal duration; no two events in a channel closer than Δ~ref~; polarity values in the declared set.
- **G8 Order invariance of featurisation.** Shuffling the row order of an event file and re-running equation (32) produces an identical feature array.

### 3.2 Front-end tests (Section 5.0 of the proposal)

- **F1 Centre frequencies.** The FFT magnitude peak of each gammatone impulse response falls within one per cent of the nominal f~c~.
- **F2 Bandwidths.** The measured 3 dB bandwidth of each channel is consistent with 1.019 ERB(f~c~) from equation (5).
- **F3 Spacing.** Channel centre frequencies are equally spaced on the ERB-rate scale of equation (6): successive differences of E(f~c~) are constant to numerical precision.
- **F4 Envelope extraction.** For an amplitude-modulated tone with known modulator m(t), the extracted envelope correlates with m(t) above 0.95. (The threshold was stated as 0.99 in an earlier draft; 0.95 is the considered value, since gammatone ringing and Hilbert transform edge effects make 0.99 optimistic even for a correct implementation. test_F4 asserts 0.95.)
- **F5 Energy conservation.** The Σ of subband energies matches input energy to within the factor implied by filter overlap. Catches normalisation applied twice or not at all.

### 3.3 E1 - Leaky integrate-and-fire

Under constant drive the LIF has a closed-form firing period. With steady-state potential V~inf~ = g u and threshold θ, integration from reset to threshold takes


> T = τ~m~ ln( V~inf~ / (V~inf~ - θ) )   (V1)

and the firing rate is 1/(T + Δ~ref~).

- **T1.1** Drive one channel with constant u and compare the measured interspike interval to equation (V1). Agreement to within one simulation time step.
- **T1.2** The threshold boundary: for V~inf~ ≤ θ the channel emits nothing; as V~inf~ approaches θ from above the interval diverges. Assert both.
- **T1.3** Refractory ceiling: with large drive the rate saturates at exactly 1/Δ~ref~.

### 3.4 E2 - Send-on-delta

The strongest set of tests in the study, because equations (16) and (17) are theorems rather than expectations.

- **T2.1 Reconstruction bound.** For white noise, chirps and real speech, assert that the tracked reference never departs from the compressed envelope by C or more, in any channel at any time. This is equation (16). A single violation is a bug, not a tolerance issue.
- **T2.2 Event count from total variation.** Bypass the filterbank and apply u(t) = A sin(2π f t) directly. Its total variation over duration D is 4AfD, so equation (17) predicts 4AfD/C events. Assert agreement to within the boundary tolerance of roughly 2fD + 1 events.
- **T2.3 Linear ramp.** A ramp of slope s must produce events at exactly regular intervals C/s, all of the same polarity. This is a sharp test of the reference-update logic and will catch the difference between the two variants described in Section 5.2 of the proposal.
- **T2.4 Polarity balance.** For a signal returning to its initial value, ON and OFF counts are equal in the lattice variant, and differ by at most one step otherwise.
- **T2.5 Rate scaling.** Doubling C halves the event count, within the T2.2 tolerance. A direct check of the 1/C relation claimed in the proposal.

### 3.5 E3 - Temporal contrast

The critical risk for E3 is that it is implemented as E2 by accident, since the two are conceptually adjacent. Tests T3.1 and T3.2 exist specifically to detect that.

- **T3.1 Steady-state silence.** Constant input produces exactly zero events after five slow time constants. E2 under the same input produces zero only after the reference settles; E3 must produce zero permanently.
- **T3.2 Slow ramp discrimination.** A ramp slow relative to τ~s~ produces zero events from E3 and many from E2, run on identical input. If both produce events, E3 is not bandpass and has been implemented incorrectly.
- **T3.3 Modulation frequency response.** The difference of two one-pole lowpass filters peaks in magnitude at ω = 1/sqrt(τ~f~ τ~s~). Drive with sinusoidal envelope modulation across a range of rates; event count must peak near f = 1/(2π sqrt(τ~f~ τ~s~)).
- **T3.4 Sign symmetry.** With symmetric thresholds, negating the input exchanges ON and OFF counts exactly.

### 3.6 E4 - Adaptive-threshold LIF

- **T4.1 Reduction to E1.** Setting Δ~a~ = 0 must produce an event set identical to E1 at the same θ~0~. This is the single most valuable test for E4, since it catches almost any divergence introduced while adding adaptation.
- **T4.2 Threshold decay.** After a single isolated event, the threshold trace follows θ~0~ + Δ~a~ ρ^n^ with ρ = exp(-Δt/τ~a~). Assert against the recorded state trace directly, not against firing behaviour.
- **T4.3 Onset emphasis.** For a step input, the ratio of events in the first 50 ms to a later 50 ms window exceeds one and increases monotonically with Δ~a~.
- **T4.4 Steady-state suppression.** Adapted firing rate under constant drive decreases monotonically as Δ~a~ τ~a~ increases.

### 3.7 E5 - Phase-locked fine structure

Vector strength, equation (26), is the natural test statistic here because it measures precisely the property the encoder exists to preserve.

- **T5.1 Locking below cutoff.** A pure tone at f~c~ with f~c~ < f~lock~ yields vector strength above 0.9 in the deterministic variant and above 0.7 in the stochastic variant.
- **T5.2 Loss above cutoff.** For f~c~ > f~lock~, vector strength falls to chance, approximately 1/sqrt(N) for N events.
- **T5.3 Periodicity recovery.** For a synthetic harmonic complex of known F~0~, the pooled interspike-interval histogram across low-frequency channels peaks at 1/F~0~. This is a direct test that the encoder does the one job it was included for.
- **T5.4 Quantitative jitter response.** Gaussian timing jitter of standard deviation σ reduces vector strength by the factor exp(-2 π^2^ σ^2^ f~c~^2^ ). Applying the P2 jitter operator must reproduce this curve. This test does double duty: it validates E5 and it validates the jitter operator used in preliminary experiment P2.

### 3.8 E6 - Time-to-first-spike

- **T6.1 Exact budget.** Total events never exceed N~ch~ D / H, and at most one event occurs per channel per frame. Both assertable exactly.
- **T6.2 Rank inversion.** Within each frame, the rank ordering of channel energies is exactly the reverse of the rank ordering of latencies. Spearman correlation of exactly minus one.
- **T6.3 Latency formula.** In the LIF-latency variant, measured latencies match equation (29) to within one time step.

### 3.9 E7 - Spiketrum, if included

- **T7.1 Residual monotonicity.** Residual energy decreases strictly with each atom selected. This is a property of matching pursuit and holds regardless of dictionary.
- **T7.2 Reconstruction improvement.** Reconstruction error decreases monotonically with atom count.
- **T7.3 Reference comparison.** If the authors' implementation can be obtained, compare outputs on identical input. This supersedes T7.1 and T7.2 as evidence. Reimplementing a colleague's algorithm from published descriptions and then reporting on it is to be avoided; see decision D9 in the proposal.

---


## 4. Layer 2: Pipeline controls

Layer 1 validates encoders in isolation. These controls validate the surrounding machinery, where the more dangerous errors live, because a broken encoder usually produces obviously broken results while a leaking split produces excellent ones.

- **C1 Upper-bound anchor.** The non-spiking reference R2 must land in the published range for TIMIT. The anchors available in the project papers are 82.68 per cent frame-level accuracy for an LSTM (Ponghiran and Roy) and 15.77 per cent phone error rate for an LSTM encoder with CTC (Bittar and Garner). A result far below this band means the pipeline is broken and nothing downstream is interpretable. A result far above it means something is leaking. Both directions trigger investigation before any spiking condition is run.
- **C2 Chance and majority floors.** Report the majority-class rate for every classification task. Any probe failing to beat it substantially is not working.
- **C3 Shuffled-label control.** Shuffle training labels, retrain, and confirm test performance returns to chance. Run once per task and after any change to splitting, featurisation or batching. This is the primary detector of leakage, which is the error most likely to produce an exciting and false result.
- **C4 Split disjointness assertions.** Programmatic set-intersection checks asserted at every run: speaker sets disjoint between train and test for T1, T3 and T4; utterance sets disjoint for T2. Cheap, and non-negotiable.
- **C5 Deliberate misalignment.** Offset labels by plus and minus one frame and confirm accuracy drops measurably. If it does not, the alignment between features and labels is not doing what it should, and the headline numbers are meaningless. This is the single most valuable control in the list, because frame misalignment is the most likely silent bug in the whole pipeline and it is otherwise invisible.
- **C6 Budget cross-check.** Event rate Λ computed by counting rows in the written event file must equal Λ reported by the encoder internally. Two independent counts of the same quantity.
- **C7 Round-trip integrity.** Write events to the release format, read them back, and assert an identical event set. This tests the format that will actually be published, not an in-memory representation.
- **C8 Seed spread.** Three seeds minimum per condition. Where the spread across seeds exceeds the binomial credible interval, differences within that spread are not reported as differences. Following Bittar and Garner, intervals on TIMIT phone error rates are roughly ± 0.85 per cent.

---


## 5. Layer 3: Independent reimplementation

One encoder is implemented twice, independently. E2 is the right choice: it is the simplest, it is the one with format significance for the release, and it has the sharpest analytic tests.

Procedure. Simon implements E2 from equations (14) to (17) of the proposal alone, without reading the assistant's implementation. Both are run on a fixed set of test signals - white noise, a chirp, a linear ramp, and one TIMIT utterance - at identical parameters and timestamp quantisation. Event sets are compared element by element.

Agreement is meaningful evidence that the specification in the proposal is unambiguous and that both implementations realise it. Disagreement is a caught bug, or else a discovery that the specification is ambiguous - most likely over the reference-update variant - which is itself worth knowing before the format is fixed. Either outcome repays the two days it costs, and it calibrates how much scrutiny the remaining encoders need.


---


## 6. Layer 4: Provenance

This is what makes the project auditable rather than merely careful, and it is the layer that most directly answers the black-box concern.

- All code in a git repository. Every reported result tagged to a commit hash.
- All runs driven by version-controlled configuration files. No parameters typed ad hoc at a command line or pasted from a chat window.
- Every figure and table regenerable end to end from raw audio by a single documented command.
- Results written to data files. The manuscript reads numbers from those files; no number is ever transcribed by hand from a conversation into the paper.
- Seeds recorded for every run.
- A results manifest mapping each figure and table in the paper to its script, configuration, commit, seed and output file.
The acceptance test for this layer is Section 8.


---


## 7. Layer 5: Pre-registered predictions

The countermeasure to Section 2.4. The proposal already states directional predictions; they are recorded and dated in the decisions log before the corresponding runs, and held fixed thereafter. At minimum:

- E4: accuracy on T1 rises and on T2 falls as adaptation strength Δ~a~ increases.
- E3: strongest on T3; poor on T4, plausibly close to useless.
- E5: strongest on T2 and T4; likely dominated at matched budget despite carrying the most information.
- E6: dominates at the low end of the event-rate axis on T1; poor on T3.
- E2: strong on T3; its case rests on format symmetry rather than peak accuracy.
- P1: temporal information index high for T2 and T3, moderate for T1.
- P2: the four tasks degrade under different corruption operators, per the signature in Section 7.2 of the proposal.
A result contradicting a recorded prediction triggers a written investigation before it is used, and the investigation is recorded whatever its outcome. The purpose is not to protect the predictions - several will very likely be wrong, and that is fine and interesting - but to ensure that a surprising result prompts scrutiny rather than a quiet adjustment of the analysis until it stops being surprising.

Related discipline: the parameter grids, seed counts and sweep ranges are fixed in configuration before the sweep runs. Extending a range after seeing results is legitimate only if declared as such in the paper.


---


## 8. The regeneration test

The acceptance test for the whole protocol, and the one Oliver should apply directly.

He picks any figure or table in the draft at random. On a clean checkout of the repository, it is regenerated from the raw audio by a single command, and the output matches what is in the manuscript. Nothing else is permitted: no manual steps, no cached intermediate files, no numbers carried over from a previous run.

If this cannot be done, the protocol has failed regardless of how carefully everything else was executed, because it means some part of the result exists only inside a process nobody can re-enter. It should be run at least twice - once at the week eight decision gate, when fixing problems is still cheap, and once before submission.

Releasing the code alongside the dataset, which the paper wants to do in any case, makes this test available to reviewers and readers as well. That is the strongest available answer to the original concern: the work is not a black box if anyone can open it.


---


## 9. Review practices

- **R1 Equation-by-equation reading.** Simon reads each encoder implementation against the corresponding equations in the proposal, line by line, before that encoder is used for any reported result. Slow, and the only thing that catches a correct implementation of a wrong equation.
- **R2 Cold review.** Code is reviewed in a fresh session with the expected result withheld. The assistant is substantially better at finding faults in code presented cold than in code it wrote earlier in the same conversation, where it tends to defend its own reasoning.
- **R3 Adversarial review.** For any headline result, ask a fresh session to argue that it is wrong and to list the most likely ways the pipeline could produce that number spuriously. Then check the list.
- **R4 Source verification.** Every citation, published figure and claim about standard practice traced to a primary source before it enters the manuscript. No exceptions for claims that sound familiar.
- **R5 Log precedence.** Where the assistant contradicts the decisions log or README, the log wins and the contradiction is noted.

---


## 10. Working agreement

Three points of process, which matter more than any individual test.

First, implementation speed is capped by review speed. The assistant can produce code far faster than it can be checked, and it lacks the instinct that makes a research student say that a number looks odd. If code is generated faster than Simon can reconstruct what it does, the checks become theatre. Deliberately slowing implementation to the rate at which it can be understood is a requirement of this protocol, not a concession.

Second, no result enters the decisions log or the draft until its Layer 1 and Layer 2 tests pass. Provisional numbers have a way of becoming final ones.

Third, this is the ordinary supervisor-and-student problem with two differences: the rate of output is much higher, and the assistant does not get uneasy when something is wrong. Both differences push in the same direction, toward more verification against independent ground truth and less reliance on anyone finding the code convincing.


---


## 11. Declaration of AI assistance

The paper should state plainly how the work was produced. A draft form, for Oliver to adjust and to check against the target journal's policy, which should be confirmed early since requirements vary:

"Implementation code for this study was written with substantial assistance from an AI coding assistant. All encoder implementations were validated against analytic known-answer tests derived from their defining equations; pipeline integrity was checked with leakage, alignment and baseline controls; and one encoder was independently reimplemented for cross-validation. All results are reproducible from the accompanying repository. The authors take full responsibility for the correctness of the work."

This is stronger than saying nothing. It is accurate, it describes verification that most purely human-written pipelines do not receive, and it removes any later question about disclosure.


---


## Appendix: pre-run checklist

To be satisfied before any result is reported.

- All G1 to G8 generic tests pass for the encoder in question.
- All F1 to F5 front-end tests pass.
- The encoder-specific tests of Sections 3.3 to 3.9 pass.
- C1 upper-bound anchor lands in the published band.
- C3 shuffled-label control returns chance.
- C4 split disjointness asserted in the run log.
- C5 deliberate misalignment produces the expected accuracy drop.
- C6 budget cross-check agrees.
- Three seeds run; spread recorded.
- Commit hash, config and seed recorded in the results manifest.
- Prediction for this result recorded and dated beforehand; any contradiction investigated in writing.