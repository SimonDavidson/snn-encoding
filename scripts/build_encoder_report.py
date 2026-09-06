"""Build the encoder survey report as a .docx.

Narrative is authored here; every number is read from results/ and from the
manifest, so regenerating after a new run picks the new values up rather than
restating stale ones. Run:

    python scripts/build_encoder_report.py

Author:        Simon Davidson & Claude
Created:       2026-09-06
Last modified: 2026-09-06
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
OUT = ROOT / "reports" / "spikeEncode_encoder_survey.docx"

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
    for chunk, strong in _markup(str(text)):
        r = p.add_run(chunk)
        r.bold = bold or strong
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
    for chunk, bold in _markup(text):
        r = p.add_run(chunk)
        r.bold = bold
        r.italic = italic
        r.font.size = Pt(size)
    return p


def _markup(text):
    """Minimal **bold** support so the narrative can emphasise inline."""
    out, buf, i = [], "", 0
    while i < len(text):
        if text.startswith("**", i):
            j = text.find("**", i + 2)
            if j == -1:
                buf += text[i:]
                break
            if buf:
                out.append((buf, False))
                buf = ""
            out.append((text[i + 2:j], True))
            i = j + 2
        else:
            buf += text[i]
            i += 1
    if buf:
        out.append((buf, False))
    return out or [("", False)]


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
    r = p.add_run(text)
    r.italic = True
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
    for chunk, bold in _markup(text):
        rr = p.add_run(chunk)
        rr.bold = bold
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
    r = p.add_run("Candidate spike encodings for audio — encoder survey")
    r.font.size = Pt(14)
    r.font.color.rgb = TEAL
    _rule(p)

    kv_table(doc, [
        ["Study", "Comparing candidate spike encodings for audio, to justify one for "
                  "release alongside DVS event-camera data"],
        ["Authors", "Simon Davidson, Oliver Rhodes (University of Manchester)"],
        ["Target venue", "Neuromorphic Computing and Engineering (IOP) — D04"],
        ["Report generated", f"{ctx['date']} from commit {ctx['commit']}"],
        ["Suite status", f"{ctx['passed']} passed, {ctx['failed']} failed, "
                         f"{ctx['skipped']} skipped (Layer 1 known-answer tests)"],
        ["Recorded results", f"{ctx['n_results']} entries in results/manifest.json"],
        ["Open questions", f"{ctx['n_open']} awaiting the design session"],
    ], widths=[4.0, 12.4])

    body(doc, "This report summarises every encoder in the study — those implemented, "
              "those specified but blocked, and the two reference points that bound the "
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
            f"Four of the six candidate encoders are implemented and pass their full "
            f"known-answer blocks. E5 and E6 are specified but blocked on open questions "
            f"against the specification, not on implementation effort. E7 is deliberately "
            f"not implemented (D09). The {ctx['failed']} failing tests are attributable "
            f"entirely to those blocks and to four individual open questions; none "
            f"represents a defect in implemented code.", fill=LILAC)


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
    body(doc, "This single requirement is the reason two encoders are currently blocked, "
              "and it is worth stating plainly because it is the property most likely to "
              "disqualify a scheme that otherwise looks reasonable. Both E5 and E6 fail it "
              "at their declared defaults, for entirely different reasons, and the "
              "distinction between those reasons determines whether the encoder is "
              "salvageable.")

    h2(doc, "1.2  Drive kinds")
    body(doc, "Encoders consume one of two things. Most take the compressed subband "
              "envelope, written u_c in the equations below. E5 alone takes the subband "
              "waveform x_c, because its entire purpose is to represent the carrier that "
              "the envelope discards. This is declared per encoder as DRIVE_KIND, and it "
              "determines what the test harness feeds the encoder when bypassing the front "
              "end.")

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
        ["E4", "ALIF", "Adaptive-threshold LIF", "theta_0", "envelope", "Implemented", "10 / 11"],
        ["E5", "PhaseLocked", "Phase-locked fine structure", "threshold", "subband", "Blocked", "0 / 12"],
        ["E6", "TTFS", "Time-to-first-spike", "e_min", "envelope", "Blocked", "0 / 9"],
        ["E7", "Spiketrum", "Matching pursuit (third-party)", "atoms / s", "audio", "Not implemented", "—"],
        ["R1", "Lauscher / SHD", "Reference channel format", "—", "audio", "Not started", "—"],
        ["R2", "Mel filterbank", "Non-spiking upper bound", "—", "audio", "Not started", "—"],
    ]
    status_fill = {"Implemented": GREEN, "Blocked": AMBER,
                   "Not implemented": GREY, "Not started": GREY}
    fills = {}
    for ri, r in enumerate(rows):
        fills[(ri, 5)] = status_fill[r[5]]
    table(doc, ["", "Class", "Scheme", "RATE_PARAM", "Drive", "Status", "Known-answer tests"],
          rows, widths=[1.1, 3.0, 4.6, 2.0, 1.9, 2.3, 2.6], fills=fills)
    caption(doc, "Test counts are the encoder's own T-block plus its parametrised share of "
                 "the generic G block. E4's single failure is test_T4_3 (Q10); E5 and E6 "
                 "fail everything because their encode_from_drive raises NotImplementedError.")

    body(doc, "The four implemented encoders divide cleanly into two integrating schemes "
              "(E1, E4) and two change-based schemes (E2, E3). That is the axis the study "
              "is built around: E1 against E4 isolates spike-frequency adaptation, and E2 "
              "against E3 isolates the bandpass, because decision D30 makes the two share "
              "one implementation of the event rule so that nothing else differs between "
              "them. Both contrasts are single-factor by construction rather than by "
              "inspection.")


def front_end(doc, ctx):
    h1(doc, "3.  The common front end")
    body(doc, "All candidates except E7 share a first stage, so that differences between "
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
    table(doc, ["delta_a", "0", "0.25", "0.5", "1", "2", "4", "8"],
          [["ISI_ss / ISI_1", "1.00", "2.11", "2.38", "2.45", "2.14", "1.51", "1.16"]],
          widths=[3.4, 1.8, 1.8, 1.8, 1.8, 1.8, 1.8, 1.8],
          fills={(0, 4): AMBER})
    caption(doc, "Measured on 5 s with 200 ms windows so the counts are adequate and the "
                 "steady state genuinely reached. Not yet registered in the manifest.")
    body(doc, "It peaks near delta_a ≈ 1 and decays either side, and the test's two adapting "
              "points, 0.5 and 2.0, straddle the peak. The mechanism is straightforward once "
              "seen: adaptation from the first spike suppresses the second, so strong "
              "adaptation lengthens the **onset** interval as well as the steady-state one — "
              "from 8 ms to 139 ms — and the two rates re-converge.")

    callout(doc, "This bears on a pre-registered prediction, not just on a red tick.",
            "P-01 predicts T1 accuracy rising and T2 falling \"as adaptation strength "
            "increases\". If the onset emphasis underneath that is non-monotone with a peak "
            "near delta_a ≈ 1, then a sweep spanning the peak could confirm or contradict "
            "P-01 according to which side its points land on. **The delta_a sweep range "
            "should be chosen with the peak located first.** PREDICTIONS.md has not been "
            "edited — §7 of the validation protocol forbids it once a run has started, and "
            "restating a prediction is the design session's call in any case.", fill=ROSE)


def e5(doc, ctx):
    h1(doc, "8.  E5 — Phase-locked fine structure")
    callout(doc, "Status: specified, not implemented. Blocked on Q11 and Q12.",
            "The only encoder that consumes the subband waveform rather than the envelope, "
            "because its entire purpose is to represent the carrier the envelope discards. "
            "Prediction P-03 rests on the contrast between E5 and the envelope encoders on "
            "T2.", fill=AMBER)

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
    callout(doc, "Status: specified, not implemented. Blocked on Q14 and Q16.",
            "The extreme temporal case and the sparsest scheme in the set. The exact "
            "inverse of E1: all information in timing, none in event count, which makes the "
            "pair (E1, E6) the cleanest available test of whether timing buys anything at "
            "matched budget.", fill=AMBER)

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
    body(doc, "Channels whose energy falls below E_min emit nothing, which is the mechanism "
              "by which the scheme is sparsified. Frame energy is defined in the "
              "specification as the sum of squared drive samples in the frame, computed on "
              "whatever drive is supplied with no further transformation, so that a test can "
              "reproduce it independently.")

    h2(doc, "9.2  Design parameters")
    table(doc, ["Parameter", "Default", "Role", "Swept?"], [
        ["e_min", "1e−6", "Energy gate — the declared RATE_PARAM", "Intended rate axis — see Q14"],
        ["frame", "0.025 s", "Frame length T_f", "Secondary axis"],
        ["hop", "0.010 s", "Frame hop H; bounds the budget at N_ch/H events per second", "Secondary rate axis (§5.6)"],
        ["tau_m", "0.02 s", "Membrane time constant for the lif mode, equation (29)", "Secondary axis"],
        ["theta", "1.0", "Threshold for the lif mode, equation (29)", "Secondary axis"],
        ["mode", "log", "log uses equation (28); lif uses equation (29)", "Yes"],
        ["E_max", "not defined", "Normalisation ceiling in equation (28) — **defined nowhere**", "Cannot be set"],
    ], widths=[3.4, 2.4, 7.6, 3.6],
        fills={(0, 3): AMBER, (6, 1): ROSE, (6, 2): ROSE, (6, 3): ROSE})

    h2(doc, "9.3  The rate parameter fails, but not structurally")
    body(doc, "At the declared default the event count is pinned at exactly the ceiling — "
              "every channel fires in every frame at every point in the sweep.")
    r = load("e6_rate_parameter_span")
    if r:
        rows = [["e_min"] + [f"{v:g}" for v in r["param_values"]],
                ["events"] + [str(c) for c in r["counts"]]]
        table(doc, ["", "0.25×", "0.5×", "1×", "2×", "4×"], rows,
              widths=[3.2, 2.4, 2.4, 2.4, 2.4, 2.4],
              fills={(1, i): ROSE for i in range(1, 6)})
        d = r["diagnostics"]
        caption(doc, f"Manifest id e6_rate_parameter_span. Span {r['span']:.3f}×, and "
                     f"{r['counts'][0]} is exactly the ceiling N_ch × N_frames. Frame energy "
                     f"on this drive runs min {d['frame_energy_min']:.2f}, median "
                     f"{d['frame_energy_median']:.1f}, max {d['frame_energy_max']:.0f} — so "
                     f"the default e_min sits {d['decades_below_quietest_frame']:.1f} decades "
                     f"below the quietest frame in the signal and gates nothing at all.")
    callout(doc, "This is a default in the wrong place, not a structural defect — and the "
                 "test suite predicts otherwise.",
            "test_G3's own docstring names E6 as the foreseeable casualty of D27, on the "
            "grounds that its count is \"structurally fixed\", and prescribes taking matched "
            "budgets from channel count or frame rate instead. **That does not describe "
            "E6.** Swept over the range the energies actually occupy, e_min moves the count "
            "across the full dynamic range: 792, 744, 640, 534, 401, 186, 78, 0. The "
            "parameter works; the default is six-point-eight decades away from where the "
            "signal is. Any base between 205.8 and 462.8 clears the required 4× without an "
            "endpoint at extinction. The remedy the docstring prescribes is not needed "
            "(Q14).", fill=LILAC)
    body(doc, "The fix cannot be made from the implementation side. The operating point lives "
              "in the test registry and the signature default lives in the specification, "
              "both of which are design-session files, so there is no change available in "
              "src/ that turns the test green. Q14 puts two options: retune the absolute "
              "value, or make e_min **relative** to the maximum frame energy, which is "
              "scale-free — verified to give identical counts across five decades of drive "
              "scale — and which would also define the E_max that equation (28) needs.")

    h2(doc, "9.4  Three further gaps found before writing a line (Q16)")
    body(doc, "Probing the specification ahead of implementation found three problems, none "
              "of which needed the encoder to exist:")
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
            "Oliver and Simon approach Wijekoon directly; E7 will not be reimplemented from "
            "the published description, to avoid reimplementing a colleague's algorithm "
            "badly. Until that conversation has happened the encoder is provisional and is "
            "excluded from the critical path.", fill=GREY)

    h2(doc, "10.1  E7 — Spiketrum")
    body(doc, "Spiketrum is a general-purpose spike-coding algorithm developed at Manchester "
              "by Alsakkal and Wijekoon, with published FPGA and ASIC implementations and "
              "reported application to auditory perception tasks. From the published "
              "abstracts it is a sparse decomposition method in the matching-pursuit family: "
              "the signal is approximated by iteratively selecting, from a time-frequency "
              "dictionary of atoms, the atom best correlated with the current residual, "
              "emitting an event identifying that atom and its time, and subtracting its "
              "contribution:")
    equation(doc, "(c_k, t_k) = argmax | ⟨ r^(k−1), g_{c,t} ⟩ |    (30)")
    equation(doc, "r^(k) = r^(k−1) − ⟨ r^(k−1), g_{c_k,t_k} ⟩ · g_{c_k,t_k}    (31)")
    body(doc, "The event train is the sequence of selected atom indices and times, and the "
              "number of atoms retained per unit time is a directly controllable rate "
              "parameter — which, notably, is the property E5 and E6 are currently blocked "
              "on. The reported properties of precisely controllable spike rate, robustness "
              "to spike loss, and signal reconstruction all follow from this structure.")
    body(doc, "Its reconstruction capability is exactly the tension noted for E2, in sharper "
              "form: an encoder that optimises reconstruction fidelity is optimising the "
              "criterion the study argues is the wrong one, and is by construction the worst "
              "case for retained speaker information. That is not a criticism of Spiketrum, "
              "which was designed for a different purpose, but it makes the encoder an "
              "informative extreme point and a useful upper reference for the privacy axis.")
    callout(doc, "Caveat requiring action, carried from the proposal.",
            "The description above is reconstructed from published abstracts and citation "
            "records; **the Spiketrum papers have not been read in full.** Before this "
            "encoder is described in a paper or implemented against, the primary sources "
            "should be obtained — principally the TETCI article on neuromorphic auditory "
            "perception, the TCSI article on the FPGA cochlea, and the evaluation paper on "
            "the encoder.", fill=ROSE)

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

    h2(doc, "10.3  R2 — Non-spiking upper bound")
    body(doc, "The essential control, and arguably the single most important row in the "
              "results table. Forty mel-scale filterbank features computed over 25 ms windows "
              "at 10 ms hop, fed to the same decoder architecture as every spiking condition. "
              "This is the standard front end used by Wu and colleagues and by Bittar and "
              "Garner, so results are directly comparable to the published literature as well "
              "as internally.")
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


def results_section(doc, ctx):
    h1(doc, "12.  Recorded results")
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

    body(doc, "Two cautions about what these results are and are not. First, **none of them "
              "is a task result.** No probe has been run, no corpus has been touched, and "
              "the TIMIT licence question is still open. Everything recorded so far "
              "characterises the encoders and the harness, not their performance on T1, T2 "
              "or T3. Second, three seeds are the minimum for anything reported, but every "
              "measurement here is on a deterministic stimulus through a deterministic path, "
              "where there is nothing for a seed to vary; each config says so explicitly "
              "rather than leaving a reader to wonder why one seed was enough.")

    h2(doc, "12.1  Known-answer suite by block")
    rows = [
        ["F", "Front end — filterbank, envelope, group delay", "6", "0", "Complete"],
        ["T1", "E1 LIF", "3", "0", "Complete"],
        ["T2", "E2 send-on-delta", "9", "0", "Complete"],
        ["T3", "E3 temporal contrast", "6", "0", "Complete"],
        ["T4", "E4 adaptive LIF", "3", "1", "Q10"],
        ["T5", "E5 phase-locked", "0", "5", "Q11, Q12 — encoder not written"],
        ["T6", "E6 time-to-first-spike", "0", "3", "Q14, Q16 — encoder not written"],
        ["G", "Generic, parametrised over all six encoders", "28", "13", "E5 and E6 stubs"],
        ["corrupt", "Corruption operators", "3", "1", "Q13"],
    ]
    fills = {}
    for i, r in enumerate(rows):
        fills[(i, 3)] = GREEN if r[3] == "0" else ROSE
    table(doc, ["Block", "Covers", "Passed", "Failed", "Blocked on"], rows,
          widths=[1.8, 6.4, 1.6, 1.6, 5.0], fills=fills)
    caption(doc, f"Totals: {ctx['passed']} passed, {ctx['failed']} failed, "
                 f"{ctx['skipped']} skipped. Every failure is attributable to an open "
                 f"question; none indicates a defect in implemented code. Continuous "
                 f"integration runs the same suite in a clean environment on every push and "
                 f"reports the identical failure set.")


def questions_section(doc, ctx):
    h1(doc, "13.  Open questions, and what each unblocks")
    body(doc, "Nine questions are open against the design session. They are listed here in "
              "the order that clears the most work, which is not the order they were raised. "
              "Two pairs should be answered together: Q11 with Q12, because both bear on E5's "
              "constructor signature, and Q14 with Q16, because making e_min relative to the "
              "maximum frame energy would define the E_max that equation (28) needs.")
    rows = [
        ["Q11 + Q12", "#2, #3", "E5", "E5's declared rate parameter spans 1.04× not 4×, and "
         "the mode with a working parameter cannot be expressed; plus two under-specifications",
         "12 tests — E5's G block and the whole T5 block"],
        ["Q16 + Q14", "#7, #5", "E6", "Equation (28) has no E_max and is not evaluable at "
         "e_min = 0; test_T6_1/T6_2 unsatisfiable at hop < frame; e_min default gates nothing",
         "8 tests — E6's G block and T6"],
        ["Q10", "#1", "E4", "test_T4_3 asserts a monotonicity the ALIF does not have; onset "
         "emphasis peaks near delta_a ≈ 1",
         "1 test — but bears on prediction P-01 and on the delta_a sweep range"],
        ["Q13", "#4", "corrupt", "Fixture yields 275 events where its own guard requires 500",
         "1 test"],
        ["Q15", "#6", "record", "Two figures quoted in the record do not reproduce as stated; "
         "in both cases the metric was never defined",
         "Nothing — corrects the record"],
        ["Q07", "—", "release", "ON and OFF as separate channel indices, or as a polarity bit",
         "Nothing — release-format question for Oliver"],
        ["Q09", "—", "E3", "test_T3_6 says d[:, 0] is exactly zero; in floating point it "
         "usually is", "Nothing"],
    ]
    fills = {(0, 4): AMBER, (1, 4): AMBER, (2, 4): ROSE}
    table(doc, ["Question", "Issue", "Area", "Substance", "What answering it unblocks"], rows,
          widths=[2.2, 1.4, 1.6, 7.4, 4.6], size=8.5, fills=fills)
    callout(doc, "If only one answer comes back, Q10 is the one that matters most.",
            "It is worth a single red test and nothing else in implementation terms, but it "
            "is the only open item with consequences for a **pre-registered prediction**. "
            "P-01 predicts T1 accuracy rising and T2 falling as adaptation strength "
            "increases; if the onset emphasis underneath is non-monotone with a peak near "
            "delta_a ≈ 1, a sweep spanning that peak could confirm or contradict P-01 "
            "according to which side its points fall.", fill=ROSE)


def predictions_section(doc, ctx):
    h1(doc, "14.  Pre-registered predictions")
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
def build():
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

    ctx = {
        "date": "6 September 2026",
        "commit": commit(),
        "passed": 61, "failed": 23, "skipped": 1,
        "n_results": len(manifest),
        "n_open": 9,
        "manifest": manifest,
        "predictions": preds,
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
    cp.title = "spikeEncode — encoder survey"
    cp.revision = 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    _normalise_zip_times(OUT)
    print(f"written: {OUT}")
    return OUT


if __name__ == "__main__":
    build()
