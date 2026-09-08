"""Build the one-page decisions brief for Oliver as a .docx.

A companion to the encoder survey report, not a summary of it: the survey says
what has been built, this says what cannot move without Oliver. Styling helpers
are imported from the report builder rather than restated, so the two documents
cannot drift apart visually and there is one palette in the project.

Deliberately one page. Every line that is not a decision or the cost of not
taking one has been cut.

    python scripts/build_oliver_brief.py

A PDF for printing is produced alongside with

    soffice --headless --convert-to pdf --outdir reports reports/<file>.docx

which is also how the one-page claim is checked: python-docx cannot paginate,
so "one page" is verified by converting and counting /Type /Page, not asserted.

Author:        Simon Davidson & Claude
Created:       2026-09-08
Last modified: 2026-09-08
"""
import datetime as _dt
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_encoder_report import (  # noqa: E402
    AMBER, INK, LILAC, NAVY, REPORT_VERSION, ROSE, ROOT, TEAL,
    _normalise_zip_times, _rule, body, callout, caption, commit,
    open_questions, table)

OUT = ROOT / "reports" / "spikeEncode_decisions_for_Oliver.docx"


def build(force=False):
    """Same overwrite guard as the survey report, for the same reason: the
    commit hash is embedded, so a rebuild replaces a copy that may already be
    in someone's inbox."""
    if OUT.exists() and not force:
        raise SystemExit(
            f"{OUT.name} already exists. The commit hash is embedded, so "
            f"rebuilding produces a different file and would replace a copy "
            f"that may already have been sent. Run with --force to replace it "
            f"deliberately.")
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(9.5)
    st.font.color.rgb = INK
    st.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    st.paragraph_format.space_after = Pt(4)
    st.paragraph_format.line_spacing = 1.0
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(1.6)
        s.top_margin = s.bottom_margin = Cm(1.3)

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(1)
    r = p.add_run("spikeEncode — decisions needed from Oliver")
    r.bold = True
    r.font.size = Pt(17)
    r.font.color.rgb = NAVY

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run(f"8 September 2026  ·  companion to the encoder survey, "
                  f"version {REPORT_VERSION}  ·  commit {commit()}")
    r.font.size = Pt(9.5)
    r.font.color.rgb = TEAL
    _rule(p)

    body(doc, "**Where the work is.** All six candidate encoders are implemented and "
              "tested, and the probe harness now runs all three tasks end to end with the "
              "non-spiking reference measured alongside. That is weeks 1–2 and 5–7 of the "
              "twelve-week plan, at day 19.", size=9.5)
    body(doc, "**The catch.** Every number so far is on a synthetic stand-in corpus, "
              "because there is still no TIMIT. The stand-in has known ground truth, which "
              "is what lets the pipeline controls actually fail — and they have, catching "
              "two specification errors that would have been invisible on real audio. But "
              "it cannot answer what the preliminary experiments exist to ask, and control "
              "C1 — the one saying the pipeline is calibrated rather than merely "
              "self-consistent — needs a real corpus.", size=9.5)

    rows = [
        ["O2", "TIMIT licence — does Manchester hold current LDC membership?",
         "The largest blocker in the project: control C1, P1's real answer, the week-4 "
         "decision gate, and the weeks 1–2 deliverable. Nineteen days with nothing logged; "
         "§9 names it the top risk because it is week-one work."],
        ["Q07", "Release format — are ON and OFF separate channel indices, or a polarity "
                "bit?",
         "The event file format, and controls C6 and C7 with it. Best settled before the "
         "featurisation is fixed, since doubling the channel count changes what the decoder "
         "receives. Interacts with the SHD convention, which is unipolar."],
        ["O3", "Spiketrum — the approach to Wijekoon.",
         "Whether E7 enters the comparison at all. Separately: the Spiketrum papers have "
         "not been read in full, and the survey's description is from abstracts."],
        ["Q28", "Do we make the stand-in corpus more speech-like, or wait for TIMIT?",
         "Whether further preliminary work is worth doing. Formant transitions would let "
         "P1 and P2 rehearse properly; waiting keeps the battery question on real speech."],
    ]
    table(doc, ["", "Decision", "What it is holding up"], rows,
          widths=[1.2, 6.0, 10.2], size=9,
          fills={(i, 0): ROSE for i in range(len(rows))})
    caption(doc, "Not blocking today: O1 corpus specifics, needed before stage two; O4 "
                 "whether an IOP read-and-publish agreement covers the article charge; O5 "
                 "alignment strategy, which depends on O1.")

    callout(doc, "One result worth a minute of the meeting.",
            "The study's central engineering question has its first number, and it does not "
            "favour the answer the field assumes. The mel reference costs 128,000 bit/s; the "
            "spiking encoder reaches 98.5 per cent of its accuracy only at **398,929 bit/s, "
            "three times the representation it is approximating**. The two cross near a "
            "fifth of that rate, where the encoder sits at ~92 per cent of the bound. Both "
            "figures depend on declared bit widths and the corpus is synthetic, so this is "
            "not yet a result — but it is the shape of the argument the paper will have to "
            "make.", fill=LILAC)

    n_open = len(open_questions())
    callout(doc, f"For information: {n_open} questions are open against the design "
                 f"session, up from nine two days ago.",
            "Expected shape rather than drift. An encoder arrives with a specification "
            "section and known-answer tests written from its equations, so it either passes "
            "or it does not; the harness has neither, the specification declaring the "
            "pipeline deliberately unspecified, so it generates questions instead of "
            "consuming answers. Six of the twenty are one question, and none needs Oliver.",
            fill=AMBER)

    body(doc, "**Nothing above blocks the next fortnight except O2.** With a corpus the "
              "harness runs as it stands and the first real Pareto fronts follow within "
              "days. Without one, what remains is consolidation rather than progress.",
              size=9.5)

    stamp = _dt.datetime(2026, 8, 20, 0, 0, 0)
    cp = doc.core_properties
    cp.created = cp.modified = stamp
    cp.author = cp.last_modified_by = "Simon Davidson & Claude"
    cp.title = "spikeEncode — decisions needed from Oliver"
    cp.revision = 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    _normalise_zip_times(OUT)
    print(f"written: {OUT}")
    return OUT


if __name__ == "__main__":
    import sys
    build(force="--force" in sys.argv)
