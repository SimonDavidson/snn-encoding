# Decisions log

Append-only. Numbered, dated, one line each. Newest at the bottom.
This file is authoritative: where any session's reasoning conflicts with an
entry here, the entry wins. Superseded entries are marked SUPERSEDED BY Dnn
rather than deleted.

Format: `Dnn | YYYY-MM-DD | who | decision | rationale (one clause)`

---

D01 | 2026-08-20 | OR | Audio encoding only this study; vision kept in mind for future | scope deliverable in the time
D02 | 2026-08-20 | OR | Speaker identification removed as a probe task | not a target of the multimodal dataset
D03 | 2026-08-20 | SD+Claude | T2 becomes F0 contour estimation, absorbing the prosody task | probes the same source-retention property, needs no labels, permits speaker-disjoint splits
D04 | 2026-08-20 | OR | Target venue: Neuromorphic Computing and Engineering (IOP) | fit and open access
D05 | 2026-08-20 | OR | Channel count is a free swept parameter, not fixed to 700 | no obligation to match SHD tooling
D06 | 2026-08-20 | OR | Learned/task-trained encoders excluded | would bake a task into a general-purpose release
D07 | 2026-08-20 | OR | Dataset name: the MANCHESTER Dataset | —
D08 | 2026-08-20 | OR | SpiNNaker energy measurement out of scope; spike-count and information-per-spike metrics in scope now | staging
D09 | 2026-08-20 | OR | Oliver and Simon approach Wijekoon directly re Spiketrum; E7 not implemented from published description | avoid reimplementing a colleague's algorithm badly
D10 | 2026-08-20 | OR | Authors: Simon Davidson, Oliver Rhodes; others added if appropriate | —
D11 | 2026-08-20 | OR | Twelve-week schedule starts now, in parallel with the TIMIT licence question | Oliver away ~2 weeks; no reason to wait
D12 | 2026-08-20 | SD+Claude | Implementation runs in Claude Code on the Linux box; design stays in the Claude.ai project session | box runs continuously, laptop does not
D13 | 2026-08-20 | SD+Claude | Repository is the sole coordination medium; nothing said in either chat is durable unless written to a file here | neither session has memory or can see the other
D14 | 2026-08-20 | SD+Claude | Known-answer tests and SPEC.md authored by the design session; implementation session may not edit them | preserves the independence the validation protocol requires
D15 | 2026-08-20 | SD+Claude | Repo public, data never committed; GitHub Issues used as an async queue for Simon, not as a channel to the design session | design session can be read from but cannot be polled
D16 | 2026-08-20 | SD+Claude | Auto-continuation permitted for mechanical work only, not generative work | validation protocol section 10 caps implementation speed at review speed
D17 | 2026-09-02 | SD+Claude | LIF membrane potential clamped to reset during absolute refractory, drive discarded; refractory fixed at 0.0 for E1/E4 comparison runs | standard formulation with an exact rate ceiling, while zero refractory keeps E1 a clean non-adapting baseline for P-01
D18 | 2026-09-02 | SD+Claude | E2 lattice reference held as an integer index, r = r0 + m*C, not accumulated by repeated addition | float drift would erode the equation (16) bound over long utterances
D19 | 2026-09-02 | SD+Claude | Gammatone group delay uncompensated by default, compensation available as a declared swept option; setting reported in the paper | biologically faithful default, but it biases T3 timing and no test detects it
D20 | 2026-09-02 | Claude (impl remit) | E2 threshold comparison carries a 1e-9 tolerance in lattice units, and outstanding steps are measured as (u-r0)/C - m rather than (u - r0 - m*C)/C | drive landing exactly on a lattice point is routine, and without either measure double-rounding noise decides equation (14) and drops the crest event of every excursion
D21 | 2026-09-02 | SD+Claude | Equation (9) envelope cutoff is channel-relative, f_cut_c = min(f_cut, b_c), fourth order | a subband cannot carry envelope faster than its own bandwidth, and fixed-cutoff carrier leakage would make E1-E4 and E6 partly phase-locking in the channels carrying F0, blurring the E5 contrast that P-03 rests on
D22 | 2026-09-02 | SD+Claude | test_T2_4 builds its own signal with the endpoint forced equal to the first sample | eq (16) pins the net lattice displacement to zero only when the closure is exact; sine_drive samples a half-open interval
D23 | 2026-09-02 | SD+Claude | D20 promoted from implementation decision into SPEC 4.3 | Layer 3 requires an independent reimplementation of E2 compared event for event, which needs the tolerance in the contract
D24 | 2026-09-03 | SD+Claude | compensate_group_delay advances each channel by the summed declared lag of every stage in the envelope path, not the filterbank alone; a stage that cannot declare its lag raises | compensation applied in subbands cannot remove a lag added downstream, and under D21 the envelope lowpass is the larger contributor in exactly the channels where the gammatone delay is worst
D25 | 2026-09-03 | SD+Claude | test_F6 added, measuring onset spread across the bank with and without compensation on both envelope methods | third channel-dependent timing bias in a row that no test detected

