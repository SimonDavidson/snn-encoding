# Spike encoding for the MANCHESTER Dataset

Comparative study of candidate spike encodings for audio, to justify one for
release alongside DVS event-camera data.
Davidson & Rhodes, University of Manchester.

## Orientation

| File | What it is |
|---|---|
| `CLAUDE.md` | Standing brief for AI implementation sessions. Read first. |
| `SPEC.md` | Interface contract. Binding — the tests are written against it. |
| `DECISIONS.md` | Authoritative decision log. Wins over anyone's reasoning. |
| `NOTEBOOK.md` | Append-only session log. |
| `QUESTIONS.md` | Open questions needing design input. |
| `PREDICTIONS.md` | Pre-registered predictions. Recorded before runs. |
| `docs/proposal_v2.md` | The study design, with all equations. |
| `docs/validation_protocol.md` | How results are checked before publication. |

## Two sessions

Design and specification happen in a Claude.ai project session; implementation
happens in Claude Code on a Linux box. Neither can see the other, and neither
remembers anything between sessions. All coordination is through the files
above. See the GitHub conventions section of `CLAUDE.md`.

## Status

Scaffold only. No implementation yet. `pytest` currently fails at import,
which is the expected state: the known-answer tests were written from the
equations before the code existed.

## Data

Not in this repository and never will be. TIMIT is licensed by the LDC and
redistribution is prohibited. The MANCHESTER Dataset is unreleased.
