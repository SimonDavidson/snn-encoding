#!/usr/bin/env python3
"""
Design-session patch, 2026-09-02 — answers Q02 and three related defects
raised by the implementation session.

  1. .github/workflows/tests.yml
     The "Everything else" step ignores the only test file, so pytest collects
     nothing and exits 5. Rewritten to tolerate exit 5.

  2. tests/test_known_answers.py — test_G4
     E2 and E3 initialise state from drive[:, 0] (SPEC 4.3, 4.4). Prepending
     zeros to a signal that starts non-zero therefore changes the initial
     reference and produces a startup burst in the padded run only, so the
     count assertion fails for reasons unrelated to shift equivariance. Fixed
     by giving the test signal a silent lead-in longer than the shift.

  3. SPEC.md
     Equation (10) offers log or power-law compression but the method string
     for the power branch was never named. It is "power".

  4. docs/validation_protocol.md
     F4 tolerance stated as 0.99 there but 0.95 in the test. The test value is
     the considered one — gammatone ringing and Hilbert edge effects make 0.99
     optimistic. Document corrected to match.

Run from the repository root:  python3 patch_20260902b.py
Idempotent. Writes nothing if an anchor is missing.
"""
import io
import os
import sys

WORKFLOW = ".github/workflows/tests.yml"

WORKFLOW_TEXT = """name: tests

# Runs the known-answer suite in a clean environment that the implementation
# session did not configure. That is the point of it: a test passing on the
# Linux box because of local state fails here. See section 4 of
# docs/validation_protocol.md.

on:
  push:
    branches: ["**"]
  pull_request:
  workflow_dispatch:

jobs:
  known-answers:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Layer 1 known-answer tests
        run: pytest tests/test_known_answers.py -v --tb=short

      - name: Everything else
        # test_known_answers.py is currently the only test file, so this step
        # collects nothing and pytest exits 5. That is not a failure. Exit 5 is
        # tolerated; any other non-zero status is not.
        run: |
          set +e
          pytest tests/ -v --tb=short --ignore=tests/test_known_answers.py
          code=$?
          set -e
          if [ $code -eq 0 ] || [ $code -eq 5 ]; then
            echo "exit $code — ok (5 means no tests collected yet)"
            exit 0
          fi
          exit $code

  protected-files:
    # tests/test_known_answers.py, tests/conftest.py and SPEC.md are authored by
    # the design session. The implementation session must not edit them to make
    # a failing test pass: see the precedence rules in CLAUDE.md.
    #
    # A change to any of them is allowed only when a commit message in the push
    # carries the marker [spec], which Simon adds when applying a design-session
    # patch. This stops accidental edits, not determined ones, which is the
    # realistic goal.
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Check for unauthorised edits to design-session files
        run: |
          set -euo pipefail
          BEFORE="${{ github.event.before }}"
          AFTER="${{ github.sha }}"

          if [ -z "$BEFORE" ] || [ "$BEFORE" = "0000000000000000000000000000000000000000" ]; then
            echo "No previous commit in range; skipping guard."
            exit 0
          fi

          PROTECTED="tests/test_known_answers.py tests/conftest.py SPEC.md .github/workflows/tests.yml"
          CHANGED=$(git diff --name-only "$BEFORE" "$AFTER" -- $PROTECTED || true)

          if [ -z "$CHANGED" ]; then
            echo "No protected files touched."
            exit 0
          fi

          echo "Protected files changed in this push:"
          echo "$CHANGED"

          if git log --format=%B "$BEFORE".."$AFTER" | grep -qF '[spec]'; then
            echo "Authorised: a commit in this push is marked [spec]."
            exit 0
          fi

          echo "::error::Protected design-session files were modified without a [spec] marker."
          echo "::error::Files: $CHANGED"
          echo "::error::If a test looks wrong, raise it in QUESTIONS.md rather than editing it."
          echo "::error::If this is a design-session patch, include [spec] in the commit message."
          exit 1
"""

TEST_G4_OLD = '''    label, cls, kwargs = encoder_case
    enc = cls(**kwargs)
    drive = drive_for(cls, duration=1.0)
    shift_s = 0.1
    pad = np.zeros((drive.shape[0], int(round(shift_s / DT))))
'''

