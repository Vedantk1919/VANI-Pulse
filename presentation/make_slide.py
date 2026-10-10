"""One-slide summary for the Problem 3 submission (numbers read from outputs/*.json).

Run:  python presentation/make_slide.py      (writes presentation/best_time_to_call_one_slide.pptx)
"""
import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
bt = json.load(open(ROOT / "outputs/backtest_report.json"))
br = json.load(open(ROOT / "outputs/brief_report.json"))
comb, base, ev = bt["combined"], bt["retry_stop"]["baseline"], bt["retiming"]["empirical_validation"]
ips = br["off_policy_ips"]

INK, NAVY, AMBER, TEAL, MIST, WHITE, GREY = (RGBColor(0x14, 0x21, 0x3D), RGBColor(0x1F, 0x3A, 0x5F), RGBColor(0xE8, 0x9F, 0x2E),
                                             RGBColor(0x1C, 0x7C, 0x7D), RGBColor(0xEE, 0xF2, 0xF6), RGBColor(0xFF, 0xFF, 0xFF),
                                             RGBColor(0x5B, 0x67, 0x78))
HEAD, BODY = "Cambria", "Calibri"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
s = prs.slides.add_slide(prs.slide_layouts[6])
s.background.fill.solid()
s.background.fill.fore_color.rgb = WHITE


def box(x, y, w, h, fill=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=None):
    sh = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        sh.adjustments[0] = 0.08
    sh.shadow.inherit = False
    if name:
        sh.name = name
    return sh


def text(x, y, w, h, runs, size=14, color=INK, font=BODY, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        para.space_after = Pt(4)
        for seg in (p if isinstance(p, list) else [p]):
            t, o = (seg, {}) if isinstance(seg, str) else seg
            r = para.add_run()
            r.text = t
            r.font.name = o.get("font", font)
            r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", bold)
            r.font.color.rgb = o.get("color", color)
    return tb


# title
text(0.5, 0.35, 12.3, 0.6, "Best Time to Call: replace the fixed 15-minute redial", size=30, font=HEAD, bold=True)
text(0.5, 0.98, 12.3, 0.4, "Problem 3 | trained Apr-Aug 2026, tested on held-out September (124,779 dials) | target: meetings fixed, not connects",
     size=14, color=GREY)

# KPI callouts (left column)
kpis = [(f"{base['calls_per_meeting']} → {comb['calls_per_meeting']}", "calls per meeting (−19%)"),
        (f"−{abs(comb['dials_vs_baseline_pct'])}%", f"dials, {bt['retry_stop']['default']['meetings_retained_pct']}% of meetings kept"),
        (f"+{bt['retiming']['lift_equal_dials_pct']}%", "meetings at equal dials (model est.)"),
        (f"+{ips['lift_pct']}%", f"retry meetings, off-policy IPS (95% CI +{ips['lift_ci95_pct'][0]} to +{ips['lift_ci95_pct'][1]})")]
for i, (big, small) in enumerate(kpis):
    y = 1.6 + i * 1.12
    box(0.5, y, 3.9, 1.0, MIST, name=f"kpi{i}")
    text(0.7, y + 0.08, 3.5, 0.5, big, size=26, font=HEAD, bold=True, color=NAVY)
    text(0.7, y + 0.58, 3.5, 0.35, small, size=12, color=GREY)

# verdict card (middle)
box(4.7, 1.6, 4.1, 4.36, NAVY, name="verdict")
text(4.95, 1.78, 3.6, 0.4, "Verdict on the 15-minute rule", size=14, color=RGBColor(0xC9, 0xD6, 0xE8))
text(4.95, 2.15, 3.6, 0.7, "CHANGE", size=40, font=HEAD, bold=True, color=AMBER)
rules = ["No redial within 30 min: short redials fix 0-3% vs 3-5% at 30 min-2 h, in every segment",
         "Retry same day, 1-2 h or 4-8 h later, in the seller's best-scored slot (next day ≈ 0.5×)",
         "Max 3 dials / 24 h and 5 per lead; stop when P(meeting) < 1%",
         "Call Later = call at the asked time; busy → offer the seller's 2 best windows"]
text(4.95, 3.0, 3.65, 2.2, [[("▸ ", {"color": AMBER, "bold": True}), (r, {"color": WHITE})] for r in rules], size=13)
conn0 = base["answered"] / base["dials"]
conn1 = bt["retry_stop"]["default"]["connect_rate"]
text(4.95, 5.25, 3.65, 0.6, [[("Trade-off: ", {"color": AMBER, "bold": True}),
     (f"connect {conn0:.1%} → {conn1:.1%} | calls/meeting {base['calls_per_meeting']} → {comb['calls_per_meeting']} | "
      f"meetings {comb['meetings_vs_baseline_pct']:+}% with {abs(comb['dials_vs_baseline_pct'])}% fewer dials", {"color": WHITE})]], size=11)

# validation (right column)
box(9.1, 1.6, 3.73, 4.36, MIST, name="validation")
text(9.3, 1.78, 3.4, 0.4, "How we validated", size=18, font=HEAD, bold=True, color=NAVY)
val = ["Time split: train Apr-Aug, test Sept (no shuffling; volume grew ~6.6×)",
       f"Real outcomes: best-scored slots beat worst by +{ev['first attempt Q5_vs_Q1_meeting_lift_pct']}% (first calls) and +{ev['retry Q5_vs_Q1_meeting_lift_pct']}% (retries), bootstrap CIs exclude 0",
       f"Off-policy IPS on retries: +{ips['lift_pct']}% (CI {ips['lift_ci95_pct'][0]} to {ips['lift_ci95_pct'][1]})",
       "Label check: 2.4% false meetings, flat by hour; AUC unchanged",
       "Ensemble AUC 0.754 (vs 4 models); new sellers fall back to segment patterns"]
text(9.3, 2.3, 3.35, 2.9, [[("✓ ", {"color": TEAL, "bold": True}), v] for v in val], size=12)
text(9.3, 5.25, 3.35, 0.6, [[("Limit: ", {"color": AMBER, "bold": True}),
     "re-timing lift is estimated from data logged under the old schedule; confirm with a 5% A/B test."]], size=11, color=GREY)

# workflow (bottom)
steps = [("Data", "530k dials, 149k sellers, transcripts"), ("Features", "past-only history, segment, slot"),
         ("Model", "LightGBM+XGBoost+CatBoost\nP(answer), P(meeting)"), ("Policy", "gap curve + guardrails\n+ stop rule"),
         ("Output", "weekly windows, retry ladder,\nVANI prompt")]
w, gap, y = 2.2, 0.32, 6.2
for i, (h, d) in enumerate(steps):
    x = 0.5 + i * (w + gap)
    box(x, y, w, 0.95, WHITE if i else WHITE, name=f"step{i}").line.color.rgb = RGBColor(0xC9, 0xD3, 0xDF)
    text(x + 0.15, y + 0.08, w - 0.3, 0.3, h, size=14, bold=True, color=TEAL)
    text(x + 0.15, y + 0.4, w - 0.3, 0.5, d, size=11, color=GREY)
    if i < len(steps) - 1:
        a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + w + 0.06), Inches(y + 0.36), Inches(0.2), Inches(0.22))
        a.fill.solid(); a.fill.fore_color.rgb = AMBER; a.line.fill.background()

out = ROOT / "presentation" / "best_time_to_call_one_slide.pptx"
prs.save(out)
print(out)
