#!/usr/bin/env python3
"""Generate EditScope_Report.pdf (verified n=104)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable, KeepTogether, ListFlowable, ListItem, PageBreak,
)

ACCENT = colors.HexColor("#2E5AAC")
ACCENT_DK = colors.HexColor("#1B3A6B")
GREEN = colors.HexColor("#1F8A4C")
GREEN_BG = colors.HexColor("#E4F4EA")
RED = colors.HexColor("#C0392B")
GREY = colors.HexColor("#5B6470")
LIGHT = colors.HexColor("#F2F5FA")
LINE = colors.HexColor("#D4DAE3")

# ---------------------------------------------------------------- figures
plt.rcParams.update({"font.size": 10, "font.family": "DejaVu Sans",
                     "axes.edgecolor": "#5B6470", "axes.linewidth": 0.8})

def fig_headline(path):
    fig, ax = plt.subplots(figsize=(6.6, 2.7), dpi=160)
    labels = ["P1 — Naive\nbaseline", "P4 — W2 + W1 router\n(EditScope)"]
    vals = [0.525, 0.0071]
    err = [[0.525-0.440, 0.0071-0.0], [0.610-0.525, 0.0213-0.0071]]
    bars = ax.bar(labels, vals, color=["#C0392B", "#1F8A4C"], width=0.55,
                  yerr=err, capsize=6, ecolor="#3A3A3A", error_kw={"elinewidth": 1})
    ax.set_ylabel("Necessary-collateral\nfalse-flag rate")
    ax.set_ylim(0, 0.72)
    ax.set_title("Collateral false-flag rate — real CanItEdit (n = 104)", fontweight="bold", fontsize=11)
    label_y = [0.628, 0.05]
    for b, v, ly in zip(bars, vals, label_y):
        ax.text(b.get_x()+b.get_width()/2, ly, f"{v*100:.1f}%",
                ha="center", va="bottom", fontweight="bold", fontsize=11)
    ax.annotate("~74× reduction\nat recall 1.00, 0 wrongly-authorized",
                xy=(1, 0.105), xytext=(0.52, 0.44), fontsize=9.5, color="#1B3A6B",
                ha="center", arrowprops=dict(arrowstyle="->", color="#1B3A6B"))
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y*100:.0f}%"))
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight"); plt.close(fig)

def fig_ladder(path):
    fig, ax = plt.subplots(figsize=(6.6, 2.8), dpi=160)
    pol = ["P1\nNaive", "P3\nW2-only", "P2\nW1-alone", "P4\nW2+W1", "P5\nW2+W1+res"]
    fpr = [0.54, 0.41, 0.008, 0.008, 0.008]
    rec = [1.00, 1.00, 1.00, 1.00, 0.79]
    cols = ["#C0392B", "#E08E0B", "#9B8Bd1", "#1F8A4C", "#7FA9D6"]
    bars = ax.bar(pol, fpr, color=cols, width=0.6)
    for b, f, r in zip(bars, fpr, rec):
        x = b.get_x()+b.get_width()/2
        ax.text(x, f+0.052, f"{f*100:.1f}%", ha="center", va="bottom",
                fontsize=9, fontweight="bold")
        ax.text(x, f+0.014, f"recall {r:.2f}", ha="center", va="bottom",
                fontsize=7, color="#5B6470")
    ax.set_ylabel("Collateral false-flag rate")
    ax.set_ylim(0, 0.62)
    ax.set_title("Policy ladder — why P4 (validated run, n = 95)", fontweight="bold", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y*100:.0f}%"))
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight"); plt.close(fig)

def fig_adv(path):
    fig, ax = plt.subplots(figsize=(6.6, 2.5), dpi=160)
    grp = ["P1 / P3\n(Violation)", "P2 — W1-alone\n(Authorized)", "P4 / P5\n(Uncertain)"]
    wrong = [0, 20, 0]
    cols = ["#1F8A4C", "#C0392B", "#1F8A4C"]
    bars = ax.bar(grp, wrong, color=cols, width=0.5)
    for b, w in zip(bars, wrong):
        ax.text(b.get_x()+b.get_width()/2, w+0.4, f"{w}/20",
                ha="center", va="bottom", fontweight="bold", fontsize=11)
    ax.set_ylabel("Wrongly authorized")
    ax.set_ylim(0, 22)
    ax.set_title("Adversarial W1-unsoundness probe (n = 20)", fontweight="bold", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight"); plt.close(fig)

fig_headline("/data/editscope/_fig_headline.png")
fig_ladder("/data/editscope/_fig_ladder.png")
fig_adv("/data/editscope/_fig_adv.png")

# ---------------------------------------------------------------- styles
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName="Helvetica-Bold",
                    fontSize=15, textColor=ACCENT_DK, spaceBefore=10, spaceAfter=5)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                    fontSize=11.5, textColor=ACCENT, spaceBefore=9, spaceAfter=3)
BODY = ParagraphStyle("BODY", parent=ss["BodyText"], fontName="Helvetica",
                      fontSize=9.5, leading=13.5, spaceAfter=5, alignment=TA_LEFT)
SMALL = ParagraphStyle("SMALL", parent=BODY, fontSize=8, textColor=GREY, leading=10.5)
BULLET = ParagraphStyle("BULLET", parent=BODY, leftIndent=10, spaceAfter=2)
TITLE = ParagraphStyle("TITLE", parent=ss["Title"], fontName="Helvetica-Bold",
                       fontSize=22, textColor=ACCENT_DK, spaceAfter=2, leading=25)
SUB = ParagraphStyle("SUB", parent=BODY, fontSize=11, textColor=GREY, spaceAfter=1)
CELL = ParagraphStyle("CELL", parent=BODY, fontSize=8.5, leading=11, spaceAfter=0)
CELLB = ParagraphStyle("CELLB", parent=CELL, fontName="Helvetica-Bold")
CELLH = ParagraphStyle("CELLH", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)

def P(t, s=BODY): return Paragraph(t, s)

def callout(text, bg=GREEN_BG, bar=GREEN):
    inner = Paragraph(text, ParagraphStyle("co", parent=BODY, fontSize=9.5, leading=13.5))
    t = Table([[inner]], colWidths=[16.4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("LEFTPADDING", (0,0), (-1,-1), 12), ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LINEBEFORE", (0,0), (0,-1), 3, bar),
    ]))
    return t

def make_table(data, col_widths, header_bg=ACCENT, zebra=True, highlight_row=None):
    style = [
        ("BACKGROUND", (0,0), (-1,0), header_bg),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.5, LINE),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]
    if zebra:
        for r in range(1, len(data)):
            if r % 2 == 0:
                style.append(("BACKGROUND", (0,r), (-1,r), LIGHT))
    if highlight_row is not None:
        style.append(("BACKGROUND", (0,highlight_row), (-1,highlight_row), GREEN_BG))
        style.append(("LINEBELOW", (0,highlight_row), (-1,highlight_row), 0.6, GREEN))
        style.append(("LINEABOVE", (0,highlight_row), (-1,highlight_row), 0.6, GREEN))
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(style))
    return t

story = []

# ---- header band / title
story.append(P("TECHNICAL REPORT · 24 JUN 2026 · VERIFIED n = 104", ParagraphStyle(
    "kick", parent=SMALL, textColor=ACCENT, fontName="Helvetica-Bold", fontSize=8.5, spaceAfter=4)))
story.append(P("EditScope", TITLE))
story.append(P("A <b>sound oracle</b> for scope-faithful code edits — separating authorized intent, "
               "necessary collateral, and unauthorized scope creep.", SUB))
story.append(Spacer(1, 3))
story.append(HRFlowable(width="100%", thickness=1.2, color=ACCENT))
story.append(Spacer(1, 6))

# ---- executive summary
story.append(P("Executive summary", H1))
story.append(P("AI coding agents <b>over-edit</b>: opportunistic refactors, reformatting, and unrelated "
    "churn beyond what was asked — risk that slips through <i>even when all tests pass</i>, because tests "
    "certify behavior, not authorization. The hard part is that not all unrequested change is illegitimate: "
    "renaming a function <i>forces</i> edits at every call site. A useful checker must separate "
    "<b>authorized intent</b>, <b>necessary collateral</b>, and <b>unauthorized creep</b> — naively flagging "
    "every non-seed edit is useless."))
story.append(P("EditScope is a <b>sound symbolic oracle</b> that does exactly this. A change unit is "
    "<b>Authorized</b> iff it is part of the instruction seed <b>or</b> satisfies W2 (forced closure: "
    "reverting it provably breaks compilation / name-resolution / imports, verified by a resolver — not an LLM). "
    "Everything else is a <b>Violation</b> or routed to <b>Closure-uncertain</b>. The guarantee is "
    "<b>soundness, not completeness</b>: it never wrongly authorizes; when unsure it abstains."))
story.append(callout(
    "<b>Headline (real CanItEdit, n = 104):</b> the recommended policy <b>P4</b> cuts the naive collateral "
    "false-flag rate from <b>52.5% to 0.71% (~74×)</b> at violation-recall <b>1.00</b>, with "
    "<b>0 wrongly-authorized</b> units. The result reproduces through the frozen <font face='Courier'>audit()</font> "
    "API and is locked by CI."))
story.append(Spacer(1, 4))
story.append(Image("/data/editscope/_fig_headline.png", width=15.2*cm, height=6.2*cm))

story.append(PageBreak())

# ---- problem & idea
story.append(P("1 · Problem & approach", H1))
story.append(P("Scope creep — the gap between <i>“the code works”</i> and <i>“the model did only what it was "
    "asked”</i> — inflates review burden and hides risk. Every changed unit falls into one of three classes:"))
story.append(ListFlowable([
    ListItem(P("<b>Authorized</b> — the instruction’s intent (the <i>seed</i>).", BULLET)),
    ListItem(P("<b>Necessary collateral</b> — structurally forced by an authorized change (e.g. a rename "
               "forcing call-site edits).", BULLET)),
    ListItem(P("<b>Unauthorized scope creep</b> — genuinely out-of-scope edits.", BULLET)),
], bulletType="bullet", start="square"))
story.append(P("2 · The idea — Warranted Edits (EditScope v3)", H2))
story.append(callout(
    "<b>Authorization = seed ∪ W2.</b> A unit is authorized if it is part of the instruction seed, OR it "
    "satisfies <b>W2 (forced closure)</b>: reverting it provably breaks compilation / name-resolution / imports, "
    "verified by a symbolic resolver. <b>W1 (behavioral necessity)</b> was proven <b>unsound</b> as a warrant "
    "and demoted to a <i>risk router</i> — a non-seed, non-W2 unit whose revert flips a test is routed to "
    "<b>Uncertain</b>, never auto-authorized.",
    bg=LIGHT, bar=ACCENT))
story.append(P("<b>Three outcomes:</b> Authorized · Violation · Closure-uncertain. "
    "<b>Recommended policy = P4</b> (W2 authorization + W1 router); <b>P1 (naive)</b> is the reported baseline. "
    "The resolver is symbolic — pyflakes + mypy(--strict) + a cross-file import/call-graph closure check — "
    "with no LLM and no code execution in the authorization path."))

# ---- experiment log
story.append(P("3 · Experiment log", H1))
story.append(P("3.1 · Synthetic kill-gate (Runs A–D)", H2))
story.append(ListFlowable([
    ListItem(P("<b>Run A:</b> naive FPR 1.00 · revert-only 0.50 · <b>+closure 0.00</b> at recall 1.00.", BULLET)),
    ListItem(P("<b>Run B:</b> W2-only is sound (0 violations); <b>W1 and W1∪W2 commit soundness violations</b> — "
               "the original two-warrant design failed.", BULLET)),
    ListItem(P("<b>Run C:</b> W2-only <b>PASS</b> (FPR 0.00, recall 1.00); naive / revert-only / closure each "
               "FAIL (8 soundness violations each).", BULLET)),
    ListItem(P("<b>Run D:</b> W2-only-strict hard-flags genuine collateral (Family F FPR 1.00); adding the "
               "<b>W1 router → 0.00</b> while staying sound.", BULLET)),
], bulletType="bullet", start="square"))

story.append(P("3.2 · Real data — CanItEdit, verified n = 104", H2))
story.append(P("Coverage: attempted <b>105</b>, passed-gold <b>104</b>, <b>1 skipped</b> (id 78 "
    "<font face='Courier'>llm_inference</font>, needs a <font face='Courier'>vllm</font> GPU server — the single "
    "principled exclusion). Nine previously-skipped problems were recovered by installing "
    "<font face='Courier'>z3</font>, <font face='Courier'>autograd</font>, and "
    "<font face='Courier'>torch</font> (skips were dependency-gated, not runner bugs)."))
t1 = make_table([
    [P("Policy", CELLH), P("Collateral FPR [95% CI]", CELLH), P("Recall", CELLH),
     P("Uncertain", CELLH), P("Wrongly auth.", CELLH)],
    [P("P1 — Naive baseline", CELL), P("0.525 [0.440–0.610]", CELL), P("1.00", CELL), P("0", CELL), P("0", CELL)],
    [P("<b>P4 — W2 + W1 router</b>", CELLB), P("<b>0.0071 [0–0.0213]</b>", CELLB), P("<b>1.00</b>", CELLB),
     P("<b>0.301</b>", CELLB), P("<b>0</b>", CELLB)],
], [4.4*cm, 4.6*cm, 1.9*cm, 2.4*cm, 2.6*cm], highlight_row=2)
story.append(t1)
story.append(Spacer(1, 3))
story.append(P("P4 cuts P1’s 52.5% false-flag rate to 0.71% (~74×) at recall 1.0, 0 wrongly-authorized — "
    "consistent with the earlier n = 95 / 96 runs (the larger denominator barely moves the numbers).", SMALL))
story.append(Spacer(1, 6))
story.append(Image("/data/editscope/_fig_ladder.png", width=15.2*cm, height=6.4*cm))
story.append(P("The five-policy ladder (validated run, n = 95) shows why P4 is chosen: W2-only (P3) ≈ naive — the "
    "<b>W1 router</b> does the discriminating work; P4 strictly dominates P5 (which drops recall 1.0→0.79 for no "
    "FPR gain); P2 ties P4 on collateral but is unsound (next).", SMALL))

story.append(PageBreak())

story.append(P("3.3 · Adversarial W1-unsoundness probe (n = 20)", H2))
story.append(P("Injected test-coupled out-of-scope edits placed in <b>separate, ungrounded</b> units "
    "(each <font face='Courier'>is_seed=False, w1=True, w2=False</font>), scored through the real "
    "<font face='Courier'>check / newly_broken / outcome</font> functions."))
t2 = make_table([
    [P("Policy", CELLH), P("Wrongly authorized", CELLH), P("Verdict", CELLH)],
    [P("P1 / P3", CELL), P("0 / 20", CELL), P("Violation", CELL)],
    [P("<b>P2 — W1-alone</b>", CELLB), P("<b>20 / 20</b>", ParagraphStyle("r",parent=CELLB,textColor=RED)),
     P("Authorized (unsound)", ParagraphStyle("r",parent=CELL,textColor=RED))],
    [P("<b>P4 — W2 + W1 router</b>", CELLB), P("<b>0 / 20</b>", CELLB), P("Uncertain (safe)", CELLB)],
    [P("P5", CELL), P("0 / 20", CELL), P("Uncertain", CELL)],
], [5.2*cm, 4.6*cm, 6.1*cm], highlight_row=3)
story.append(t2)
story.append(Spacer(1, 4))
story.append(Image("/data/editscope/_fig_adv.png", width=14.0*cm, height=5.3*cm))
story.append(P("This is the tie-breaker that justifies <b>P4 over P2</b>: P2 ties P4 on collateral (0.008) but is "
    "fooled 20/20 here, while P4 is fooled 0/20.", SMALL))
story.append(callout(
    "<b>Scope honesty:</b> these 20 are <i>separate-unit</i> test-coupled edits. A violation hidden "
    "<b>inside</b> an authorized unit (intra-unit smuggling) is a distinct, acknowledged blind spot — see §5.",
    bg=colors.HexColor("#FBF3D9"), bar=colors.HexColor("#E0A800")))

story.append(P("3.4 · Frozen-API parity", H2))
story.append(P("The oracle is frozen as a self-contained package (<font face='Courier'>scope_oracle/</font>, schema "
    "v1.0.0) exposing <font face='Courier'>audit()</font> / <font face='Courier'>audit_case()</font>. The headline "
    "reproduces <i>through the frozen contract</i>, not just the research harness:"))
t3 = make_table([
    [P("Metric", CELLH), P("Validated (n=95)", CELLH), P("Frozen oracle (n=96)", CELLH)],
    [P("P1 collateral FPR", CELL), P("0.538", CELL), P("0.5344", CELL)],
    [P("<b>P4 collateral FPR</b>", CELLB), P("<b>0.0077</b>", CELLB), P("<b>0.00763</b>", CELLB)],
    [P("P4 violation recall", CELL), P("1.00", CELL), P("1.00", CELL)],
    [P("Wrongly authorized", CELL), P("0", CELL), P("0", CELL)],
], [6.0*cm, 4.9*cm, 5.0*cm])
story.append(t3)
story.append(P("Soundness is enforced by an 8-test freeze suite (<font face='Courier'>test_audit_freeze</font>) that "
    "runs in CI on every push — currently green on <font face='Courier'>main</font>.", SMALL))

story.append(PageBreak())

# ---- limitations
story.append(P("4 · Limitations & threats to validity", H1))
story.append(ListFlowable([
    ListItem(P("<b>Trivial violation recall</b> on these sets — all injected violations were non-seed; real "
               "agent edits will distribute more naturally.", BULLET)),
    ListItem(P("<b>W2-only ≈ naive</b> — the discriminating power is the W1 router, not W2 alone.", BULLET)),
    ListItem(P("<b>Mutation-injected violations ≠ real scope creep</b> — the strongest reason to move to "
               "real-agent edits (Track A).", BULLET)),
    ListItem(P("<b>Python-only</b>; cross-file handled by a symbolic import/call-graph. Dynamic dispatch, "
               "<font face='Courier'>*</font>-imports, and runtime attribute resolution are conservatively "
               "treated as no-closure (Uncertain, never Violation).", BULLET)),
    ListItem(P("<b>Intra-unit smuggling</b> is <i>downgraded, not eliminated</i> — opt-in statement-level "
               "granularity now catches separable side-effecting smuggles in top-level functions, "
               "in class methods, return-feeding (external-mutation) statements, creep nested inside "
               "if / for / while / with / try blocks, and the canonical return-embedded short-circuit "
               "idiom (<font face='Courier'>mutator() or value</font>, reverted surgically so the real "
               "return is preserved) — each with a revert guard that keeps the soundness invariant intact; "
               "only non-mutator or effect-last embedded expressions and pure-local dead code remain out "
               "of scope (conservatively unflagged to avoid false positives such as "
               "<font face='Courier'>cache.get(k) or default</font>).", BULLET)),
    ListItem(P("<b>Dataset revision pinned</b> — runs target HF commit <font face='Courier'>3c07f38</font> of "
               "nuprl/CanItEdit (test split, 105 examples; parquet sha256 9f78b1a2…), so the benchmark is "
               "reproducible and the pin is recorded in every metric card.", BULLET)),
], bulletType="bullet", start="square"))

# ---- scorecard
story.append(P("5 · Publishability scorecard", H1))
story.append(callout(
    "<b>Publishability ≈ 80%, tier-dependent.</b> Novelty ~80% · mechanism soundness ~75% · method rigor ~75% "
    "· evidence realism ~45% · completeness ~55% · positioning ~75%.", bg=LIGHT, bar=ACCENT))
t4 = make_table([
    [P("Venue", CELLH), P("Odds now", CELLH), P("Path to lift", CELLH)],
    [P("Workshop / NIER", CELL), P("~85%", CELL), P("Ready — the floor deliverable", CELL)],
    [P("Mid-tier (SANER / ICSME)", CELL), P("~55–65%", CELL), P("Real-PR slice + non-toy resolver", CELL)],
    [P("Top SE / ML main track", CELL), P("~30–40% → ~55–65%", CELL), P("Real-agent benchmark + Pareto control win", CELL)],
], [4.8*cm, 3.8*cm, 7.3*cm])
story.append(t4)

# ---- next steps
story.append(P("6 · Next steps", H1))
story.append(ListFlowable([
    ListItem(P("<b>Track A (Measure):</b> run real coding agents through the frozen oracle; report a per-model "
               "metric card (pass rate · scope-violation rate · collateral false-flag rate · uncertain rate · "
               "extra-edit size); hunt a non-obvious finding.", BULLET)),
    ListItem(P("<b>Human-validated slice:</b> hand-label ~100–150 units; report oracle↔human agreement; reserve "
               "part as the <b>independent eval set</b> (defeats Track C circularity).", BULLET)),
    ListItem(P("<b>Track C (Control):</b> best-of-N selection → repair loop → DPO (compute-gated); report a "
               "<b>Pareto</b> win (violations ↓ at pass rate held).", BULLET)),
    ListItem(P("<b>Hardening:</b> add a real-PR slice for external validity (the residual intra-unit cases "
               "— non-mutator / effect-last embeddings — are rare and stay conservatively unflagged).", BULLET)),
], bulletType="bullet", start="square"))
story.append(Spacer(1, 8))
story.append(HRFlowable(width="100%", thickness=0.8, color=LINE))
story.append(P("EditScope — sound scope-edit oracle · frozen audit() API (schema v1.0.0) · resolver: "
    "symbolic pycompile + pyflakes + mypy(strict) + symbolic-import-name call-graph · repo: "
    "github.com/bharat06-co/editscope · generated 24 Jun 2026.", SMALL))

# ---------------------------------------------------------------- build
def on_page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(ACCENT); canvas.setLineWidth(2)
    canvas.line(2*cm, A4[1]-1.15*cm, A4[0]-2*cm, A4[1]-1.15*cm)
    canvas.setFont("Helvetica", 7.5); canvas.setFillColor(GREY)
    canvas.drawString(2*cm, A4[1]-1.0*cm, "EditScope — Technical Report")
    canvas.drawRightString(A4[0]-2*cm, A4[1]-1.0*cm, "verified n = 104")
    canvas.setFont("Helvetica", 8); canvas.setFillColor(GREY)
    canvas.drawCentredString(A4[0]/2, 1.0*cm, f"— {doc.page} —")
    canvas.restoreState()

doc = BaseDocTemplate("/data/editscope/EditScope_Report.pdf", pagesize=A4,
                      leftMargin=2*cm, rightMargin=2*cm, topMargin=1.6*cm, bottomMargin=1.5*cm,
                      title="EditScope Technical Report (n=104)", author="Bharat (P1)")
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=on_page)])
doc.build(story)
print("OK wrote EditScope_Report.pdf")