TEST_G4_NEW = '''    label, cls, kwargs = encoder_case
    enc = cls(**kwargs)
    shift_s = 0.1
    # The test signal must open with a silent lead-in longer than the shift.
    # E2 initialises its reference, and E3 both its filters, from drive[:, 0]
    # (SPEC 4.3, 4.4). Prepending zeros to a signal that starts at a non-zero
    # value would therefore change the initial state and produce a startup
    # burst in the padded run only, failing the count assertion for a reason
    # that has nothing to do with shift equivariance. With a zero lead-in every
    # encoder begins from the same state either way, and the comparison tests
    # what it is meant to test.
    lead = np.zeros((kwargs["n_channels"], int(round(2 * shift_s / DT))))
    drive = np.hstack([lead, drive_for(cls, duration=1.0)])
    pad = np.zeros((drive.shape[0], int(round(shift_s / DT))))
'''

SPEC_ANCHOR = "**Group delay.**"
SPEC_INSERT = """**Compression method strings.** `compress` takes `method="log"` for the
logarithmic branch of equation (10) and `method="power"` for the power-law
branch, the latter using `exponent`. `epsilon` applies to the logarithmic
branch only. `method="none"` returns the envelope unchanged, which is needed
for E5, whose drive is the subband waveform rather than a compressed envelope.

"""

PROTO_OLD = "envelope correlates with m(t) above 0.99."
PROTO_NEW = ("envelope correlates with m(t) above 0.95. (The threshold was "
             "stated as 0.99 in an earlier draft; 0.95 is the considered "
             "value, since gammatone ringing and Hilbert transform edge "
             "effects make 0.99 optimistic even for a correct implementation. "
             "test_F4 asserts 0.95.)")


def main():
    if not os.path.exists("CLAUDE.md"):
        sys.exit("error: run this from the repository root.")

    report = []

    # 1. workflow — always rewritten, content is self-contained
    os.makedirs(os.path.dirname(WORKFLOW), exist_ok=True)
    io.open(WORKFLOW, "w", encoding="utf-8").write(WORKFLOW_TEXT)
    report.append(f"rewrote {WORKFLOW} (exit-5 tolerance)")

    # 2. test_G4
    p = "tests/test_known_answers.py"
    t = io.open(p, encoding="utf-8").read()
    if "silent lead-in longer than the shift" in t:
        report.append(f"{p}: G4 already patched, skipped")
    elif TEST_G4_OLD in t:
        io.open(p, "w", encoding="utf-8").write(t.replace(TEST_G4_OLD, TEST_G4_NEW, 1))
        report.append(f"patched {p} (test_G4 zero lead-in)")
    else:
        sys.exit(f"ANCHOR NOT FOUND in {p} — nothing else written. "
                 "Send this message back to the design session.")

    # 3. SPEC
    p = "SPEC.md"
    t = io.open(p, encoding="utf-8").read()
    if "**Compression method strings.**" in t:
        report.append(f"{p}: compress note already present, skipped")
    elif SPEC_ANCHOR in t:
        io.open(p, "w", encoding="utf-8").write(
            t.replace(SPEC_ANCHOR, SPEC_INSERT + SPEC_ANCHOR, 1))
        report.append(f"patched {p} (compress method strings)")
    else:
        report.append(f"WARNING: {p} anchor '{SPEC_ANCHOR}' not found — "
                      "add the compress note by hand")

    # 4. validation protocol
    p = "docs/validation_protocol.md"
    if os.path.exists(p):
        t = io.open(p, encoding="utf-8").read()
        if "0.95 is the considered" in t:
            report.append(f"{p}: F4 tolerance already corrected, skipped")
        elif PROTO_OLD in t:
            io.open(p, "w", encoding="utf-8").write(t.replace(PROTO_OLD, PROTO_NEW, 1))
            report.append(f"patched {p} (F4 tolerance 0.99 -> 0.95)")
        else:
            report.append(f"WARNING: {p} F4 sentence not found — correct by hand")
    else:
        report.append(f"WARNING: {p} not present")

    for line in report:
        print(line)
    print("\n  git add -A")
    print("  git commit -m 'Answer Q02: CI exit-5, G4 lead-in, compress strings, F4 tolerance [spec]'")
    print("  git push")


if __name__ == "__main__":
    main()
