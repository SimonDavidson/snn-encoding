# Lab notebook

Append-only, newest at the bottom. One entry per working session, from either
the implementation session or the design session.

Template — copy this block, do not reformat it:

```
## YYYY-MM-DD | session: implementation | code | design
**Did:**
**Tests:** (which passed, which failed, which are new)
**Results written:** (paths, and manifest entries added)
**Blocked on:**
**Next:**
```

---

## 2026-08-20 | session: design
**Did:** Proposal v2 issued incorporating Oliver's answers (D01-D11). Battery
reduced to three tasks; information-theoretic metrics added; E7 marked
provisional; accent-diversity risk added to stage two.
**Tests:** none yet — repository not created.
**Results written:** none.
**Blocked on:** TIMIT licence (O2); corpus specifics (O1).
**Next:** create repo, write interface spec and Layer 1 known-answer tests,
then implement the common front end and E1.

## 2026-08-20 | session: design
**Did:** Wrote SPEC.md (interface contract), tests/test_known_answers.py (Layer 1
suite, ~45 tests derived from equations 4-29), tests/conftest.py, CI workflow,
and the GitHub conventions section of CLAUDE.md. Verified every expected value
in the test suite arithmetically and independently of any implementation.
**Tests:** none pass — spikeenc does not exist yet. Expected: the suite was
written before the code, deliberately.
**Results written:** none.
**Blocked on:** nothing. Implementation can begin.
**Next (implementation session):** read SPEC.md, then build in this order —
(1) SpikeTrain and metrics, (2) Filterbank, until F1-F5 pass, (3) E1, until
T1.1-T1.3 pass, (4) E2, until T2.1-T2.5 pass. E2 is where the sharpest tests
are; do not move on until they are green.
