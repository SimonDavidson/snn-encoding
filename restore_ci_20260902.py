#!/usr/bin/env python3
"""
Recreate .github/workflows/tests.yml and record that .github/ is design-session
territory in CLAUDE.md.

The workflow directory was dropped when the scaffold tarball was extracted
(GUI extractors commonly skip dotfile directories). This also replaces the
original guard, which compared protected files against origin/main and so was
a no-op for commits landing directly on main.

Run from the repository root:   python3 restore_ci_20260902.py
Idempotent.
"""
import io
import os
import sys

WORKFLOW_DIR = ".github/workflows"
WORKFLOW = os.path.join(WORKFLOW_DIR, "tests.yml")

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
        run: pytest tests/ -v --tb=short --ignore=tests/test_known_answers.py

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

          # New branch or force push: no usable range, nothing to compare.
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

CLAUDE_NOTE = """
### Design-session files

These are authored by the design session and must not be edited by the
implementation session:

- `SPEC.md`
- `tests/test_known_answers.py`, `tests/conftest.py`
- `.github/workflows/tests.yml`
- `DECISIONS.md` — Simon writes this; append end-of-session entries only for
  decisions taken within your own remit, never design decisions

Changes to any of them are made by the design session and committed by Simon
with `[spec]` in the commit message, which is what the CI guard checks for. If
you believe one of these files is wrong, stop and write the argument in
`QUESTIONS.md`.
"""


def main():
    if not os.path.exists("CLAUDE.md"):
        sys.exit("error: CLAUDE.md not found. Run this from the repository root.")

    os.makedirs(WORKFLOW_DIR, exist_ok=True)
    io.open(WORKFLOW, "w", encoding="utf-8").write(WORKFLOW_TEXT)
    print(f"wrote {WORKFLOW}")

    claude = io.open("CLAUDE.md", encoding="utf-8").read()
    if "### Design-session files" in claude:
        print("CLAUDE.md already records the design-session file list; unchanged")
    else:
        io.open("CLAUDE.md", "a", encoding="utf-8").write(CLAUDE_NOTE)
        print("appended the design-session file list to CLAUDE.md")

    print("\nNext:")
    print("  gh auth refresh -h github.com -s workflow   # if the push is refused")
    print("  git add .github/workflows/tests.yml CLAUDE.md")
    print("  git commit -m 'Restore CI workflow and strengthen guard [spec]'")
    print("  git push")


if __name__ == "__main__":
    main()
