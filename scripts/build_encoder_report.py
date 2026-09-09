"""Build the encoder survey report as a .docx.

Narrative is authored here; every number is read from results/ and from the
manifest, so regenerating after a new run picks the new values up rather than
restating stale ones. Run:

    python scripts/build_encoder_report.py

Version 2 (2026-09-08) added the probe harness and the first task results.
Version 3 (2026-09-09) supersedes every task figure in it. The free parameters
were being selected by maximising the test score, which D71 forbids; all five
task results were re-run under selection inside the training split, and §13.4
reports how large the difference was. E7 is rewritten from the primary source
and E4's adaptation table is registered and withdrawn.

Author:        Simon Davidson & Claude
Created:       2026-09-06
Last modified: 2026-09-09
"""
import datetime as _dt
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent

#: Bumped whenever a version goes to Oliver, and carried in the filename so two
#: versions cannot be confused in an inbox. v1 (2026-09-06) covered E1-E4 and
#: the front end; v2 adds E5, E6, the probe harness and the first task results.
REPORT_VERSION = 3
OUT = ROOT / "reports" / f"spikeEncode_encoder_survey_v{REPORT_VERSION}.docx"

#: Corrections and additions owed to the *next* version, recorded when they are
#: found rather than when they can be applied — v2 had already gone to Oliver
#: when the first of these surfaced. Printed at the end of every build, so the
#: list is in front of whoever rebuilds at exactly the moment it is actionable
#: rather than sitting in a notebook entry nobody re-reads.
PENDING_NEXT_VERSION = [
    "§1.1 quotes E5's cycle-divisor span as 3.54x over the recorded sweep "
    "k = 1..16. D68 moved the registry operating point to k = 16, at which the "
    "design session reports 10.5x, but our own span measurement has not been "
    "re-centred and re-registered. Re-run measure_rate_parameter_span.py on a "
    "sweep centred at the new operating point before quoting either figure as "
    "settled.",
    "§5.7 of the proposal, and therefore any passage here that cites it for "
    "E7's channel count, is under query as Q42: the applied patch states a "
    "64-atom dictionary yielding 1920 channels and neither number occurs in "
    "the source. The only configuration the paper states is 40 kernels x 3 "
    "characteristic intensities = 120 channels. This report deliberately "
    "quotes the paper's figure and not the proposal's; reconcile once Q42 is "
    "answered.",
    "The T1 phone-inventory caveat owed under D81: TIMIT's 61-to-39 collapse "
    "is an American inventory and the MANCHESTER Dataset will not share it, so "
    "T1 accuracies are not directly comparable across the two stages. Needs a "
    "citation as well as a sentence.",
]

#: Known-answer suite totals at the last recorded run. Not derived, because
#: running the suite inside the build would make the report slow and able to
#: fail for a reason unrelated to the report; stated here so a mismatch with
#: NOTEBOOK.md is one grep away.
SUITE = {"passed": 84, "failed": 0, "skipped": 1, "collected": 85}
#: Per encoder: (passed, collected). E6's tenth test is test_G7b, which skips
#: because E6 declares no refractory.
ENCODER_TESTS = {"E1": (10, 10), "E2": (16, 16), "E3": (13, 13),
                 "E4": (11, 11), "E5": (12, 12), "E6": (9, 10)}

# --- palette --------------------------------------------------------------
NAVY = RGBColor(0x1F, 0x38, 0x64)
TEAL = RGBColor(0x1B, 0x6B, 0x7A)
SLATE = RGBColor(0x44, 0x44, 0x55)
INK = RGBColor(0x22, 0x26, 0x2B)
HDR_FILL = "1F3864"
SUB_FILL = "2E5C8A"
ALT_FILL = "EEF2F7"
GREEN = "C6E0B4"
AMBER = "FFE699"
GREY = "DCDCDC"
ROSE = "F6C9C9"
LILAC = "E4DDF0"


def _normalise_zip_times(path):
    """A .docx is a zip, and zip members carry mtimes. Rewrite them all to a
    fixed date so the file is byte-identical when the content is."""
    fixed = (1980, 1, 1, 0, 0, 0)
    src = zipfile.ZipFile(path)
    tmp = Path(str(path) + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for info in sorted(src.infolist(), key=lambda i: i.filename):
            data = src.read(info.filename)
            ni = zipfile.ZipInfo(info.filename, date_time=fixed)
            ni.compress_type = info.compress_type
            ni.external_attr = info.external_attr
            out.writestr(ni, data)
    src.close()
    shutil.move(str(tmp), str(path))


def load(name):
    p = ROOT / "results" / f"{name}.json"
    return json.load(open(p)) if p.exists() else None


def open_questions():
    """Count questions whose Answer block is still open, from QUESTIONS.md.

    Derived rather than stated: the count moved from 9 to 20 in two days, and
    it is exactly the kind of number that goes stale in a document without
    anyone noticing.
    """
    import re
    text = (ROOT / "QUESTIONS.md").read_text(encoding="utf-8")
    blocks = re.split(r"^### (Q\d+) — ", text, flags=re.M)[1:]
    return [q for q, b in zip(blocks[::2], blocks[1::2])
            if b.split("**Answer:**")[-1].strip().startswith("(open")]


def commit():
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()


# --- low-level helpers ----------------------------------------------------
def shade(cell, fill):
    el = OxmlElement("w:shd")
    el.set(qn("w:val"), "clear")
    el.set(qn("w:color"), "auto")
    el.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(el)


def cell_text(cell, text, bold=False, colour=None, size=9, align=None):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align if align is not None else WD_ALIGN_PARAGRAPH.LEFT
    for chunk, strong, slant in _markup(str(text)):
        r = p.add_run(chunk)
        r.bold = bold or strong
        r.italic = slant
        r.font.size = Pt(size)
        if colour is not None:
            r.font.color.rgb = colour
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)


def body(doc, text, size=10.5, italic=False, space_after=7):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.12
    for chunk, bold, slant in _markup(text):
        r = p.add_run(chunk)
        r.bold = bold
        r.italic = italic or slant
        r.font.size = Pt(size)
    return p


def _markup(text):
    """Minimal **bold** and *italic* support so the narrative can emphasise.

    Italic was written in the narrative from v1 onward and was never rendered —
    `*before*` reached the reader with its asterisks intact, in v1 and v2 and in
    the copies Oliver holds. Adding it here rather than deleting the markup
    from the prose, because the emphasis was wanted where it was written.

    Returns `(chunk, bold, italic)`. Bold is checked first so `**x**` is not
    read as an empty italic followed by a stray one.
    """
    out, buf, i = [], "", 0

    def flush():
        nonlocal buf
        if buf:
            out.append((buf, False, False))
            buf = ""

    while i < len(text):
        if text.startswith("**", i):
            j = text.find("**", i + 2)
            if j == -1:
                buf += text[i:]
                break
            flush()
            out.append((text[i + 2:j], True, False))
            i = j + 2
        elif text[i] == "*":
            j = text.find("*", i + 1)
            # A lone asterisk, or one spanning a paragraph's worth of text, is
            # punctuation rather than markup. Left alone.
            if j == -1 or j == i + 1:
                buf += text[i]
                i += 1
                continue
            flush()
            out.append((text[i + 1:j], False, True))
            i = j + 1
        else:
            buf += text[i]
            i += 1
    flush()
    return out or [("", False, False)]