D26 | 2026-09-03 | SD+Claude | E3 event rule is the SPEC 4.3 reference-lattice rule applied to d, spacing theta, anchored at d = 0; equation (21) and proposal 5.3 rewritten | no one-event-per-crossing rule can be a rate parameter, since its count is bounded by the number of excursions of d and saturates as theta falls
D27 | 2026-09-03 | SD+Claude | G3 additionally requires the event count to span at least 4x across the declared sweep, not merely to be monotonic | monotonicity is necessary but not sufficient; a candidate giving 52, 52, 52, 35, 0 passes the original test and cannot hit a matched budget
D28 | 2026-09-03 | SD+Claude | Exponential-filter discretisation alpha = exp(-dt/tau) restated in SPEC 1, covering equations (12), (18)-(19), (22)-(23) and (32) | stated in proposal 5.3 but SPEC cites equations by number only, and SPEC is the sole contract a Layer 3 reimplementation works from
D29 | 2026-09-03 | SD+Claude | test_T3_5 and test_T2_6 added; test_T3_1 docstring and the T3 block header corrected | the T3 block pinned the filters and the symmetry but not the event rule, and T3.1's stated ground for discriminating E3 from E2 was false
D30 | 2026-09-03 | Claude (impl remit) | E2 and E3 share one implementation of the SPEC 4.3 reference-lattice rule, parametrised by the anchor r0 | D26's single-factor contrast is a claim about the code as well as the study, and two copies could diverge while each still passed its own test block
D31 | 2026-09-03 | SD+Claude | test_T3_6 added, asserting E3 equals E2 applied to d; authored after the design session had read encoders.py, and marked as such in the file header and its own docstring | D30 made the single-factor contrast true by construction and tested by nothing, and a later un-sharing would break D26's central claim with no test noticing
D32 | 2026-09-03 | SD+Claude | SPEC 4.4 requires TemporalContrast to raise when tau_slow <= tau_fast | the guard was added within implementation remit, but a Layer 3 reimplementation works from SPEC alone and would not have it, and an inverted pair exchanges ON and OFF silently rather than failing
D33 | 2026-09-03 | SD+Claude | test_T3_5 docstring corrected: continuous peak 0.9048013 not 0.9048124, residual at 0.30 s 6.74e-3 not 2.5e-3, t* 3.99186 ms | Q08; both errors were the design session's, neither affected an assertion, and both were in values that exist specifically to be hand-checked by a Layer 3 reimplementer

D34 | 2026-09-04 | SD | Adaptation state `a` keeps decaying through an absolute refractory period and is not incremented within it | equation (23) has no refractory term and the threshold tracks spike history rather than the membrane, so clamping V says nothing about a

D35 | 2026-09-05 | Claude (impl remit) | Every reported number is produced by a script under `scripts/` driven by a committed JSON config under `configs/`, and registered by `spikeenc.provenance.record`, which writes the data file and the manifest entry together and refuses to run unless the script and config are themselves committed and unmodified | a commit hash records provenance only if the tree that produced the number is the tree the hash names, and untracked-file blindness in a plain dirty check would let a script record a result against a commit not containing it
D36 | 2026-09-05 | Claude (impl remit) | The equation (9) lowpass lag declared under D24 is the first moment of the designed digital filter's impulse response, sum(n*h[n])/sum(h[n]) | it is the DC group delay exactly for the filter actually used, avoids the transfer-function conversion SPEC 3 records as unreliable at the low channels' normalised cutoffs, and agrees with the analog Butterworth prototype to within 0.6 per cent so a Layer 3 reimplementation choosing either route lands in the same place