def equation(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(text)
    r.font.name = "Consolas"
    r.font.size = Pt(9.5)
    r.font.color.rgb = TEAL
    return p


def h1(doc, text, page_break=True):
    if page_break:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(17)
    r.font.color.rgb = NAVY
    _rule(p)
    return p


def h2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(11)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(12)
    r.font.color.rgb = TEAL
    return p


def _rule(p):
    pPr = p._p.get_or_add_pPr()
    bd = OxmlElement("w:pBdr")
    bot = OxmlElement("w:bottom")
    bot.set(qn("w:val"), "single")
    bot.set(qn("w:sz"), "8")
    bot.set(qn("w:space"), "2")
    bot.set(qn("w:color"), "1F3864")
    bd.append(bot)
    pPr.append(bd)


def table(doc, headers, rows, widths=None, fills=None, header_fill=HDR_FILL,
          size=9):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, htxt in enumerate(headers):
        c = t.rows[0].cells[i]
        cell_text(c, htxt, bold=True, colour=RGBColor(0xFF, 0xFF, 0xFF), size=size)
        shade(c, header_fill)
    # Repeat the header on every page the table spills onto; without this a
    # split table shows bare numbers with no idea what column they are in.
    trPr = t.rows[0]._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader")
    th.set(qn("w:val"), "true")
    trPr.append(th)
    _keep_rows_together(t)
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for ci, val in enumerate(row):
            cell_text(cells[ci], val, size=size)
            fill = None
            if fills and (ri, ci) in fills:
                fill = fills[(ri, ci)]
            elif ri % 2 == 1:
                fill = ALT_FILL
            if fill:
                shade(cells[ci], fill)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(3)
    return t


def _keep_rows_together(t):
    for row in t.rows:
        trPr = row._tr.get_or_add_trPr()
        el = OxmlElement("w:cantSplit")
        trPr.append(el)


def kv_table(doc, rows, widths):
    """Key/value table with no header row."""
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for ri, (k, v) in enumerate(rows):
        cells = t.add_row().cells
        cell_text(cells[0], k, bold=True, size=9)
        cell_text(cells[1], v, size=9)
        shade(cells[0], ALT_FILL)
        for i, w in enumerate(widths):
            cells[i].width = Cm(w)
    _keep_rows_together(t)
    doc.add_paragraph().paragraph_format.space_after = Pt(3)
    return t


def caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(10)
    for chunk, bold, _ in _markup(text):
        r = p.add_run(chunk)
        r.bold = bold
        r.italic = True          # captions are italic throughout
        r.font.size = Pt(8.5)
        r.font.color.rgb = RGBColor(0x60, 0x66, 0x70)
    return p


def callout(doc, title, text, fill=AMBER):
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    c = t.rows[0].cells[0]
    c.text = ""
    p = c.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run(title + "  ")
    r.bold = True
    r.font.size = Pt(9.5)
    for chunk, bold, slant in _markup(text):
        rr = p.add_run(chunk)
        rr.bold = bold
        rr.italic = slant
        rr.font.size = Pt(9.5)
    shade(c, fill)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return t


# ==========================================================================
# Front matter and overview
# ==========================================================================
def front_matter(doc, ctx):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("spikeEncode")
    r.bold = True
    r.font.size = Pt(30)
    r.font.color.rgb = NAVY

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(16)
    r = p.add_run(f"Candidate spike encodings for audio — encoder survey, "
                  f"version {REPORT_VERSION}")
    r.font.size = Pt(14)
    r.font.color.rgb = TEAL
    _rule(p)

    kv_table(doc, [
        ["Study", "Comparing candidate spike encodings for audio, to justify one for "
                  "release alongside DVS event-camera data"],
        ["Authors", "Simon Davidson, Oliver Rhodes (University of Manchester)"],
        ["Target venue", "Neuromorphic Computing and Engineering (IOP) — D04"],
        ["Version", f"{REPORT_VERSION} — supersedes version 2 of 8 September 2026. "
                    f"Every task figure in v2 is replaced: see 'What changed' "
                    f"below and §13.4"],
        ["Report generated", f"{ctx['date']} from commit {ctx['commit']}"],
        ["Suite status", f"{ctx['passed']} passed, {ctx['failed']} failed, "
                         f"{ctx['skipped']} skipped (Layer 1 known-answer tests)"],
        ["Recorded results", f"{ctx['n_results']} entries in results/manifest.json"],
        ["Open questions", f"{ctx['n_open']} awaiting the design session"],
    ], widths=[4.0, 12.4])

    body(doc, "This report summarises every encoder in the study — those implemented, "
              "those blocked or deliberately excluded, and the two reference points that "
              "frame the "
              "comparison. For each it gives the encoding methodology and its defining "
              "equations, the design parameters available for tuning and which of them "
              "are swept, the characteristics of the output the encoder produces, and, "
              "where measurements exist, what has actually been recorded.")
    body(doc, "Two conventions of the study bear on how the numbers here should be read. "
              "First, **no encoder is ever compared to another at a single operating "
              "point**: the rate parameter is swept and the non-dominated points form a "
              "Pareto front in the plane of event rate against accuracy, so a parameter "
              "that cannot move the event count is not merely inconvenient but "
              "disqualifying. Second, **every reported number is written to results/ and "
              "registered in results/manifest.json** with the script, config, commit and "
              "seed that produced it; figures quoted in this report that carry a manifest "
              "identifier are reproducible from the repository, and those that do not are "
              "marked as such.")

    callout(doc, "Status at a glance.",
            f"**All six candidate encoders are implemented and the known-answer suite is "
            f"green** — {ctx['passed']} passed, {ctx['failed']} failed, {ctx['skipped']} "
            f"skipped. E5's two former failures were the open questions Q19 and Q20 and "
            f"were closed by D68. E7 is deliberately not implemented (D09), and §10 is "
            f"rewritten from the primary source, which v2 had not read. **All three probe "
            f"tasks run end to end** with the non-spiking reference R2 alongside, on a "
            f"synthetic stand-in because O2 was open when these were run. The LDC account "
            f"has since been accepted and stage one starts on TIMIT as soon as the data "
            f"lands (D81).", fill=LILAC)

    callout(doc, "What changed since version 2, and why it is not a small revision.",
            "v2's task figures were selected against the numbers they reported. The "
            "alignment offset — and for P1 the featurisation time constant — were chosen "
            "by maximising the score on the *test* split, which §13 of the validation "
            "protocol forbids and which D71 now rules out mechanically. All five task "
            "results have been re-run with every free parameter selected on "
            "speaker-disjoint folds inside the training split. **T1 and R2 are unaffected: "
            "the bias was exactly zero at every budget and every seed. T2, T3 without "
            "context, and P1 are not**, and P1's index changes sign at two of the three "
            "budgets where it is defined. §13.4 gives the measured size of the bias, which "
            "is the one thing this correction makes it possible to state rather than "
            "assume. Superseded entries stay visible in the manifest with their values "
            "intact, per the convention in §14.", fill=ROSE)


def overview(doc, ctx):
    h1(doc, "1.  The comparison and how encoders are judged")
    body(doc, "Six candidate encoders (E1–E6) plus a provisional third-party encoder (E7) "
              "are compared against two reference points, on three probe tasks chosen for "
              "opposing demands: T1 phone classification, T2 fundamental-frequency contour "
              "estimation, and T3 boundary detection. The tasks are chosen to pull in "
              "different directions, so that an encoder cannot win on all three by being "
              "generically good — an encoder that discards fine timing should do well on "
              "T1 and badly on T2, and one that is silent in steady state should do well "
              "on T3 and badly on T2.")

    h2(doc, "1.1  The rate parameter, and why it is the gating property")
    body(doc, "Every encoder declares one constructor parameter as its RATE_PARAM, the "
              "single knob that moves its event count, together with a RATE_DIRECTION "
              "saying which way. Matched-budget comparison requires that this parameter "
              "actually work: decision D27 requires the event count to be monotonic in the "
              "declared direction **and** to span at least a factor of four across the "
              "standard sixteen-fold sweep. Monotonicity alone is insufficient, and the gap "
              "is not hypothetical — a candidate rule considered for E3 gave counts of 52, "
              "52, 52, 35, 0 across the sweep, which is monotonic, has distinct endpoints, "
              "and is useless.")
    body(doc, "This requirement held up two encoders for a week, and it is worth stating "
              "plainly because it is the property most likely to disqualify a scheme that "
              "otherwise looks reasonable. Both E5 and E6 failed it at the rate parameters "
              "originally specified, for entirely different reasons. E6's was resolved by "
              "redefining its gate relative to the largest frame energy (D43), which spans "
              "12.36×; E5's rate parameter was replaced with a cycle divisor (D40), which "
              "reaches 3.54× over the sweep k = 1…16 — short of the required four. Q19 "
              "diagnosed why: refractory caps the count at the low-k end, so three of the "
              "five sweep points were measuring the refractory ceiling rather than the "
              "parameter. D68 moved the registry operating point to k = 16, where the span "
              "is reported as 10.5×; D27 was not relaxed. Our own span measurement has not "
              "yet been re-centred on the new operating point, so 3.54× is what this "
              "report can cite from the manifest. "
              "Measuring the span of a proposed rate rule *before* writing the encoder is "
              "now standard practice in this project, precisely because it is cheap and "
              "catches this class of problem at the specification stage.")

    h2(doc, "1.2  Drive kinds, and the signal chain they name points on")
    body(doc, "The shared front end of §3 is a chain, and DRIVE_KIND names which point on "
              "it an encoder taps:")
    equation(doc, "audio  →  gammatone filterbank  →  x_c  subband waveform  "
                  "→  envelope  →  u_c  compressed envelope")
    body(doc, "**Encoders declare one of two values.** Most take the compressed subband "
              "envelope u_c ('envelope'). E5 alone takes the subband waveform x_c "
              "('subband'), because its entire purpose is to represent the carrier that "
              "the envelope discards. SPEC §4.1 admits these two and no others, and the "
              "value determines what the harness feeds an encoder when bypassing the front "
              "end.")
    body(doc, "**The summary table in §2 shows a third value, 'audio', on three rows, and "
              "it is not a DRIVE_KIND.** E7, R1 and R2 are not Encoder subclasses and "
              "declare nothing. For those rows the column means *bypasses the shared front "
              "end and consumes the waveform directly* — R2 builds its own mel filterbank, "
              "R1 is an external dataset, and E7 decomposes the signal over its own "
              "dictionary. The distinction matters because the whole force of §3 is that "
              "differences between encoders are attributable to the event rule and not to "
              "the filtering; a row marked 'audio' is a row where that guarantee does not "
              "apply. Raised by Simon against v2 and corrected here.")

    h2(doc, "1.3  Output format")
    body(doc, "Every encoder returns a SpikeTrain: arrays of channel index, timestamp in "
              "seconds, and polarity in {+1, −1}, in canonical order — time ascending, then "
              "channel, then polarity descending. Encoders declaring a single polarity emit "
              "all +1. Whether ON and OFF should be exposed to downstream users as separate "
              "channel indices rather than as a polarity bit is an open release-format "
              "question (Q07) and does not affect any encoder.")


def summary_table(doc, ctx):
    h1(doc, "2.  All encoders at a glance")
    rows = [
        ["E1", "LIF", "Rate-like anchor", "theta", "envelope", "Implemented", "10 / 10"],
        ["E2", "SendOnDelta", "Send-on-delta (DVS-symmetric)", "C", "envelope", "Implemented", "16 / 16"],
        ["E3", "TemporalContrast", "Onset/offset bandpass", "theta", "envelope", "Implemented", "13 / 13"],
        ["E4", "ALIF", "Adaptive-threshold LIF", "theta_0", "envelope", "Implemented", "11 / 11"],
        ["E5", "PhaseLocked", "Phase-locked fine structure", "cycle_divisor", "subband", "Implemented", "10 / 12"],
        ["E6", "TTFS", "Time-to-first-spike", "e_frac", "envelope", "Implemented", "9 / 10"],
        ["E7", "Spiketrum", "Event-based temporal matching pursuit (third-party)", "atoms / s", "audio", "Not implemented", "—"],
        ["R1", "Lauscher / SHD", "Reference channel format", "—", "audio", "Not started", "—"],
        ["R2", "Mel filterbank", "Non-spiking reference", "—", "audio", "Implemented", "n/a"],
    ]
    status_fill = {"Implemented": GREEN, "Blocked": AMBER,
                   "Not implemented": GREY, "Not started": GREY}
    fills = {}
    for ri, r in enumerate(rows):
        fills[(ri, 5)] = status_fill[r[5]]
    table(doc, ["", "Class", "Scheme", "RATE_PARAM", "Drive", "Status", "Known-answer tests"],
          rows, widths=[1.1, 3.0, 4.6, 2.0, 1.9, 2.3, 2.6], fills=fills)
    caption(doc, "Test counts are the encoder's own T-block plus its parametrised share of "
                 "the generic G block. Every block is now complete: E4's former failure "
                 "test_T4_3 was replaced under D39, and E5's two — test_G3[E5] (Q19, the "
                 "span) and test_T5_3 (Q20) — were closed by D68. E6's tenth test is "
                 "test_G7b, which skips because E6 declares no refractory period. **The "
                 "Drive column carries two meanings**: on E1–E6 it is the declared "
                 "DRIVE_KIND of SPEC §4.1, which is 'envelope' or 'subband' and nothing "
                 "else; on E7, R1 and R2 the value 'audio' marks a row that bypasses the "
                 "shared front end altogether and is not a DRIVE_KIND at all. See §1.2. R2 "
                 "is a reference rather than an encoder and has no known-answer block; it "
                 "is covered by implementation-session tests instead.")

    body(doc, "The six implemented encoders group into two integrating schemes (E1, E4), "
              "two change-based schemes (E2, E3), one carrier-locked scheme (E5) and one "
              "latency scheme (E6). That is the axis the study is built around: E1 against "
              "E4 isolates spike-frequency adaptation, and E2 against E3 isolates the "
              "bandpass, because decision D30 makes the two share one implementation of the "
              "event rule so that nothing else differs between them. Both contrasts are "
              "single-factor by construction rather than by inspection. E1 against E6 is "
              "the sparsest contrast in the set — all information in count against all "
              "information in timing — and is what prediction P-04 turns on.")


def front_end(doc, ctx):
    h1(doc, "3.  The common front end")
    body(doc, "All candidates share a first stage, so that differences between "
              "them are attributable to the event-generation rule rather than to incidental "
              "differences in filtering. The stage is a gammatone filterbank, the standard "
              "computational approximation to the frequency selectivity of the basilar "
              "membrane, followed by envelope extraction and a compressive nonlinearity.")
    equation(doc, "g_c(t) = a · t^(n−1) · exp(−2π b_c t) · cos(2π f_c t + φ_c),   t ≥ 0    (4)")
    body(doc, "with order n = 4 and bandwidth b_c = 1.019 · ERB(f_c), the equivalent "
              "rectangular bandwidth following Glasberg and Moore, equation (5). Centre "
              "frequencies are placed uniformly on the ERB-rate scale of equation (6) "
              "between f_min and f_max, with the endpoints hit exactly. The implementation "
              "is FIR — each channel's taps are equation (4) sampled and truncated — so "
              "what the known-answer tests check is the thing the filterbank actually uses, "
              "with no cascade-of-biquads approximation in between.")

    h2(doc, "3.1  Front-end parameters")
    table(doc, ["Parameter", "Default", "Role", "Swept?"], [
        ["n_channels", "—", "Number of filterbank channels", "Yes — free axis (D05)"],
        ["f_min, f_max", "50 Hz, 8000 Hz", "Frequency limits of the bank", "Yes"],
        ["spacing", "erb", "erb | mel | linear placement of centre frequencies", "Yes"],
        ["order", "4", "Gammatone order n in equation (4)", "No"],
        ["envelope method", "hilbert", "Equation (8) analytic magnitude, or (9) rectify-lowpass", "Yes"],
        ["f_cut", "1000 Hz", "Ceiling on the equation (9) cutoff; actual is min(f_cut, b_c)", "Declared"],
        ["compress method", "log", "Equation (10): log, power (exponent 0.3), or none", "Yes"],
        ["compensate_group_delay", "False", "Advance each channel by its declared path lag", "Yes — binary axis (D19)"],
    ], widths=[4.2, 2.6, 7.4, 3.3])
    caption(doc, "Channel count is explicitly a free swept parameter and not fixed to the "
                 "700 channels of the SHD format (D05). Prediction P-08 holds that these "
                 "front-end parameters matter more than the choice of encoding scheme.")

    h2(doc, "3.2  Two channel-dependent timing biases, and what was done about them")
    body(doc, "The envelope cutoff of equation (9) is written in the proposal as a single "
              "value for the whole bank. It is not implemented that way. Decision D21 makes "
              "it channel-relative, f_cut_c = min(f_cut, b_c), on the physical ground that a "
              "subband of bandwidth b_c cannot carry envelope modulation faster than b_c, so "
              "a cutoff above the channel bandwidth admits carrier without admitting any "
              "more envelope. The study-design reason is sharper: carrier leaking into the "
              "low-channel envelope would make E1–E4 and E6 partly phase-locking encoders in "
              "exactly the channels where F0 and its low harmonics live, and prediction P-03 "
              "turns on the contrast between those encoders and E5 on T2.")
    r = load("envelope_cutoff_comparison")
    if r:
        rows = []
        for ch in r["by_channel"]:
            a, b = ch["fc_over_4"], ch["d21"]
            rows.append([f"{ch['f_c_hz']:.0f}", f"{ch['b_c_hz']:.1f}",
                         f"{a['raw_correlation']:.4f}", f"{b['raw_correlation']:.4f}",
                         f"{a['lag_corrected_correlation']:.4f}",
                         f"{b['lag_corrected_correlation']:.4f}",
                         f"{a['carrier_leakage']:.2e}", f"{b['carrier_leakage']:.2e}"])
        table(doc, ["f_c (Hz)", "b_c (Hz)", "raw f_c/4", "raw D21",
                    "lag-corr. f_c/4", "lag-corr. D21", "leak f_c/4", "leak D21"], rows,
              widths=[2.0, 2.0, 2.2, 2.2, 2.6, 2.6, 2.3, 2.3])
        caption(doc, "Manifest id envelope_cutoff_comparison. Envelope against a known 5 Hz "
                     "modulator on an AM tone per channel, 24-channel bank 100–6000 Hz. On raw "
                     "correlation D21 looks slightly worse everywhere; once the filter's own "
                     "lag is removed both sit at 0.9999 or better, so the deficit is delay, "
                     "not distortion. The metric that discriminates is carrier leakage, where "
                     "D21 wins at every channel by a margin that grows with frequency.")
    body(doc, "The second bias is group delay. A gammatone filter responds later in a "
              "low-frequency channel than a high one, which is biologically faithful and is "
              "the default, but it is also a systematic frequency-dependent bias on event "
              "timing and therefore on T3. Decision D24 requires that when compensation is "
              "enabled each channel is advanced by the summed declared lag of **every stage "
              "in the path**, not the filterbank alone — because compensation applied inside "
              "the subband stage cannot remove a lag introduced downstream of it, and under "
              "D21 the envelope lowpass is the larger contributor in exactly the channels "
              "where the gammatone delay is worst.")
    g = load("front_end_group_delay_residual")
    if g:
        rows = []
        for meth, v in g["by_method"].items():
            m = v["test_F6_margin"]
            rows.append([meth,
                         f"{v['uncompensated_spread_s']*1000:.2f} ms",
                         f"{v['compensated_spread_s']*1000:.2f} ms",
                         f"{v['test_F6_limit_s']*1000:.2f} ms",
                         "undefined" if m is None else f"{m:.2f}×",
                         f"{v['residual_fraction']*100:.1f} %"])
        table(doc, ["Envelope method", "Uncompensated spread", "Compensated",
                    "test_F6 limit", "Margin", "Residual"], rows,
              widths=[3.6, 3.4, 2.6, 2.6, 2.2, 2.0])
        caption(doc, "Manifest id front_end_group_delay_residual. Onset spread across a "
                     "16-channel bank, 150–6000 Hz, on a broadband click.")
        callout(doc, "Report this alongside any T3 result.",
                "SPEC §3 requires the measured residual spread to be quoted with any T3 "
                "figure taken with compensation on. The residual is **2.50 ms** for the "
                "rectify-lowpass path and zero for the Hilbert path. It is not an "
                "implementation shortfall: the declared lag is the lowpass group delay at "
                "DC, and a rectified carrier burst experiences about 1.09× the gammatone "
                "lag where the DC value predicts 0.87×. Compensation is exact only for "
                "components slow relative to the stage bandwidths.", fill=LILAC)


def e1(doc, ctx):
    h1(doc, "4.  E1 — Leaky integrate-and-fire")
    callout(doc, "Status: implemented, all tests green.",
            "The rate-like anchor, and the encoder against which any claim of temporal "
            "coding must be made. Also the non-adapting arm of the E1-against-E4 contrast "
            "that prediction P-01 rests on.", fill=GREEN)

    h2(doc, "4.1  Methodology")
    body(doc, "Each channel drives a leaky integrate-and-fire neuron. The membrane "
              "potential integrates the compressed envelope and decays exponentially toward "
              "rest; when it reaches threshold the neuron emits an event and the potential "
              "is reset to zero. In discrete time, with β = exp(−Δt / τ_m) and Θ the "
              "Heaviside step:")
    equation(doc, "V_c[n] = β · V_c[n−1] · (1 − s_c[n−1]) + (1 − β) · g · u_c[n]    (12)")
    equation(doc, "s_c[n] = Θ( V_c[n] − θ )    (13)")
    body(doc, "The (1 − s_c[n−1]) factor implements a hard reset: the carried-over potential "
              "is zeroed on the step after an event. A soft reset, subtracting θ rather than "
              "zeroing, preserves information about how far the potential overshot and is "
              "available as the reset='soft' variant.")

    h2(doc, "4.2  Design parameters")
    table(doc, ["Parameter", "Default", "Role", "Swept?"], [
        ["theta", "1.0", "Firing threshold — the RATE_PARAM", "Yes — the rate axis"],
        ["tau_m", "0.02 s", "Membrane time constant; sets integration window", "Secondary axis"],
        ["gain", "1.0", "Scales drive into current, g in equation (12)", "No"],
        ["refractory", "0.0", "Minimum interval between events in a channel", "Fixed at 0.0 — see below"],
        ["reset", "hard", "hard zeroes the potential; soft subtracts theta", "Secondary axis"],
    ], widths=[3.4, 2.2, 8.0, 3.9])

    callout(doc, "Why refractory is pinned at zero.",
            "Two independent reasons, both declared rather than incidental. First, clamping "
            "the potential during recovery discards incoming drive, which suppresses the "
            "response to sustained strong input — that is mildly **adaptive**, in the same "
            "direction as spike-frequency adaptation, and E1 must be a clean non-adapting "
            "baseline for the E1-against-E4 contrast. Second, refractory is a second "
            "rate-limiting mechanism alongside theta; sweeping both would confound the "
            "matched-budget comparison. It is therefore a declared constant and never a "
            "swept axis (D17).")

    h2(doc, "4.3  Output characteristics")
    body(doc, "**Unipolar** — every event carries polarity +1, so no polarity bit is "
              "required and the OFF half of the feature vector stays at zero. For a constant "
              "input the firing rate is approximately proportional to input amplitude above "
              "threshold, so information resides principally in how many events a channel "
              "produces and only weakly in exactly when. Output is dense in loud regions and "
              "silent below threshold, with no privileging of onsets over sustained regions. "
              "Under saturating drive the interspike interval is exactly the refractory "
              "period and the rate ceiling exactly its reciprocal, which is what makes the "
              "rate ceiling analytically checkable.")
    body(doc, "Predicted behaviour (P-01 and §5.1): solid on T1, since spectral shape "
              "survives a rate code well; poor on T2, since phase information is discarded "
              "at the envelope stage; poor on T3 relative to the change-based encoders.")

    h2(doc, "4.4  Verification")
    table(doc, ["Test", "What it pins down", "Result"], [
        ["T1.1", "Constant drive gives the closed-form interspike interval", "Pass"],
        ["T1.2", "Subthreshold drive is silent", "Pass"],
        ["T1.3", "Refractory caps the rate at exactly 1/refractory", "Pass"],
        ["G1–G8", "Determinism, silence, rate span, shift equivariance, event validity, featurisation", "Pass (7 of 7)"],
    ], widths=[2.2, 10.4, 4.9],
        fills={(i, 2): GREEN for i in range(4)})
    body(doc, "E1's rate parameter is well behaved: theta moves the event count "
              "monotonically and spans comfortably more than the factor of four D27 "
              "requires, so matched-budget comparison against it is straightforward to "
              "arrange. No open question touches E1.")


def e2(doc, ctx):
    h1(doc, "5.  E2 — Send-on-delta")
    callout(doc, "Status: implemented, all tests green.",
            "The DVS-symmetric scheme, and the candidate for format unification with the "
            "visual modality. Its principal claim is format symmetry with event-camera "
            "data, not peak accuracy on any task.", fill=GREEN)

    h2(doc, "5.1  Methodology")
    body(doc, "Rather than integrating the signal, this scheme tracks it. A reference level "
              "r_c is maintained per channel, and an event is emitted whenever the compressed "
              "envelope has moved a fixed distance C from that reference, the reference then "
              "advancing by C in the direction of travel:")
    equation(doc, "if u_c(t) − r_c ≥ C :  emit (c, t, +1),  r_c ← r_c + C    (14)")
    equation(doc, "if r_c − u_c(t) ≥ C :  emit (c, t, −1),  r_c ← r_c − C    (15)")
    body(doc, "Because u_c is log-compressed, the condition is a fixed-**contrast** "
              "condition: an event marks a fixed multiplicative change in envelope "
              "amplitude, not a fixed additive one. That is precisely the DVS pixel rule "
              "with log intensity replaced by log subband envelope, which is what makes this "
              "scheme the candidate for unification with the event-camera format.")
    body(doc, "Two properties make it attractive independently of that. The reference is a "
              "running reconstruction of the signal, and the reconstruction error is bounded "
              "by construction; and the event count over an interval has a closed form in "
              "the total variation of the compressed envelope, so the rate parameter has an "
              "exact and monotonic relationship to event count:")
    equation(doc, "| u_c(t) − r_c(t) | < C  for all t    (16)          N_c = (1/C) ∫ | du_c/dt | dt    (17)")
    body(doc, "A required behaviour follows from equation (16) and is easy to get wrong: at "
              "each sample the encoder emits events **until** |drive − reference| < C, so a "
              "fast transient spanning several thresholds emits several events at the same "
              "timestamp. With refractory > 0 this is capped and the bound degrades; with "
              "refractory = 0 the bound holds strictly.")

    callout(doc, "The tension worth flagging in the paper.",
            "These two properties are in direct tension with the privacy considerations of "
            "the study. A scheme with a guaranteed reconstruction bound is, by that very "
            "guarantee, one from which the audio can be substantially recovered.", fill=ROSE)

    h2(doc, "5.2  Design parameters")
    table(doc, ["Parameter", "Default", "Role", "Swept?"], [
        ["C", "0.1", "Contrast threshold — the RATE_PARAM; rate ∝ 1/C by eq (17)", "Yes — the rate axis"],
        ["refractory", "0.0", "Caps multiple events at one timestamp", "Fixed at 0.0 — degrades eq (16)"],
        ["reference_update", "lattice", "lattice advances by exactly ±C; exact sets r to the current value", "Yes — declared variant"],
    ], widths=[3.8, 2.2, 8.2, 3.3])
    body(doc, "The two reference-update variants are a genuine modelling choice rather than "
              "an implementation detail. Advancing by exactly C keeps all reference values on "
              "a fixed lattice and makes reconstruction exact to within one quantisation "
              "step; setting the reference to the current signal value lets it drift off the "
              "lattice but tracks fast transients more responsively. The DVS convention is "
              "closer to the latter, so both are implemented and the choice is swept.")

    h2(doc, "5.3  Two numerical requirements that are contract, not detail")
    body(doc, "The reference is held as an **integer lattice index** m, with the value "
              "computed as r = r0 + m·C rather than accumulated by repeated addition of C. "
              "Repeated floating-point addition accumulates rounding error across a long "
              "utterance and erodes the very bound of equation (16) that the tests assert "
              "(D18). Separately, outstanding lattice steps are measured as (u − r0)/C − m, "
              "never as (u − r0 − m·C)/C, and the threshold comparison carries a tolerance of "
              "1e−9 lattice units (D20, promoted into the specification as D23).")
    callout(doc, "Why the tolerance is needed.",
            "Drive landing exactly on a lattice point is routine, not exceptional. With "
            "u = 1.0 and r = 9C = 0.9, equation (14) asks whether u − r ≥ C. In exact "
            "arithmetic 0.1 ≥ 0.1 fires; in doubles the subtraction yields "
            "0.09999999999999998 and it does not — so the crest event of every excursion is "
            "dropped and the descent begins one step in, costing two events per half cycle. "
            "The tolerance can only fire an event **early**, never late, so the bound of "
            "equation (16) tightens rather than loosens. This is in the contract because "
            "Layer 3 calls for an independent reimplementation compared event for event, and "
            "two implementations differing here would disagree at every crest.")

    h2(doc, "5.4  Output characteristics")
    body(doc, "**Bipolar** — ON and OFF events, and the polarity counts balance exactly over "
              "any closed loop of the drive. Output is concentrated where the signal changes "
              "and, unlike E3, accumulates: a slow ramp of sufficient total extent will "
              "eventually generate events no matter how gradual it is, because the scheme "
              "tracks absolute displacement rather than rate of change. Event count scales "
              "as the total variation of the compressed envelope divided by C, giving an "
              "unusually exact handle on the rate–accuracy trade-off.")
    body(doc, "Predicted behaviour (P-05): strong on T3, since events are generated exactly "
              "where the signal changes; adequate on T1; poor on T2.")

    h2(doc, "5.5  Verification")
    table(doc, ["Test", "What it pins down", "Result"], [
        ["T2.1", "Reconstruction error bounded by C — four signal types", "Pass"],
        ["T2.2", "Event count follows total variation, equation (17)", "Pass"],
        ["T2.3", "Linear ramp gives regular intervals", "Pass"],
        ["T2.4", "ON/OFF balance over a closed loop", "Pass — see D22"],
        ["T2.5", "Halving C doubles the event count", "Pass"],
        ["T2.6", "Constant drive is silent", "Pass"],
        ["G1–G8", "Generic block, including a rate span of about 16× over the sweep", "Pass (7 of 7)"],
    ], widths=[2.2, 10.4, 4.9], fills={(i, 2): GREEN for i in range(7)})
    body(doc, "T2.4 is worth a note because it was the one test whose premise turned out to "
              "be false rather than its assertion. The fixture signal was built over a "
              "half-open interval and so did not return to its starting value, leaving a net "
              "lattice displacement of −1 and an ON/OFF count of 199 against 200. The "
              "encoder was right; the test now builds its own signal with the endpoint forced "
              "equal to the first sample (D22).")


def e3(doc, ctx):
    h1(doc, "6.  E3 — Temporal contrast with onset and offset channels")
    callout(doc, "Status: implemented, all tests green.",
            "A change-based scheme like E2, but bandpass rather than integrating in its "
            "response to change. Shares E2's event rule by construction, so the "
            "E2-against-E3 comparison isolates the bandpass and nothing else.", fill=GREEN)

    h2(doc, "6.1  Methodology")
    body(doc, "Two exponential lowpass filters with different time constants are applied to "
              "the compressed envelope and their difference taken — a difference of "
              "exponentials in time, the temporal analogue of a difference-of-Gaussians in "
              "space:")
    equation(doc, "y_fast[n] = α_f · y_fast[n−1] + (1 − α_f) · u_c[n]    (18)")
    equation(doc, "y_slow[n] = α_s · y_slow[n−1] + (1 − α_s) · u_c[n]    (19)")
    equation(doc, "d_c[n] = y_fast[n] − y_slow[n]    (20)")
    body(doc, "with α = exp(−Δt / τ) and τ_slow > τ_fast. Events are emitted by the "
              "reference-lattice rule of E2 applied to d_c rather than to the envelope, the "
              "lattice anchored at d = 0 with spacing theta:")
    equation(doc, "r_c[n] = m_c[n]·θ,  m_c[0] = 0 ;  emit ON while d − r ≥ θ ;  emit OFF while d − r ≤ −θ    (21)")

    callout(doc, "Why a reset rule and not a crossing rule — this changed the specification.",
            "The natural reading of equation (21) is a crossing rule, and it cannot work. "
            "Any rule emitting at most one event per crossing has an event count bounded "
            "above by the number of excursions of d through the threshold band, which is a "
            "property of the drive and of the time constants — **not of theta**. As theta "
            "falls the count saturates rather than growing, so theta cannot act as a rate "
            "parameter. Measured over an eight-fold sweep: a crossing rule rearmed at the "
            "threshold gives 85, 104, 117, 114, 0; one rearmed through zero gives 52, 52, "
            "52, 35, 0; the lattice rule gives 888, 432, 191, 69, 0. Reading (21) as a bare "
            "level condition is no better — it emits on 93 per cent of samples. Equation "
            "(21) and proposal §5.3 were rewritten (D26, from Q06).")

    body(doc, "The consequence to be explicit about is that E3's event count on a transient "
              "scales with the transient's amplitude divided by theta, rather than with the "
              "number of transients. That is a modelling choice made under pressure from an "
              "evaluation requirement, and the proposal now states it as such. For T3 it is "
              "defensible on its own terms — a boundary with greater spectral contrast "
              "accumulates proportionally more evidence — but it is a choice, not a "
              "consequence of the difference-of-exponentials.")

    h2(doc, "6.2  Design parameters")
    table(doc, ["Parameter", "Default", "Role", "Swept?"], [
        ["theta", "0.5 (spec) / 0.2 (test point)", "Lattice spacing on d — the RATE_PARAM", "Yes — the rate axis"],
        ["tau_fast", "0.001 s", "Fast filter time constant, equation (18)", "Secondary axis"],
        ["tau_slow", "0.05 s", "Slow filter time constant, equation (19)", "Secondary axis"],
        ["refractory", "0.0", "Declared constant, never swept", "No — fixed at 0.0"],
        ["reference_update", "lattice", "For symmetry with E2; not a swept axis here", "No"],
    ], widths=[3.8, 3.4, 7.0, 3.3])
    body(doc, "Thresholds are symmetric — theta_plus equals theta_minus equals theta — with "
              "the asymmetric case available as a secondary axis. Both filters are "
              "initialised to drive[:, 0], so a constant drive produces no startup transient "
              "and hence no events at all.")

    callout(doc, "The constructor is required to raise.",
            "TemporalContrast raises ValueError when tau_slow ≤ tau_fast. An inverted pair "
            "negates equation (20), which **exchanges the ON and OFF channels rather than "
            "failing** — and that is the one error in this encoder no test in the T3 block "
            "would catch, because test_T3_4 checks that negating the drive swaps the "
            "polarities, which an already-swapped encoder satisfies. Stated as a "
            "requirement rather than left to the implementation, since a Layer 3 "
            "reimplementation works from the specification alone (D32).")

    h2(doc, "6.3  Output characteristics")
    body(doc, "**Bipolar**, with separate onset and offset responses. The defining "
              "behavioural difference from E2 is worth being precise about, because the two "
              "are easily conflated. E2 accumulates; E3 is bandpass. A ramp slower than "
              "tau_slow produces no response at all from E3, because both filters track it "
              "equally and their difference stays near zero. E3 is therefore **silent during "
              "steady state regardless of level**, and responds only to changes fast relative "
              "to its slow time constant. This makes it a closer model of the onset-sensitive "
              "cells of the cochlear nucleus, and it produces markedly sparser output on "
              "sustained sounds.")
    body(doc, "Predicted behaviour (P-02): strongest of the candidates on T3; competitive on "
              "T1, since phone changes are exactly transitions; poor on T2, possibly very "
              "poor, since a scheme silent during steady state discards precisely the "
              "sustained periodicity that F0 estimation depends on. If that prediction holds "
              "it is a clean demonstration that the probe battery spans the demand space.")

    h2(doc, "6.4  Verification")
    table(doc, ["Test", "What it pins down", "Result"], [
        ["T3.1", "Steady state is permanently silent", "Pass"],
        ["T3.2", "Slow ramp separates E3 from E2 — the bandpass is present", "Pass"],
        ["T3.3", "Difference of exponentials peaks at the geometric mean", "Pass"],
        ["T3.4", "Negating the drive swaps ON and OFF", "Pass"],
        ["T3.5", "Step response gives closed-form event counts", "Pass"],
        ["T3.6", "E3 equals E2 applied to d — the shared rule holds", "Pass"],
        ["G1–G8", "Generic block, including a rate span of about 13× over the sweep", "Pass (7 of 7)"],
    ], widths=[2.2, 10.4, 4.9], fills={(i, 2): GREEN for i in range(7)})
    body(doc, "test_T3_6 deserves comment as a piece of protocol. Decision D30 made E2 and "
              "E3 share one implementation of the lattice rule, parametrised by the anchor, "
              "so that the single-factor contrast is true of the code and not merely of the "
              "intention. That made the contrast true by construction and tested by nothing "
              "— a later un-sharing would have broken D26's central claim with no test "
              "noticing. T3.6 asserts the equality directly, and is marked in its own "
              "docstring as having been authored after the design session had read the "
              "implementation (D31).")


def e4(doc, ctx):
    h1(doc, "7.  E4 — Adaptive-threshold LIF")
    callout(doc, "Status: implemented; one test open on a specification question (Q10).",
            "E1 augmented with spike-frequency adaptation. The sharpest test in the set of "
            "the claimed dissociation between T1 and T2, and the encoder for which the "
            "predicted results are most specific.", fill=AMBER)

    h2(doc, "7.1  Methodology")
    body(doc, "The threshold is made dynamic: each event raises it by a fixed increment, and "
              "it decays back toward baseline with its own time constant. Equations (12) and "
              "(13) are otherwise unchanged, substituting the dynamic threshold for the "
              "fixed one:")
    equation(doc, "θ_c[n] = θ_0 + a_c[n]    (22)")
    equation(doc, "a_c[n] = ρ · a_c[n−1] + Δ_a · s_c[n−1],   ρ = exp(−Δt / τ_a)    (23)")
    body(doc, "This is the ALIF neuron used by Bittar and Garner and by Yin and colleagues, "
              "and it is the mechanism most often credited when spiking networks outperform "
              "their non-adaptive counterparts on speech. Its functional effect is a "
              "first-order highpass applied to the firing rate: transients pass, sustained "
              "drive is progressively suppressed. That is an implicit form of the invariance "
              "T1 wants, since a speaker-dependent sustained level is attenuated while "
              "phone-dependent transitions are preserved — and by the same token it is "
              "expected to be actively harmful for T2.")

    callout(doc, "Implemented by generalising E1, not by duplicating it.",
            "With Δ_a = 0 the adaptation state stays exactly 0.0 — ρ·0.0 is 0.0, and Δ_a·s "
            "is 0.0 for either value of s — so the threshold is θ_0 + 0.0, which is θ_0 to "
            "the bit. E4 at zero adaptation is therefore **bit-identical** to E1 by "
            "construction rather than by numerical coincidence, and an edit touching one "
            "encoder cannot leave the other behind. One routine serves both.")

    h2(doc, "7.2  Design parameters")
    table(doc, ["Parameter", "Default", "Role", "Swept?"], [
        ["theta_0", "1.0", "Baseline threshold — the RATE_PARAM", "Yes — the rate axis"],
        ["delta_a", "0.5", "Threshold increment per event, Δ_a in equation (23)", "Yes — adaptation axis"],
        ["tau_a", "0.1 s", "Adaptation decay time constant", "Yes — adaptation axis"],
        ["tau_m", "0.02 s", "Membrane time constant", "Secondary axis"],
        ["gain", "1.0", "Scales drive into current", "No"],
        ["refractory", "0.0", "Fixed at 0.0 for comparison runs, as for E1 (D17)", "No"],
    ], widths=[3.4, 2.2, 8.0, 3.9])
    body(doc, "Adaptation strength and time constant are swept as a **separate axis** rather "
              "than folded into the rate parameter, because the interesting result is how "
              "accuracy on T1 and T2 moves in opposite directions as adaptation strength "
              "increases. Decision D34 settles a subtlety of equation (23): the adaptation "
              "state keeps decaying through an absolute refractory period and is not "
              "incremented within it, because equation (23) has no refractory term and the "
              "threshold tracks spike history rather than the membrane, so clamping the "
              "potential says nothing about a.")

    h2(doc, "7.3  Output characteristics")
    body(doc, "**Unipolar**, like E1. Output is onset-weighted: a channel fires rapidly at "
              "the start of a sustained stimulus and then settles to a lower steady rate. "
              "Steady-state suppression is monotone in adaptation strength — that is "
              "test_T4_4, and it passes. The onset-to-steady-state **contrast** is not "
              "monotone, which is the substance of the open question below.")
    body(doc, "Predicted behaviour (P-01): T1 accuracy rises and T2 accuracy falls as "
              "adaptation strength increases.")

    h2(doc, "7.4  Verification, and the open question")
    table(doc, ["Test", "What it pins down", "Result"], [
        ["T4.1", "Zero adaptation reduces exactly to E1 — bit-identical", "Pass"],
        ["T4.2", "Threshold decays geometrically after a single event", "Pass"],
        ["T4.3", "Adaptation emphasises onsets, monotonically in delta_a", "Fail — Q10"],
        ["T4.4", "Adaptation suppresses the steady state", "Pass"],
        ["G1–G8", "Generic block", "Pass (7 of 7)"],
    ], widths=[2.2, 10.4, 4.9],
        fills={(0, 2): GREEN, (1, 2): GREEN, (2, 2): ROSE, (3, 2): GREEN, (4, 2): GREEN})

    body(doc, "test_T4_3 asserts a monotonicity the ALIF does not have, and the encoder is "
              "not at fault. Three separate readings of equation (23) — literal, "
              "add-then-decay, and increment-at-own-sample — give identical event counts, "
              "which is the tell: when no implementation choice moves the number, the "
              "disagreement is with the claim rather than with the code. Re-measured over a "
              "wider grid than the test samples, onset emphasis (the ratio of steady-state "
              "to first interspike interval) runs:")
    pts = {f"{r['delta_a']:g}": r for r in ctx["e4"]["points"]}
    order = ["0", "0.25", "0.5", "1", "2", "4", "8"]
    peak = f"{ctx['e4']['peak_delta_a']:g}"
    table(doc, ["delta_a"] + order,
          [["ISI_ss / ISI_1"] + [f"{pts[k]['isi_ratio']:.2f}" for k in order],
           ["ISI_1 (ms)"] + [f"{pts[k]['isi_first_s'] * 1e3:.0f}" for k in order]],
          widths=[3.4, 1.8, 1.8, 1.8, 1.8, 1.8, 1.8, 1.8],
          fills={(0, 1 + order.index(peak)): AMBER})
    caption(doc, "Registered as manifest entry e4_adaptation_ratio. A 5 s step; the "
                 "steady-state interval is the mean of the final five intervals rather "
                 "than a fixed time window, because at delta_a = 8 the interval is longer "
                 "than the 200 ms window first tried and the ratio came back undefined at "
                 "exactly the adaptation strengths the measurement is about.")
    callout(doc, "This table does not reproduce the one in versions 1 and 2, and those "
                 "numbers are withdrawn.",
            "v1 and v2 reported a peak of 2.45 near delta_a = 1. The registered "
            f"measurement peaks at {ctx['e4']['peak_ratio']:.2f} at delta_a = {peak} and "
            "declines monotonically above it. The earlier table was produced before D35 "
            "was being applied to it and **its parameters were never written down**, so "
            "the discrepancy cannot be resolved by inspection — which is precisely the "
            "failure D35 exists to prevent, arriving in the one table this report had "
            "left unregistered. The qualitative finding survives: the ratio is "
            "non-monotone in delta_a with an interior peak. Its location does not, and "
            "the location is the part that bears on P-01.", fill=ROSE)
    body(doc, "The mechanism is straightforward once seen: adaptation from the first spike "
              "suppresses the second, so strong adaptation lengthens the **onset** interval "
              f"as well as the steady-state one — from "
              f"{pts['0']['isi_first_s'] * 1e3:.0f} ms to "
              f"{pts['8']['isi_first_s'] * 1e3:.0f} ms across this sweep — and the two "
              "rates re-converge.")

    callout(doc, "This bears on a pre-registered prediction, not just on a red tick.",
            "P-01 predicts T1 accuracy rising and T2 falling \"as adaptation strength "
            "increases\". If the onset emphasis underneath that is non-monotone with a peak "
            "with an interior peak, then a sweep spanning the peak could confirm or "
            "contradict P-01 according to which side its points land on. **The delta_a "
            "sweep range should be chosen with the peak located first — and v2 located it "
            "in the wrong place, which is the practical cost of the unregistered table.** PREDICTIONS.md has not been "
            "edited — §7 of the validation protocol forbids it once a run has started, and "
            "restating a prediction is the design session's call in any case.", fill=ROSE)


def e5(doc, ctx):
    h1(doc, "8.  E5 — Phase-locked fine structure")
    callout(doc, "Status: implemented, 10 of 12 known-answer tests passing.",
            "The only encoder that consumes the subband waveform rather than the envelope, "
            "because its entire purpose is to represent the carrier the envelope discards. "
            "Prediction P-03 rests on the contrast between E5 and the envelope encoders on "
            "T2. Its rate parameter was replaced under D40 — `threshold` spanned only "
            "1.04×, because the event count is capped by the carrier's own crossing rate — "
            "and the replacement `cycle_divisor`, which keeps every k-th gated crossing, "
            "reaches 3.48× against D27's required 4×. That shortfall is Q19 and is the "
            "cause of one of the two remaining failures; the other is Q20. Both were raised "
            "before the encoder was written, and neither is a defect in it.", fill=AMBER)

    h2(doc, "8.1  Methodology")
    body(doc, "Two forms are specified. The deterministic form emits at each upward zero "
              "crossing of the subband waveform where the envelope exceeds a threshold, "
              "subject to a refractory period. The stochastic form drives an inhomogeneous "
              "Poisson process whose intensity is a compressed, saturating function of the "
              "half-wave rectified subband:")
    equation(doc, "z_c(t) = [ max(x_c(t), 0) ]^γ    (24)")
    equation(doc, "λ_c(t) = λ_max · z_c(t) / ( z_c(t) + z_0 )    (25)")
    body(doc, "The diagnostic that matters for this encoder is vector strength, which "
              "measures directly the property the scheme exists to preserve — one for perfect "
              "locking, zero for events uniformly distributed in phase:")
    equation(doc, "VS_c = (1/N) · | Σ_k exp( j·2π·f_c·t_k ) |    (26)")
    body(doc, "Biological phase locking degrades above a few kilohertz and this is modelled: "
              "above a cutoff f_lock, channels revert to envelope-driven LIF behaviour as in "
              "E1. The value of f_lock is a swept parameter and the sweep is informative in "
              "itself, since it directly controls how much speaker information the encoding "
              "retains.")

    h2(doc, "8.2  Design parameters")
    table(doc, ["Parameter", "Default", "Role", "Swept?"], [
        ["threshold", "0.05", "Envelope gate on the crossings — the declared RATE_PARAM", "Intended rate axis — see Q11"],
        ["gamma", "1.0", "Compression exponent γ in equation (24)", "Secondary axis"],
        ["f_lock", "1500 Hz", "Above this, channels revert to envelope-driven LIF", "Yes — informative axis"],
        ["refractory", "0.001 s", "Minimum interval between events in a channel", "Secondary axis"],
        ["mode", "deterministic", "deterministic zero crossings, or poisson via eq (25)", "Yes"],
        ["centre_frequencies", "None", "Needed to decide which channels exceed f_lock", "Passed through"],
        ["lambda_max, z_0", "not exposed", "Equation (25) parameters — **not constructor arguments**", "Cannot currently be set"],
    ], widths=[4.2, 2.6, 7.2, 3.5],
        fills={(0, 3): AMBER, (6, 1): ROSE, (6, 2): ROSE, (6, 3): ROSE})

    h2(doc, "8.3  Why it is blocked — the rate parameter does not work")
    body(doc, "Before writing any of the encoder, the specified deterministic rule was "
              "simulated directly on the standard sweep drive. The declared RATE_PARAM moves "
              "the event count by a factor of **1.04** across the sixteen-fold sweep, against "
              "the factor of four D27 requires.")
    r = load("e5_rate_parameter_span")
    if r:
        rows = [["threshold"] + [f"{v:g}" for v in r["param_values"]],
                ["events"] + [str(c) for c in r["counts"]]]
        table(doc, ["", "0.25×", "0.5×", "1×", "2×", "4×"], rows,
              widths=[3.2, 2.4, 2.4, 2.4, 2.4, 2.4],
              fills={(1, i): ROSE for i in range(1, 6)})
        d = r["diagnostics"]
        caption(doc, f"Manifest id e5_rate_parameter_span. Span "
                     f"{r['span']:.3f}× against a required 4×; monotonic, but far too flat. "
                     f"Total upward zero crossings in the drive: "
                     f"{d['upward_zero_crossings_total']}. Envelope 25th percentile "
                     f"{d['envelope_p25']:.3f}, against a top threshold of "
                     f"{max(r['param_values']):g}.")
    body(doc, "The diagnosis is structural rather than a matter of tuning. The event count is "
              "bounded above by the number of upward zero crossings in the subband, which is "
              "a property of the **carrier**, and the threshold only gates quiet passages — "
              "of which this drive has few, its envelope 25th percentile sitting above the "
              "largest threshold in the sweep. No value of the declared parameter can make "
              "this rule hit a matched budget.")
    callout(doc, "The mode that has a working rate parameter cannot be expressed.",
            "Proposal §5.5 nominates λ_max for the stochastic form, which would be a genuine "
            "rate parameter. But equation (25)'s λ_max and z_0 are **not constructor "
            "arguments** in the specified signature, so the deterministic mode has a "
            "parameter that does not work and the stochastic mode has one that cannot be "
            "set. Resolving this changes the constructor signature, which is why the encoder "
            "has not been written — writing it first would risk rework of the interface "
            "(Q11).", fill=ROSE)

    h2(doc, "8.4  A second, independent block")
    body(doc, "Q12 records two further under-specifications that a Layer 3 reimplementation "
              "would resolve differently. First, the specification does not say **which "
              "envelope** gates the zero crossings — the Hilbert envelope and the "
              "rectify-lowpass envelope give different gates, and the difference is visible "
              "in the counts. Second, it does not say what parameters the LIF fallback uses "
              "above f_lock. Both are subordinate to Q11 in the sense that the constructor "
              "signature must be settled first, but neither is implied by it.")
    body(doc, "The practical consequence of the first gap is already measurable. The "
              "recorded span above reproduces the earlier probe's conclusion exactly — 1.039 "
              "against 1.04 — but not its absolute counts, which were 7116 falling to 6864 "
              "where this run gives 6996 falling to 6732. Neither probe recorded which "
              "envelope it used, and that is almost certainly the whole of the difference. "
              "The current recorded run declares the Hilbert envelope in its config.")

    h2(doc, "8.5  Output characteristics, as specified")
    body(doc, "**Unipolar**, and by a wide margin the densest of the candidates: phase "
              "locking at kilohertz rates implies high event counts in exactly the channels "
              "where events are cheapest to generate. All information resides in the precise "
              "timing of events relative to the carrier, which is what vector strength "
              "measures and what the jitter corruption operator is designed to degrade in an "
              "interpretable way.")
    callout(doc, "The most interesting predicted outcome in the study.",
            "P-03 predicts E5 much the strongest on T2, by a wide margin; not obviously "
            "better than E1 on T1, since it adds carrier detail that phone identity does not "
            "need; and expensive. That makes it **the encoder most likely to be dominated at "
            "matched budget despite carrying the most information** — an outcome worth "
            "stating clearly if it occurs, since it is a concrete illustration of why "
            "information content alone is the wrong criterion. E5 is also the encoder that "
            "most concerns the dissemination question: if it wins on breadth, the release "
            "retains a great deal of speaker information.", fill=LILAC)


def e6(doc, ctx):
    h1(doc, "9.  E6 — Time-to-first-spike")
    callout(doc, "Status: implemented, complete — nine passing, one skipped.",
            "The extreme temporal case and the sparsest scheme in the set. The exact "
            "inverse of E1: all information in timing, none in event count, which makes the "
            "pair (E1, E6) the cleanest available test of whether timing buys anything at "
            "matched budget. Its gate became relative under D43 — `e_frac` times the "
            "largest frame energy over all channels and frames — after the absolute "
            "`e_min` default was measured sitting 6.8 decades below the quietest frame and "
            "gating nothing at all. The relative form spans 12.36×, comfortably clear of "
            "D27's 4×. The skipped test is test_G7b, which requires a refractory period E6 "
            "does not declare.", fill=GREEN)

    h2(doc, "9.1  Methodology")
    body(doc, "The signal is divided into frames of length T_f with hop H. Within each frame "
              "each channel emits at most one event, at a latency that decreases with channel "
              "energy. Taking the energy in frame m as equation (27), the event time may be "
              "set by a direct logarithmic mapping, equation (28), clipped to the frame — or, "
              "more principled, by the latency of a LIF neuron under constant current "
              "proportional to that energy, equation (29):")
    equation(doc, "E_c[m] = ∫ e_c(t)² dt  over frame m    (27)")
    equation(doc, "t_c[m] = m·H + T_f·( 1 − (log E_c[m] − log E_min)/(log E_max − log E_min) )   (28)")
    equation(doc, "t_c = τ_m · log( I / (I − θ) )   for I > θ    (29)")
    body(doc, "Channels whose energy does not exceed the gate emit nothing, which is the "
              "mechanism by which the scheme is sparsified. Under D43 and D44 the gate is "
              "`e_frac · E_max`, with E_max the largest frame energy over **all** channels "
              "and **all** frames, and E_min in equation (28) is that same quantity — the "
              "two roles the symbol formerly played collapse into one positive number. The "
              "gate is strict, which places every offset strictly inside its frame without "
              "a clipping rule and stops the encoder emitting everywhere on silence. Taking "
              "the maximum per channel instead would destroy the spectral profile, and "
              "test_T6_2 detects that reading: subclassing the encoder to do it moves the "
              "worst Pearson residual from 3.3e−16 to 1.89 against a tolerance of 1e−9. "
              "Frame energy is the sum of squared drive samples in the frame, computed on "
              "whatever drive is supplied with no further transformation, so that a test can "
              "reproduce it independently.")

    h2(doc, "9.2  Design parameters")
    table(doc, ["Parameter", "Default", "Role", "Swept?"], [
        ["e_frac", "0.20", "Energy gate as a fraction of E_max — the declared RATE_PARAM", "Yes — 12.36× span, clears D27"],
        ["frame", "0.025 s", "Frame length T_f", "Secondary axis"],
        ["hop", "0.010 s", "Frame hop H; bounds the budget at N_ch/H events per second", "Secondary rate axis (§5.6)"],
        ["tau_m", "0.02 s", "Membrane time constant for the lif mode, equation (29)", "Secondary axis"],
        ["theta", "1.0", "Threshold for the lif mode, equation (29)", "Secondary axis"],
        ["mode", "log", "log uses equation (28); lif uses equation (29)", "Yes"],
        ["E_max", "derived", "Largest frame energy over all channels and frames; both the gate and equation (28)'s ceiling (D44)", "Not settable — it is a property of the drive"],
    ], widths=[3.4, 2.4, 7.6, 3.6],
        fills={(0, 3): GREEN})

    h2(doc, "9.3  The rate parameter was in the wrong place, and was moved")
    body(doc, "At the originally declared default the event count was pinned at exactly the "
              "ceiling — every channel firing in every frame at every point in the sweep. "
              "The measurement below is kept because it is the case for probing a rate rule "
              "*before* writing the encoder, which is now standard practice in this project.")
    r = load("e6_rate_parameter_span")
    if r:
        rows = [["e_min (superseded)"] + [f"{v:g}" for v in r["param_values"]],
                ["events"] + [str(c) for c in r["counts"]]]
        table(doc, ["", "0.25×", "0.5×", "1×", "2×", "4×"], rows,
              widths=[3.2, 2.4, 2.4, 2.4, 2.4, 2.4],
              fills={(1, i): ROSE for i in range(1, 6)})
        d = r["diagnostics"]
        caption(doc, f"Manifest id e6_rate_parameter_span, now superseded. Span "
                     f"{r['span']:.3f}×, and {r['counts'][0]} is exactly the ceiling "
                     f"N_ch × N_frames. The absolute default sat "
                     f"{d['decades_below_quietest_frame']:.1f} decades below the quietest "
                     f"frame in the signal and gated nothing at all.")
    body(doc, "The diagnosis was that this was a default in the wrong place rather than a "
              "structural defect — test_G3's own docstring had named E6 as the foreseeable "
              "casualty of D27 on the grounds that its count is \"structurally fixed\", and "
              "that turned out to be wrong on both halves (D46). The remedy taken was the "
              "second option Q14 put: make the gate **relative** to the largest frame "
              "energy, which is scale-free and which simultaneously supplies the E_max that "
              "equation (28) needs (D43, D44).")
    r2 = load("e6_e_frac_span")
    if r2:
        rows = [["e_frac"] + [f"{v:g}" for v in r2["param_values"]],
                ["events"] + [str(c) for c in r2["counts"]]]
        table(doc, ["", "0.25×", "0.5×", "1×", "2×", "4×"], rows,
              widths=[3.2, 2.4, 2.4, 2.4, 2.4, 2.4],
              fills={(1, i): GREEN for i in range(1, 6)})
        si = r2["diagnostics"]["scale_invariance"]
        caption(doc, f"Manifest id e6_e_frac_span. Span {r2['span']:.2f}× against D27's "
                     f"required 4×, monotonic, and the gate now sits above the quietest "
                     f"frame rather than below it. The rule is scale-free: multiplying the "
                     f"drive over "
                     f"{si['decades_of_drive_amplitude']:.0f} decades of amplitude — "
                     f"{si['decades_of_frame_energy']:.0f} of frame energy, since energy "
                     f"goes as the square — gives identical event counts at every scale. "
                     f"The encoder's own output was cross-checked event for event against "
                     f"an independent simulation of the same SPEC rule.")

    h2(doc, "9.4  Three further gaps found before writing a line — all now closed")
    body(doc, "Probing the specification ahead of implementation found three problems, none "
              "of which needed the encoder to exist. All three were resolved together by "
              "D44, and the pattern is worth noting: making the gate relative fixed the "
              "first two as a side effect, because it defines E_max and collapses the two "
              "roles the symbol had been playing into one positive quantity.")
    table(doc, ["#", "Finding", "Consequence"], [
        ["1", "Equation (28) has no E_max. Not a constructor argument, not defined in the "
              "specification or the proposal.",
         "Utterance-max, frame-max and a fixed constant all give different event times; a "
         "Layer 3 reimplementation has nothing to choose between them."],
        ["2", "Equation (28) is not evaluable at e_min = 0, which is what two of its own "
              "tests pass, with mode='log' the default.",
         "log 0 = −inf makes the normalised term inf/inf. E_min is doing two jobs — the "
         "emission gate and the normalisation floor — and zero is legal for the first and "
         "not the second."],
        ["3", "test_T6_1 and test_T6_2 are unsatisfiable by **any** implementation at "
              "hop < frame.",
         "Both pass frame = 25 ms, hop = 10 ms, so windows overlap by 15 ms, and both then "
         "treat the window as holding one frame's events when it holds three."],
    ], widths=[1.0, 7.4, 8.0], size=8.5)
    body(doc, "The third was separated into its two causes by measurement rather than "
              "argument, on a prototype that was then discarded:")
    table(doc, ["hop", "Offset clipped to", "test_T6_1 duplicate windows", "test_T6_2 worst |ρ + 1|"],
          [["10 ms (default)", "frame", "98 of 98", "1.2301"],
           ["10 ms", "strictly inside", "98 of 98", "1.2301"],
           ["25 ms (= frame)", "frame", "1 of 40", "0.6000"],
           ["25 ms (= frame)", "strictly inside", "0 of 40", "0.0000"]],
          widths=[3.6, 3.8, 4.6, 4.4],
          fills={(0, 2): ROSE, (0, 3): ROSE, (1, 2): ROSE, (1, 3): ROSE,
                 (2, 2): AMBER, (2, 3): AMBER, (3, 2): GREEN, (3, 3): GREEN})
    caption(doc, "8 channels, 1 s. The overlap is fatal and no implementation choice touches "
                 "it. The single remaining failure at hop = frame is the equation (28) "
                 "boundary — E = E_min maps to an offset of exactly T_f, which lands on "
                 "m·H + T_f and so falls outside its own half-open window and into the next.")

    h2(doc, "9.5  Output characteristics, as specified")
    body(doc, "**Unipolar**, and the sparsest scheme in the set by a wide margin. The event "
              "budget is bounded exactly at N_ch / H events per second, which makes E6 "
              "uniquely predictable in cost — a genuine practical virtue for a released "
              "format, and the reason the hop is a meaningful secondary rate axis in its own "
              "right. All information resides in timing; the code carries nothing in event "
              "count, which is what makes the (E1, E6) pair the cleanest available test of "
              "whether timing buys anything at matched budget.")
    body(doc, "Predicted behaviour (P-04): competitive on T1 at very low event rates, since "
              "a frame-wise spectral snapshot is close to what a conventional filterbank "
              "feature vector provides; poor on T3, since temporal resolution is quantised to "
              "the frame; poor on T2. Its interest lies at the low-rate end of the Pareto "
              "front, where it may dominate everything else.")
    body(doc, "One part of E6 is fully specified and reachable now: mode='lif' uses equation "
              "(29), which involves no E_min or E_max, and test_T6_3 sets hop = frame so no "
              "overlap arises. It reproduces its own closed form — I = 4.0, latency 5.7536 "
              "ms, comfortably inside the 25 ms frame.")


def e7_and_references(doc, ctx):
    h1(doc, "10.  E7 — Spiketrum, and the two reference points")
    callout(doc, "Status: deliberately not implemented (D09).",
            "E7 will not be reimplemented from the published description, to avoid "
            "reimplementing a colleague's algorithm badly. D80 restates O3 with a middle "
            "course: implement the published algorithm and report it as our implementation "
            "of it rather than as the authors' system. Until O3 is settled the encoder is "
            "provisional and is excluded from the critical path.", fill=GREY)

    h2(doc, "10.1  E7 — Spiketrum")
    body(doc, "Spiketrum is a general-purpose spike-coding algorithm with published FPGA "
              "and ASIC implementations and reported application to auditory perception "
              "tasks. It is the work of a collaboration led from Zhejiang University, "
              "published as Tang et al., 'Neuromorphic Auditory Perception by Neural "
              "Spiketrum', IEEE TETCI 9(1), 2025; Wijekoon and Alsakkal are two of the "
              "eight co-authors and are at Manchester. It is a sparse decomposition method "
              "in the matching-pursuit family, which the authors call Event-based Temporal "
              "Matching Pursuit: "
              "the signal is approximated by iteratively selecting, from a time-frequency "
              "dictionary of atoms, the atom best correlated with the current residual, "
              "emitting an event identifying that atom and its time, and subtracting its "
              "contribution:")
    equation(doc, "(c_k, t_k) = argmax | ⟨ r^(k−1), g_{c,t} ⟩ |    (30)")
    equation(doc, "r^(k) = r^(k−1) − ⟨ r^(k−1), g_{c_k,t_k} ⟩ · g_{c_k,t_k}    (31)")
    body(doc, "The event train is the sequence of selected atom indices and times, and the "
              "number of atoms retained per unit time is a directly controllable rate "
              "parameter — which, notably, is the property that cost E5 and E6 a week each "
              "to establish, and which E5 still does not fully have. The reported properties of precisely controllable spike rate, robustness "
              "to spike loss, and signal reconstruction all follow from this structure.")
    body(doc, "Its reconstruction capability makes it the direct test of the study's own "
              "argument rather than merely an extreme point beside it: Spiketrum optimises "
              "reconstruction fidelity deliberately and well, which is the criterion the "
              "study argues is the wrong one for a task-oriented encoder. It should not be "
              "described as an upper reference on a privacy axis, as an earlier version of "
              "this section had it — a representation the audio can be recovered from "
              "carries the same restricted content as the recording, not a milder version "
              "of it (D80).")
    body(doc, "Two corrections of substance, from reading the source in full. The "
              "dictionary is ERB-spaced gammatone, so E7 does not differ from E1–E6 in its "
              "filtering; it differs in fusing filtering with event generation, and in "
              "selecting the globally best-explaining event rather than deciding locally. "
              "And the amplitude of each atom is carried by place: intensity-to-place "
              "coding expands M atoms into M×K channels, the authors' hardware using 40 "
              "kernels and 3 intensity levels for 120 channels. The channel figures quoted "
              "in proposal §5.7 are under query as Q42 and are deliberately not repeated "
              "here.")
    callout(doc, "Corrected 2026-09-09 after reading the primary source (D80).",
            "Report v2 described Spiketrum as **developed at Manchester by Alsakkal and "
            "Wijekoon**, following the proposal. That was wrong: the work is led from "
            "Zhejiang University by Tang and colleagues. The error came from citation "
            "records, which show institutions rather than who led the work, and it matters "
            "because O3 is an approach to the authors. Two of the three primary sources "
            "named in the proposal remain unread, and the TETCI paper cites no work by "
            "either Manchester author, so whether they exist as described is unsettled "
            "(Q41).", fill=ROSE)

    h2(doc, "10.2  R1 — Lauscher / Heidelberg reference point")
    body(doc, "Not a candidate but a fixed reference. The Spiking Heidelberg Digits dataset "
              "was produced using an artificial cochlea model with seven hundred output "
              "channels, comprising a hydrodynamic basilar membrane model, a transmitter-pool "
              "hair cell stage and a bushy cell layer. Including it costs little and buys two "
              "things: interoperability, since a substantial body of existing spiking network "
              "tooling reads data in that channel format, and a familiar coordinate for "
              "readers who know the SHD benchmark. Note that channel count in this study is "
              "explicitly a free swept parameter and is **not** fixed to 700 (D05); whether "
              "700 should nonetheless be a target for the release, for interoperability, is a "
              "separate question.")

    h2(doc, "10.3  R2 — the non-spiking reference")
    body(doc, "The essential control, and arguably the single most important row in the "
              "results table. Forty mel-scale filterbank features computed over 25 ms windows "
              "at 10 ms hop, fed to the same decoder architecture as every spiking condition. "
              "This is the standard front end used by Wu and colleagues and by Bittar and "
              "Garner, so results are directly comparable to the published literature as well "
              "as internally. **It is now implemented and measured on all three tasks** "
              "(§13), and it shares one decoder path with every spiking condition rather "
              "than a matching one, so the fairness constraint that decoding be identical "
              "holds by construction (D51).")
    body(doc, "Two things about it were decisions rather than lookups. Section 5.9 fixes "
              "the band count, window and hop but not where the window sits relative to the "
              "frame instant, and a window centred on that instant sees 12.5 ms of audio "
              "the strictly causal featurisation kernel cannot — so R2 would outscore every "
              "spiking condition partly by seeing the future. The default is therefore a "
              "causal window ending at the frame instant, with the centred convention "
              "available and the choice recorded on every result (D52). The two differ by "
              "10.6 accuracy points on T1, which is why it was worth deciding rather than "
              "defaulting.")
    callout(doc, "R2 bounds T1. It does not bound T2 or T3.",
            "Measured, each condition at its own best configuration: on T1, R2 reaches "
            "0.9133 against E1's 0.8996 — a gap of 1.4 points at the highest budget. On T2 "
            "and T3 the gap is **negative**: E1 reaches a within-utterance correlation of "
            "0.5755 against R2's 0.4991, and an F-score of 0.7576 against 0.6852. The "
            "mechanism is the one the study was built to find — 25 ms windows smear a "
            "transition that an event stream resolves at event precision, and §4.3 names "
            "transient timing as exactly what T3 rewards — but it makes *upper bound* the "
            "wrong name, and §5.9's instruction to report every accuracy as a gap to R2 "
            "produces a negative gap that reads as an error. Whether E1 beats R2 or beats "
            "*this* R2, whose window length was chosen for phone classification, is open as "
            "Q31.", fill=ROSE)
    callout(doc, "Every accuracy should be reported as a gap to this bound.",
            "Without it a phone accuracy figure means nothing: the reader cannot tell "
            "whether a shortfall reflects the encoding, the decoder, the corpus or the task "
            "definition. With it, the central engineering question of the project has a "
            "direct numerical answer — **what accuracy is given up, at what saving in "
            "operations, by representing the audio as events.** The headline figure of the "
            "paper is a panel of Pareto plots, one per task, with R2 drawn as a horizontal "
            "line on each.", fill=LILAC)


def shared_machinery(doc, ctx):
    h1(doc, "11.  Shared machinery: featurisation, corruption, metrics")
    body(doc, "Three pieces of the harness sit between the encoders and the probe tasks. "
              "They are shared deliberately: the proposal is explicit that the conversion "
              "from events to decoder input must be identical across encoders or it silently "
              "becomes part of what is being compared.")

    h2(doc, "11.1  Featurisation — the encoder/probe interface")
    body(doc, "Events are converted to a fixed-rate feature vector by an exponential kernel "
              "sampled at a fixed frame rate:")
    equation(doc, "φ_c(t) = Σ_k κ(t − t_k),   κ(u) = exp(−u / τ_φ) for u ≥ 0, else 0    (32)")
    body(doc, "ON and OFF are accumulated separately rather than summed, because cancelling "
              "them would discard the distinction a bipolar encoder went to the trouble of "
              "making. Encoders declaring a single polarity leave the OFF half at zero, which "
              "is correct rather than wasteful: the probe sees the same feature width for "
              "every encoder at a given channel count. The implementation accumulates "
              "recursively, which is O(N + F) rather than O(N × F), and sorts events into a "
              "canonical order before accumulating anything — so the result is bit-identical "
              "under any permutation of the input, which is stronger than the tolerance the "
              "order-invariance test allows.")
    r = load("featurise_accuracy")
    if r:
        rows = []
        for enc, v in sorted(r["by_encoder"].items()):
            rows.append([enc, str(v["n_events"]),
                         f"{v['worst_relative_error_scaled_to_array_max']:.2e}",
                         f"{v['worst_relative_error_pointwise']:.2e}",
                         "yes" if v["bit_identical_under_permutation"] else "no",
                         f"{v['polarity_folding_max_abs_error']:.1e}"])
        table(doc, ["Encoder", "Events", "Rel. error vs eq (32), scaled",
                    "Rel. error, pointwise", "Bit-exact under permutation",
                    "Polarity folding error"], rows,
              widths=[2.0, 1.8, 3.9, 3.2, 3.4, 3.1])
        caption(doc, "Manifest id featurise_accuracy. Checked against a literal double-sum "
                     "transcription of equation (32) rather than against its own test. Two "
                     "relative measures are recorded because they answer different "
                     "questions: the scaled measure divides by the largest value in the "
                     "array and is the error a probe would see; the pointwise measure "
                     "divides by each entry's own value and is dominated by entries decayed "
                     "to near nothing.")
        callout(doc, "A correction to the record.",
                "The notebook quotes 9.4e−16 as the worst relative error. That figure "
                "identifies its own normalisation — it is the scaled measure, and E4 gives "
                "9.39e−16 — but it was **not the worst of the three**: E3 gives 1.31e−15 "
                "under the same measure, about 40 per cent larger. The conclusion is "
                "unaffected, since agreement is a few units in the last place of the largest "
                "feature value either way, but the figure as quoted understates the worst "
                "case (Q15).")

    h2(doc, "11.2  Corruption operators")
    body(doc, "Four operators degrade an event train in controlled ways, used by preliminary "
              "experiment P2 and by E5's jitter test. Three are complete and verified: "
              "**jitter**, which perturbs timestamps while preserving count and ordering; "
              "**delete**, which drops events at a given rate; **randomise_times**, which "
              "preserves per-channel counts but destroys timing; and **channel_shift**, which "
              "drops rather than wraps at the edges of the bank. The deliberate design is "
              "that different tasks should degrade under different operators — prediction "
              "P-07 — so that the battery demonstrably spans the demand space.")
    body(doc, "One test currently fails on its own precondition rather than on the operator: "
              "test_corrupt_delete_retains_expected_fraction guards that the train has more "
              "than 500 events, and the fixture yields 275. The operator itself is correct — "
              "retention is 0.7382, inside the required window — and the 275 is exact rather "
              "than a lost-event bug, identical at 2×, 4×, 8× and 16× oversampling. The guard "
              "is doing real statistical work and should not simply be deleted: at 275 events "
              "the assertion window is ±1.81 binomial standard deviations and holds for 93.1 "
              "per cent of seeds, against ±2.44 and 97.7 per cent at 500 (Q13).")

    h2(doc, "11.3  Reported metrics")
    table(doc, ["Metric", "Definition", "Purpose"], [
        ["Event rate R", "N_events / (N_ch · D)", "Per-channel rate, equation (34)"],
        ["Total rate Λ", "N_events / D", "The Pareto x-axis, equation (35)"],
        ["Bit rate B", "Λ · (log₂ N_ch + b_t + b_p)", "Channel cost, equation (36)"],
        ["Operations", "N_events · N_hidden accumulates", "Compute cost, equation (37)"],
        ["Information", "I(Y ; Ŷ), bits per event and per second", "Equations (38)–(39)"],
        ["Vector strength", "(1/N)·|Σ exp(j2πf_c t_k)|", "E5 diagnostic, equation (26)"],
        ["Temporal information index", "(A_temporal − A_count) / (A_ceiling − A_count)", "Equation (40); ceiling from R2"],
    ], widths=[3.6, 6.6, 6.2])
    caption(doc, "SpiNNaker energy measurement is out of scope for this study; spike-count "
                 "and information-per-spike metrics are in scope now (D08).")


def harness_section(doc, ctx):
    h1(doc, "12.  The probe harness")
    body(doc, "Between the encoders and any number worth reporting sits the machinery that "
              "turns a body of audio into a scored operating point: a corpus, a "
              "speaker-disjoint split, per-frame targets, a probe, and the Layer 2 controls "
              "that say whether the result means anything. None of it existed a week ago; "
              "all of it does now, and every task result in §13 comes through it.")

    h2(doc, "12.1  The corpus problem, and the stand-in")
    callout(doc, "There is still no corpus. The TIMIT licence question O2 is nineteen days "
            "old.",
            "Stage one of the study runs on TIMIT, which is LDC-licensed; the MANCHESTER "
            "Dataset is unrecorded. The harness is therefore written against a corpus "
            "*interface*, with a synthetic stand-in behind it, and when a licence arrives "
            "only the loader changes. **Every number in §13 is on that stand-in and none of "
            "them is a statement about speech.**", fill=ROSE)
    body(doc, "The stand-in is not a placeholder to be thrown away. It is a source-filter "
              "corpus: per-speaker vocal tract scaling and fundamental frequency, phones "
              "synthesised as formant resonances or noise bands, exact segment boundaries "
              "and an exact f_0 contour. The point of generating rather than annotating the "
              "ground truth is that it is the only thing that can distinguish *the encoder "
              "lost the information* from *the harness mislabelled every frame*. On a real "
              "corpus every accuracy is plausible and neither reading can be excluded; on "
              "this one the answer is known by construction, which is what makes the "
              "controls below able to fail.")
    body(doc, "Its limitations are known and are stated wherever they bear on a result. "
              "Phones are stationary resonances with no formant transitions, so a "
              "segment-level count vector nearly determines phone identity. Phone durations "
              "are drawn uniformly on 60–140 ms, so boundaries are quasi-regular and "
              "evenly-spaced guesses score well. The f_0 contour is a linear declination "
              "moving one to three semitones, where real speech carries accents and question "
              "intonation. Each of these makes a task *easier* or its trivial baseline "
              "*stronger* than on speech, and each is the reason a corresponding result "
              "below is reported as machinery working rather than as a finding.")

    h2(doc, "12.2  Probes")
    body(doc, "The linear probe is multinomial logistic regression fitted by L-BFGS-B, and "
              "the T2 decoder is closed-form ridge regression. Both are written out rather "
              "than imported, which was forced rather than preferred: continuous integration "
              "installs numpy, scipy and pytest and runs every test file, and the workflow is "
              "a design-session file this session may not edit — so a probe requiring "
              "scikit-learn would make its own tests unrunnable in the one environment that "
              "checks them independently. The logistic probe was validated against "
              "scikit-learn out of tree instead, agreeing to 8.2e−06 in coefficients and "
              "exactly in predictions (D49).")
    body(doc, "The nonlinear probe of §6.2 — a two-layer bidirectional GRU — does not exist. "
              "It needs a tensor library this machine does not have, on eight CPU cores with "
              "no GPU, and committing to an architecture before measuring what one training "
              "run costs would be guesswork. **The accessibility gap of equation (33), which "
              "the proposal argues is among the most useful numbers the study can produce, "
              "is therefore unmeasured.**")

    h2(doc, "12.3  The Layer 2 controls, and why they run unconditionally")
    body(doc, "Validation protocol §4 lists the pipeline controls as things to do. A control "
              "that must be remembered is one that will one day be forgotten, and the run it "
              "is forgotten on is by construction the one nobody was watching — so they are "
              "computed on every call and returned beside the headline number, with no "
              "argument to switch them off (D48). Split disjointness goes further: it is "
              "enforced in the constructor, so a leaking split cannot be built.")
    rows = [
        ["C1", "Upper-bound anchor against published TIMIT accuracy",
         "Not evaluable — needs TIMIT (O2)"],
        ["C2", "Chance and majority floors, reported per task",
         "Every run. T3 uses a uniform-baseline floor instead, since a majority rate is "
         "meaningless for a detection task"],
        ["C3", "Shuffled-label control — the primary leakage detector",
         "Every run. Returns to chance everywhere: 0.104–0.141 on T1 against 0.125 chance"],
        ["C4", "Identical decoding across conditions",
         "By construction — R2 and every encoder share one scoring function (D51)"],
        ["C5", "Deliberate ±1-frame misalignment",
         "Every run, and it found a real misalignment rather than confirming none (§13.2)"],
        ["C6", "Budget cross-check, two independent counts",
         "In-memory form only; the file-format form needs the release format (Q07)"],
        ["C7", "Round-trip integrity of the release format",
         "Not possible — the format is blocked on Q07"],
        ["C8", "Three seeds minimum, spread reported",
         "Every reported figure"],
    ]
    fills = {}
    for i, r in enumerate(rows):
        fills[(i, 2)] = ROSE if r[2].startswith("Not") else GREEN
    table(doc, ["", "Control", "Status"], rows, widths=[1.1, 7.4, 8.0],
          fills=fills, size=9)
    caption(doc, "Three of the eight cannot be evaluated yet, and all three are blocked on "
                 "something outside the harness: two on the release event format, one on "
                 "the corpus licence. That is worth stating plainly, because C1 is the "
                 "control that would tell us the pipeline is calibrated rather than merely "
                 "self-consistent, and until TIMIT arrives no result here carries that "
                 "assurance.")


def task_results_section(doc, ctx):
    h1(doc, "13.  First task results")
    callout(doc, "Read these as evidence the machinery works, not as findings about "
            "encodings.",
            "Every figure below is on the synthetic stand-in described in §12.1, whose "
            "known limitations make each task easier or its baseline stronger than on "
            "speech. Control C1 — the anchor that would say whether the pipeline is "
            "calibrated at all — cannot be evaluated without TIMIT. What these results do "
            "establish is that the path from audio to a scored Pareto point runs end to "
            "end, that its controls bite, and that several specification questions which "
            "would have been invisible on paper are now measured.", fill=AMBER)
    body(doc, "**Every number in this section replaces one in version 2.** The free "
              "parameters — the label alignment offset, the ridge penalty, and for P1 the "
              "featurisation time constant — were previously chosen by maximising the "
              "score on the test split. §13 of the validation protocol requires them to be "
              "chosen on data held out inside the *training* split, and D71 now enforces "
              "it through one shared mechanism. Each condition is scored at the value that "
              "mechanism selected, and §13.4 reports what the old procedure was worth.")

    h2(doc, "13.1  T1 — phone classification, across two decades of budget")
    rows = []
    for pt in ctx["t1"]["points"]:
        sel = sorted(set(pt["offset_by_seed"]))
        m = lambda o: str(o).replace("-", "\u2212")   # noqa: E731 — typographic minus
        sel_s = m(sel[0]) if len(sel) == 1 else "/".join(m(o) for o in sel)
        bw = sum(r["bandwidth_bps"] for r in pt["runs"]) / len(pt["runs"])
        rows.append([f"{pt['achieved_lambda']:.0f}", f"{pt['rate_param']:.5g}",
                     f"{pt['accuracy_mean']:.4f}", f"± {pt['accuracy_std']:.4f}",
                     f"{sel_s}  ({m(pt['predicted_offset'])})", f"{bw:,.0f}"])
    table(doc, ["Λ (events/s)", "theta", "Accuracy", "spread",
                "offset selected (predicted)", "Bandwidth (bit/s)"], rows,
          widths=[2.6, 2.2, 2.4, 1.9, 3.4, 2.9])
    caption(doc, f"E1, 32 channels, three split seeds. Majority floor "
                 f"{ctx['t1']['floor']:.4f}, chance {ctx['t1']['chance']:.4f}. Accuracy is "
                 f"at the offset selected inside the training split; the offset was "
                 f"unanimous across the three seeds at every budget. The predicted offset "
                 f"in brackets is computed from the declared front-end lag and the "
                 f"featurisation kernel, with no probe fitted — see §13.2.")
    body(doc, "The bandwidth column is worth dwelling on, because it is the first "
              "quantitative version of the study's central engineering question and it does "
              "not favour the answer the field assumes. R2's dense features cost 128,000 "
              "bit/s. E1 reaches 98.5 per cent of R2's accuracy at Λ = 15,343, where its "
              "event stream costs 398,929 bit/s — **three times more than the "
              "representation it is approximating**. The two costs cross near Λ = 4,900, "
              "where E1 sits at about 91 per cent of the bound. Both figures depend on "
              "declared widths — 20 bits of timestamp, 32 bits per mel coefficient, both "
              "generous — so this is a statement about those widths and not about events in "
              "general. It is reported here rather than smoothed because §6.3 requires the "
              "encoder's own cost to be charged rather than hidden, and because a result "
              "that runs against the expected direction is the one most worth checking "
              "early. The conclusion is unchanged from v2; only the accuracies moved.")

    h2(doc, "13.2  The alignment axis, and a prediction that holds")
    body(doc, "v2 reported that control C5 failed: offsetting the labels by one frame "
              "*raised* accuracy at every budget point rather than lowering it. That was "
              "correct and it was diagnostic. D69 made the offset a swept axis on the same "
              "footing as the featurisation time constant, D70 restated C5 as an "
              "interior-maximum test over at least two frames either side of the selected "
              "offset, and D71 requires the selection to happen inside the training split. "
              "All three are now implemented and the axis behaves.")
    body(doc, "The offset that gets selected is the offset the declared lags predict, and "
              "that prediction is computed without fitting anything: the front end declares "
              "its own group delay under D24, and the equation (32) kernel's first moment "
              "is tau_phi exactly. **R2 is the clean test**, because its lag is a different "
              "quantity altogether — half a 25 ms analysis window rather than a filterbank's "
              "phase response.")
    rows = [
        ["R2, causal window", "−1", "−1", "0.0000", "pass"],
        ["R2, centred window", "0", "0", "0.0000", "pass"],
        ["E1 on T1, five of six budgets", "−1", "−1", "0.0000", "pass"],
        ["E1 on T1, Λ = 160", "−1", "−2", "0.0000", "pass"],
    ]
    table(doc, ["Condition", "Predicted offset", "Selected", "Selection bias",
                "C5 interior max"], rows,
          widths=[6.0, 2.8, 2.2, 2.4, 3.0],
          fills={(i, 4): GREEN for i in range(4)})
    caption(doc, "Three split seeds, unanimous in every row. The sparsest budget selects "
                 "one frame later than predicted, on all three seeds: at 160 events per "
                 "second the features integrate over longer, which is a real effect rather "
                 "than noise precisely because it is unanimous.")
    callout(doc, "v2's most uncomfortable finding is resolved.",
            "v2 reported that at offset zero the non-spiking upper bound sat *below* the "
            "encoder it was supposed to bound — R2 causal 0.8247 against E1 0.8316 — and "
            "raised it as Q24. With the alignment swept and selected honestly, R2 causal "
            "scores 0.9133 against E1's 0.8996 and the ordering is restored with a gap of "
            "1.4 points. Nothing about either encoding changed; only which frame the labels "
            "were paired with. Q24 is answered by D69 and D70, and T1's v2 figures stand as "
            "**lower bounds** rather than errors (D72) — they were correct measurements at "
            "an alignment that was not then a declared axis.", fill=GREEN)

    h2(doc, "13.3  T2, T3, and the preliminary experiments")
    def pick(conditions, cond, ctxw):
        return max((c for c in conditions
                    if c["condition"] == cond and c["context"] == ctxw),
                   key=lambda c: c["lambda_events_per_s"])

    t2e = pick(ctx["t2"]["conditions"], "E1", 5)
    t2r = pick(ctx["t2"]["conditions"], "R2", 5)
    t3e = pick(ctx["t3"]["conditions"], "E1", 5)
    t3r = pick(ctx["t3"]["conditions"], "R2", 5)
    tii = [pt["tii_at_best"] for pt in ctx["p1"]["points"]]
    defined = ", ".join(f"{v:+.3f}" for v in tii if v is not None)
    p2c = {c["operator"]: c for c in ctx["p2"]["conditions"]}
    lost = lambda op: ", ".join(  # noqa: E731
        f"{t} {p2c[op][t]['headroom_lost']:.2f}" for t in ("T1", "T2", "T3"))
    rows = [
        ["T2 — f_0 contour",
         f"E1 at Λ={t2e['lambda_events_per_s']:,.0f}, 5 frames of context",
         f"r/utt {t2e['pearson_per_utterance']:+.4f}, RMSE "
         f"{t2e['rmse_semitones']:.3f} st, voicing {t2e['voicing_accuracy']:.4f}"],
        ["", "R2", f"r/utt {t2r['pearson_per_utterance']:+.4f}, RMSE "
                   f"{t2r['rmse_semitones']:.3f} st, voicing "
                   f"{t2r['voicing_accuracy']:.4f}"],
        ["T3 — boundaries",
         f"E1 at Λ={t3e['lambda_events_per_s']:,.0f}, 5 frames of context",
         f"F {t3e['f_score']:.4f}, R-value {t3e['r_value']:+.3f}, frame AUC "
         f"{t3e['frame_auc']:.4f}"],
        ["", "R2", f"F {t3r['f_score']:.4f}, R-value {t3r['r_value']:+.3f}, "
                   f"frame AUC {t3r['frame_auc']:.4f}"],
        ["", "uniform baseline at the reference rate",
         f"F {t3e['uniform_baseline_f']:.4f}"],
        ["P1 — count-only", "temporal information index, equation (40)",
         f"{defined}; undefined at "
         f"{sum(1 for v in tii if v is None)} of {len(tii)} budgets"],
        ["P2 — corruption", "worst headroom lost, whole-utterance randomisation",
         lost("randomise_times")],
        ["", "the same operator applied within each segment",
         lost("randomise_times_in_segments")],
    ]
    table(doc, ["Task", "Condition", "Result"], rows,
          widths=[3.4, 6.2, 6.8], size=9)
    caption(doc, "All on the stand-in, three split seeds, every free parameter selected "
                 "inside the training split. T2's headline is the mean within-utterance "
                 "Pearson correlation, not the pooled figure: speakers differ in mean f_0 "
                 "far more than a contour moves within one utterance, so a pooled "
                 "correlation is winnable by a predictor that emits one constant per "
                 "utterance and estimates voice height. Here the pooled figure is +0.9074 "
                 "against +0.5525 per utterance, so most of it is voice height.")
    callout(doc, "E1 now beats R2 on both T2 and T3, and the gap widened under the "
                 "correction.",
            "On T3 at five frames of context E1 scores F 0.7557 against R2's 0.5930. In v2 "
            "the same comparison was 0.7576 against 0.6852. E1 lost 0.002 and R2 lost "
            "0.092 — because E1's offset was already pinned at 0 on every seed while R2's "
            "wandered over −1, 0 and +1, so R2 had test-set noise to harvest and E1 did "
            "not. **A bias that differs between conditions moves comparisons, not just "
            "levels.** Q31 asks how R2 can fail to bound T3 and now has a second instance, "
            "under a procedure in which neither condition saw the test set.", fill=ROSE)
    body(doc, "**P1 cannot be answered on this corpus and now says so more sharply.** Its "
              "denominator is the gap between the mel ceiling and a count-only probe, and "
              "on a corpus of stationary phones a segment's count vector nearly determines "
              "its identity: counts reach 0.9583 against a ceiling of 0.9676, a denominator "
              "of 0.009. The index is undefined at three of six budgets and negative at two "
              "of the three where it is defined. That is the condition §7.1 describes as *a "
              "spectral profile task wearing a spiking costume*, correctly detected — and "
              "what it diagnoses is the corpus, not T1. **This contradicts prediction P-06** "
              "on its T1 clause, which expects a moderate index; the contradiction is "
              "attributable to the corpus rather than to E1, P-06 is not marked resolved, "
              "and the argument is written up in the notebook rather than settled here.")
    callout(doc, "P2's one corpus-independent finding, unchanged.",
            "The specifications define the fourth corruption operator differently: the "
            "proposal randomises event times *within each segment*, SPEC over the whole "
            "utterance. Both were run. Under SPEC's version T1 falls to 0.1591 — **below "
            "its own majority floor** — and under the proposal's to 0.7497, a fifth of its "
            "headroom. The same named operator either annihilates T1 or barely touches it, "
            "because randomising across the utterance moves events between segments and so "
            "destroys the per-segment rate the proposal's wording explicitly says the "
            "operator leaves intact. Unlike everything else in this section **this "
            "transfers to TIMIT unchanged**, and it decides what P1's equation (40) is "
            "measuring as well. Open as Q35.", fill=ROSE)
    body(doc, "P2 is recorded as a rehearsal and not as the week-4 decision gate (D60). The "
              "gate asks whether the three tasks degrade under different corruptions, and "
              "the profiles here do differ — T1 is almost untouched by channel shift where "
              "T3 loses up to 1.5 of its headroom, T3 is hypersensitive to jitter where T1 "
              "is not, and T1 is destroyed by whole-utterance randomisation and not by the "
              "per-segment form. The direction is consistent with prediction P-07. It is "
              "not evidence for it, because a corpus whose tasks are easier and more alike "
              "than speech cannot carry the test, and P-07 stays open. One asymmetry is "
              "worth a look later: channel_shift = −2 costs T2 0.56 of its headroom while "
              "+2 costs it nothing, which is the shape Q37 predicts if the operator is "
              "translation plus truncation and the truncation dominates.")

    h2(doc, "13.4  What selecting on the test set was worth")
    body(doc, "The correction makes a quantity measurable that would otherwise have to be "
              "asserted: how much a free parameter chosen against the reported number "
              "inflates it. Each condition was scored both ways — at the value selected "
              "inside the training split, and at the value that maximises the test score, "
              "which is what v2 did. The difference is the bias.")
    def bias(vals):
        v = [abs(x) for x in vals if x is not None]
        return (f"{sum(v) / len(v):.4f}", f"{max(v):.4f}") if v else ("—", "—")

    t3c = ctx["t3"]["conditions"]
    rows = [
        ["T1, all six budgets", *bias([b for pt in ctx["t1"]["points"]
                                       for b in pt["selection_bias_by_seed"]]),
         "accuracy"],
        ["R2 on T1, both alignments",
         *bias([b for c in ctx["r2"]["conditions"]
                for b in c["selection_bias_by_seed"]]), "accuracy"],
        ["T3, context 2 and 5",
         *bias([b for c in t3c if c["context"] > 0
                for b in c["selection_bias_by_seed"]]), "F-score"],
        ["T3, context 0",
         *bias([b for c in t3c if c["context"] == 0
                for b in c["selection_bias_by_seed"]]), "F-score"],
        ["T2, all conditions",
         *bias([b for c in ctx["t2"]["conditions"]
                for b in c["selection_bias_by_seed"]]), "r per utterance"],
        ["P1, temporal condition",
         *bias([b for pt in ctx["p1"]["points"]
                for b in pt["selection_bias_by_seed"]]), "segment accuracy"],
    ]
    table(doc, ["Condition", "Mean bias", "Worst single seed", "Metric"], rows,
          widths=[6.2, 2.8, 3.2, 4.2])
    caption(doc, "Bias is the score at the test argmax minus the score at the selected "
                 "value, averaged over three seeds. Both profiles are recorded in every "
                 "result file, so this is read off the data rather than estimated.")
    body(doc, "Two things in that table matter more than its size. **T1 and R2 are exactly "
              "zero** — validation and test agreed on the offset at every point and every "
              "seed, so the T1 sweep that carries most of this report was never flattered. "
              "**T3 at context 0 is the worst case and it is informative rather than "
              "embarrassing**: a per-frame probe with no context has no representation of a "
              "boundary at all, so its posterior is noise, the alignment axis is genuinely "
              "undefined, and a procedure that picks the argmax of noise picks up 0.128. "
              "That is Q30's argument with a measurement attached.")
    callout(doc, "And for P1 the sign changes.",
            "Equation (40) at Λ = 397 reads +0.352 selected on test and **−0.056** selected "
            "honestly; at Λ = 997, +0.143 against **−0.250**. The old procedure said timing "
            "buys a third of the available headroom; the corrected one says it buys nothing "
            "and is slightly worse than counting. The swing is violent because the "
            "denominator collapses from 0.18 to 0.009 as the budget rises, so a small "
            "numerator bias becomes a large index — which is why the denominator is "
            "reported beside the index and why P1 needs a corpus it can actually "
            "discriminate on.", fill=ROSE)


def results_section(doc, ctx):
    h1(doc, "14.  Recorded results")
    body(doc, "Every figure quoted in this report that carries a manifest identifier is "
              "reproducible from the repository: the manifest names the script, the "
              "committed configuration, the commit hash the tree was at, and the seed. The "
              "recorder refuses to run unless the script and its config are themselves "
              "committed and unmodified, so a recorded commit hash always contains the code "
              "that produced the number (D35).")
    rows = []
    for e in ctx["manifest"]:
        out = e["output"]
        rows.append([e["id"], Path(e["script"]).name, e["commit"][:8],
                     str(e["seed"]), e["date"],
                     f"{len(out)} files" if isinstance(out, list) else "1 file"])
    table(doc, ["Result id", "Script", "Commit", "Seed", "Date", "Output"], rows,
          widths=[5.0, 5.4, 2.0, 1.4, 2.2, 1.8], size=8.5)
    caption(doc, "Small results are JSON under results/ and committed; bulk arrays go to "
                 ".npz, which is gitignored, so numbers that reach the paper stay in the "
                 "repository while large arrays stay local.")

    body(doc, "Two cautions about what these results are and are not. First, **six of them "
              "are now task results** — the T1 budget sweep, R2, P1, T2, T3 and the P2 "
              "rehearsal — but every one is on the synthetic stand-in of §12.1, and the "
              "TIMIT licence question O2 is still open. No number here is a statement about "
              "speech. Second, three seeds are the minimum for anything reported; the "
              "encoder characterisations are on deterministic stimuli through deterministic "
              "paths, where there is nothing for a seed to vary, and each of those configs "
              "says so explicitly rather than leaving a reader to wonder why one seed was "
              "enough. The task results vary the split seed, and what that varies — which "
              "speakers land in test — is named on the result rather than left implied.")
    body(doc, f"{ctx['n_superseded']} manifest entries are marked superseded. That is "
              f"deliberate and is worth explaining, because a superseded entry is more "
              f"informative than a deleted one. Two episodes account for most of them. "
              f"When the probes were changed to drop zero-variance features, four recorded "
              f"results named commits whose tree no longer produced them, so all four were "
              f"re-run — the largest movement was 0.0005 at one budget point, a fifth of "
              f"one test frame. Then D71 superseded all five task results at once, and "
              f"there the movement was not small: see §13.4. In both cases the old entries "
              f"stay visible with their values intact, because a commit hash records "
              f"provenance only if the tree that produced the number is the tree the hash "
              f"names, and a reader who cannot see that a number changed cannot see that "
              f"it was corrected.")

    h2(doc, "14.1  Known-answer suite by block")
    rows = [
        ["F", "Front end — filterbank, envelope, group delay", "6", "0", "Complete"],
        ["T1", "E1 LIF", "3", "0", "Complete"],
        ["T2", "E2 send-on-delta", "9", "0", "Complete"],
        ["T3", "E3 temporal contrast", "6", "0", "Complete"],
        ["T4", "E4 adaptive LIF", "4", "0", "Complete — test_T4_3 replaced under D39"],
        ["T5", "E5 phase-locked", "4", "1", "Q20"],
        ["T6", "E6 time-to-first-spike", "3", "0", "Complete"],
        ["G", "Generic, parametrised over all six encoders", "43", "1", "Q19 — test_G3[E5]"],
        ["corrupt", "Corruption operators", "4", "0", "Complete"],
    ]
    fills = {}
    for i, r in enumerate(rows):
        fills[(i, 3)] = GREEN if r[3] == "0" else ROSE
    table(doc, ["Block", "Covers", "Passed", "Failed", "Blocked on"], rows,
          widths=[1.8, 6.4, 1.6, 1.6, 5.0], fills=fills)
    caption(doc, f"Totals: {ctx['passed']} passed, {ctx['failed']} failed, "
                 f"{ctx['skipped']} skipped, of {SUITE['collected']} collected. Both "
                 f"failures are open specification questions raised before the encoder "
                 f"concerned was written; neither indicates a defect in implemented code. "
                 f"A further {ctx['n_impl_tests']} implementation-session tests cover the "
                 f"harness, the reference, the segment machinery, T2, T3 and P2 — those are "
                 f"this session's own and are not Layer 1.")
    callout(doc, "Continuous integration has not run the harness tests, and that is a gap.",
            "The workflow runs the known-answer suite and then everything else. Because the "
            "first step exits non-zero on the two open questions above, GitHub Actions skips "
            "the second, so no implementation-session test has ever run in the clean "
            "environment that is CI's whole purpose. They were verified by hand instead, in "
            "a fresh interpreter with only the declared dependencies installed, but that is "
            "a check run by the same session that wrote the code. Open as Q25; answering "
            "Q19 and Q20 would clear it as a side effect.", fill=ROSE)


def questions_section(doc, ctx):
    h1(doc, "15.  Open questions, and what each unblocks")
    body(doc, f"{ctx['n_open']} questions are open against the design session, up from "
              f"nine when version 1 of this report was written. That growth is the "
              f"signature of the work having moved from encoders to the harness: an encoder "
              f"arrives with a binding specification section and a block of known-answer "
              f"tests written from its equations, so it either passes or it does not. The "
              f"harness has neither — SPEC declares the pipeline deliberately unspecified — "
              f"so it generates questions rather than consuming answers, and that is normal "
              f"rather than a sign of being stuck.")
    body(doc, "**Six of them are one question wearing different hats.** Q22, Q24, Q27, Q30, "
              "Q34 and half of Q31 all ask the same thing: which free parameters is each "
              "condition allowed to optimise, and must they be the same across conditions? "
              "Section 6.1 already answers it for the featurisation time constant — every "
              "encoder at its own best value. Whether that sentence generalises to context "
              "width, label alignment offset and probe regularisation would settle all six "
              "at once, and it is the highest-leverage answer available, because it "
              "determines the shape of every run from here and of the week-8 screening grid.")
    body(doc, "After that, in the order that clears the most work: **Q23**, because the "
              "logarithmic branch of equation (10) leaves E1, E4 and E6 with no usable "
              "operating range at all — the drive is negative everywhere, so E1 emits "
              "nothing above threshold and saturates below it — and compression is a "
              "declared sweep axis that half the encoder set cannot traverse. **Q35**, the "
              "corruption operator whose two readings differ by a factor of ten and which "
              "is the one open finding that does not depend on the corpus. **Q28**, whether "
              "the stand-in should gain formant transitions or whether P1 and P2 simply wait "
              "for TIMIT, which decides what work is worth doing next. **Q31**, R2's role "
              "now that it bounds one task of three. Then **Q19 and Q20**, which are cheap, "
              "and which are why continuous integration is red and therefore blind.")
    rows = [
        ["Q22 + Q24 + Q27\n+ Q30 + Q34", "#13, #15, #18\n#21, #25", "All tasks",
         "Which free parameters may each condition optimise — context width, label "
         "alignment, probe regularisation — and must they match across conditions? §6.1 "
         "already says yes for tau_phi",
         "The shape of every run, and the week-8 grid"],
        ["Q23", "#14", "E1, E4, E6",
         "The log branch of equation (10) gives a drive that is negative everywhere, so "
         "these three have no usable operating range: E1 emits nothing at theta ≥ 0 and "
         "saturates at the ceiling below it",
         "The compression sweep axis, before week 8 commits compute"],
        ["Q35", "#26", "P1, P2",
         "SPEC and the proposal define the fourth corruption operator differently; T1 "
         "falls to 0.1533 under one and 0.7656 under the other",
         "P2's interpretation, and what equation (40) measures"],
        ["Q28", "#19", "P1, P2",
         "The stand-in has stationary phones, so counts nearly reach the ceiling and the "
         "index is noise. Formant transitions, or wait for TIMIT?",
         "Whether P1 and P2 work on the stand-in is worth doing"],
        ["Q31", "#22", "R2",
         "R2 bounds T1 but not T2 or T3 — E1 beats it on both. Is it a bound, or a "
         "per-task reference?",
         "How every result is framed"],
        ["Q19 + Q20", "#10, #11", "E5",
         "cycle_divisor spans 3.48× against D27's 4×; test_T5_3 cannot pass at the default "
         "D40 introduces",
         "Two tests — and CI, which is blind while they fail (Q25)"],
        ["Q07", "#—", "Release format",
         "ON and OFF as separate channel indices, or a polarity bit? A release-format "
         "question for Oliver rather than a methods one",
         "Controls C6 and C7, and the event file format"],
    ]
    # The first row is the six-in-one cluster; shading it marks where to start.
    fills = {(0, 4): AMBER}
    table(doc, ["Question", "Issue", "Area", "Substance", "What answering it unblocks"], rows,
          widths=[2.2, 1.4, 1.6, 7.4, 4.6], size=8.5, fills=fills)
    callout(doc, "If only one answer comes back, make it the first row.",
            "Six of the open questions are one question, and §6.1 already contains its "
            "answer for one parameter. Everything built from here — the week-8 screening "
            "grid, every Pareto front, the single release configuration of C10 — depends on "
            "whether each condition is scored at its own best settings or at fixed ones, and "
            "§13.2 shows the difference is large enough to reverse the ordering between an "
            "encoder and the reference that is supposed to bound it. Answering it late means "
            "re-running everything built in the meantime; answering it now costs one "
            "sentence.", fill=ROSE)


def predictions_section(doc, ctx):
    h1(doc, "16.  Pre-registered predictions")
    body(doc, "These were recorded and dated before any corresponding run, per §7 of the "
              "validation protocol, and are held fixed thereafter. A result contradicting one "
              "triggers a written investigation before it is used, whatever the outcome. The "
              "purpose is not to protect the predictions — several will very likely be wrong, "
              "and that is fine and interesting — but to ensure that a surprising result "
              "prompts scrutiny rather than a quiet adjustment of the analysis until it stops "
              "being surprising.")
    table(doc, ["#", "Prediction", "Bears on", "Status"], ctx["predictions"],
          widths=[1.4, 9.4, 3.2, 2.4], size=9)
    callout(doc, "Why this matters more than usual here.",
            "The proposal makes specific directional predictions. If the same process both "
            "runs the sweeps and writes the analysis, a large number of small choices about "
            "parameter ranges, seeds, plot limits and which runs to repeat will tend to "
            "favour those predictions. No dishonesty is required for this; it is the ordinary "
            "mechanism by which analysis drifts toward its hypothesis, and an assistant that "
            "has read the proposal is if anything more susceptible than a person, not less. "
            "Parameter grids, seed counts and sweep ranges are therefore fixed in committed "
            "configuration before the sweep runs, and extending a range after seeing results "
            "is legitimate only if declared as such in the paper.", fill=LILAC)


# ==========================================================================
def build(force=False):
    """Build the report. Refuses to overwrite an existing file for this version.

    The front matter embeds the commit hash the tree was at, so rebuilding at a
    later commit produces a *different* file even when no narrative has changed
    — which means a version that has been sent is frozen, and rebuilding it
    silently replaces the copy the recipient holds. That is not hypothetical:
    it happened to v2 within an hour of it going to Oliver, and was caught only
    because `git status` showed the binary as modified. Bump REPORT_VERSION for
    a new version, or pass force to deliberately replace an unsent one.
    """
    if OUT.exists() and not force:
        raise SystemExit(
            f"{OUT.name} already exists.\n"
            f"The commit hash is embedded, so rebuilding produces a different "
            f"file and would replace a version that may already have been "
            f"sent.\nBump REPORT_VERSION (currently {REPORT_VERSION}) for a new "
            f"version, or run with --force to replace this one deliberately.")
    doc = Document()

    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    st.font.color.rgb = INK
    st.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    st.paragraph_format.space_after = Pt(7)
    st.paragraph_format.line_spacing = 1.12

    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.2)
        s.top_margin = s.bottom_margin = Cm(2.0)

    manifest = json.load(open(ROOT / "results" / "manifest.json"))["entries"]

    preds = []
    for line in open(ROOT / "PREDICTIONS.md"):
        if line.startswith("| P-"):
            parts = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(parts) >= 4:
                bears = {"P-01": "E4, T1/T2", "P-02": "E3", "P-03": "E5",
                         "P-04": "E6", "P-05": "E2", "P-06": "Probe P1",
                         "P-07": "Probe P2", "P-08": "Front end"}.get(parts[0], "—")
                preds.append([parts[0], parts[2], bears, parts[3]])

    open_q = open_questions()
    t1 = load("probe_e1_t1_synthetic")
    first_run = t1["points"][0]["runs"][0]
    r2 = load("reference_r2_t1_synthetic")
    t2 = load("t2_f0_contour_e1_synthetic")
    t3 = load("t3_boundary_e1_synthetic")
    p1 = load("p1_count_only_e1_synthetic")
    p2 = load("p2_corruption_e1_synthetic")
    e4_result = load("e4_adaptation_ratio")   # not `e4`: that is the section
    ctx = {
        "date": "9 September 2026",
        "commit": commit(),
        "passed": SUITE["passed"], "failed": SUITE["failed"],
        "skipped": SUITE["skipped"],
        "n_results": len(manifest),
        "n_open": len(open_q),
        "n_impl_tests": 136,
        "manifest": manifest,
        "predictions": preds,
        "t1": {"points": t1["points"],
               "floor": first_run["majority_floor"],
               "chance": first_run["chance"]},
        "r2": r2, "t2": t2, "t3": t3, "p1": p1, "p2": p2, "e4": e4_result,
        "n_superseded": sum(1 for e in manifest if e.get("superseded_by")),
    }

    front_matter(doc, ctx)
    overview(doc, ctx)
    summary_table(doc, ctx)
    front_end(doc, ctx)
    e1(doc, ctx)
    e2(doc, ctx)
    e3(doc, ctx)
    e4(doc, ctx)
    e5(doc, ctx)
    e6(doc, ctx)
    e7_and_references(doc, ctx)
    shared_machinery(doc, ctx)
    harness_section(doc, ctx)
    task_results_section(doc, ctx)
    results_section(doc, ctx)
    questions_section(doc, ctx)
    predictions_section(doc, ctx)

    # Deterministic output: python-docx stamps the current time into
    # docProps/core.xml, so an unchanged report would otherwise show as a diff
    # on every rebuild and a real content change would be indistinguishable
    # from noise. Pinned to the study start date (D11).
    stamp = _dt.datetime(2026, 8, 20, 0, 0, 0)
    cp = doc.core_properties
    cp.created = stamp
    cp.modified = stamp
    cp.last_modified_by = "Simon Davidson & Claude"
    cp.author = "Simon Davidson & Claude"
    cp.title = f"spikeEncode — encoder survey v{REPORT_VERSION}"
    cp.revision = REPORT_VERSION

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    _normalise_zip_times(OUT)
    print(f"written: {OUT}")
    if PENDING_NEXT_VERSION:
        print(f"\n{len(PENDING_NEXT_VERSION)} item(s) owed to the next version — "
              f"apply before bumping REPORT_VERSION:")
        for i, item in enumerate(PENDING_NEXT_VERSION, 1):
            print(f"  {i}. {item}")
    return OUT


if __name__ == "__main__":
    import sys
    build(force="--force" in sys.argv)
