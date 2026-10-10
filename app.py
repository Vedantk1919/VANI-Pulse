"""VANI Best Time to Call - demo dashboard.   Run:  streamlit run app.py

Pages follow the demo story: overview -> what the data says -> demo sellers (history, plan,
before vs after, prompt) -> talk to VANI on Sarvam -> results and validation.
"""
import json
from datetime import datetime, time

import altair as alt
import pandas as pd
import streamlit as st

from src.config import OUT_DIR
from src import demo_sellers as ds
from src import prompt_gen as pg
from src import sarvam
from src import seller_md as sm

st.set_page_config(page_title="VANI Best Time to Call", layout="wide", page_icon="📞")

NAVY, AMBER, TEAL, GREY, RED = "#1F3A5F", "#E89F2E", "#1C7C7D", "#8A94A6", "#C0504D"
OUTCOME_COLORS = alt.Scale(domain=["Meeting Fixed", "Call Later / Busy", "General (talked)", "Not Interested", "Not Answered"],
                           range=[TEAL, AMBER, "#5B8DB8", RED, "#C8CED8"])


@st.cache_data
def load_json(name):
    p = OUT_DIR / name
    return json.load(open(p)) if p.exists() else None


@st.cache_resource
def warm():
    pg._attempts_by_seller(); pg._persona(); pg._model(); sm._timeline(); sm._profile(); sm._vani_dials()
    ds._persona_counts()
    from src import predict as pr
    pr.catalog()
    return True


rep, mrep, ana, brief = load_json("backtest_report.json"), load_json("model_report.json"), load_json("analysis.json"), load_json("brief_report.json")

# ------------------------------------------------------------------ sidebar: page + seller
PAGES = ["1 · Overview", "2 · What the data says", "3 · Best time to call & 15-min rule", "4 · Predict for any GLID (live)",
         "5 · Demo sellers", "6 · Talk to VANI (Sarvam)", "7 · Results & validation", "8 · 🧪 Live GLID test (runtime)"]
qp = st.query_params                      # direct links: ?p=3&s=2 opens page 3 with demo seller 2
page = st.sidebar.radio("Demo flow", PAGES, label_visibility="collapsed",
                        index=min(max(int(qp.get("p", 1)) - 1, 0), len(PAGES) - 1))
st.sidebar.divider()
st.session_state["mask"] = st.sidebar.toggle("🎬 Recording mode", value=st.session_state.get("mask", False),
                                             help="Hides company, product, buyer-city names and GLIDs on screen. VANI still gets the real prompt.")
st.sidebar.markdown("**Seller under test**")
if not ds.DEMO:
    st.sidebar.warning("No demo sellers: create data/demo_sellers.json (see src/demo_sellers.py).")
labels = [f"{i + 1}. {d['scenario']}" + ("" if st.session_state["mask"] else f" · {d['glid']}")
          for i, d in enumerate(ds.DEMO)] + ["Custom GLID…"]
choice = st.sidebar.selectbox("Demo seller", labels, label_visibility="collapsed",
                              index=min(max(int(qp.get("s", 1)) - 1, 0), len(labels) - 1))
if choice == "Custom GLID…":
    glid = int(st.sidebar.number_input("GLID", value=0, step=1))
    d_ = st.sidebar.date_input("As of", value=datetime(2026, 9, 15).date())
    t_ = st.sidebar.time_input("Time", value=time(11, 0))
    at = datetime.combine(d_, t_)
    scenario = None
else:
    sel = ds.DEMO[labels.index(choice)]
    glid, at, scenario = sel["glid"], datetime.fromisoformat(sel["at"]), sel
    st.sidebar.caption((f"GLID {glid} · " if not st.session_state.get("mask") else "") + f"as of {at:%a %d %b %Y %H:%M}")
    st.sidebar.caption(sel["show"])


def source(*keys, extra=None):
    """'📁 Source' line naming the dataset file(s) or our computed output behind a number or chart."""
    parts = [ds.SOURCES[k][0] for k in keys] + ([extra] if extra else [])
    st.caption("📁 Source: " + " · ".join(parts))


def kpi_row(items, widths=None):
    """items: (label, value, note) -> metric with a plain note underneath (no misleading arrows),
    or (label, value, delta, delta_color) -> metric with a coloured delta."""
    cols = st.columns(widths or len(items))
    for c, it in zip(cols, items):
        if len(it) == 4:
            c.metric(it[0], it[1], it[2], delta_color=it[3])
        else:
            c.metric(it[0], it[1])
            if it[2]:
                c.caption(it[2])


# ------------------------------------------------------------------ 1. overview
def page_overview():
    st.title("📞 VANI: Best Time to Call")
    st.markdown("##### Call each seller at the right time, retry without irritating them, and open the call with what VANI already knows.")
    if rep:
        comb, base, d = rep["combined"], rep["retry_stop"]["baseline"], rep["retry_stop"]["default"]
        kpi_row([("Calls per meeting", f"{comb['calls_per_meeting']}", f"from {base['calls_per_meeting']}"),
                 ("Dials", f"{comb['dials_vs_baseline_pct']}%", f"{d['meetings_retained_pct']}% of meetings kept"),
                 ("Meetings at equal dials", f"+{rep['retiming']['lift_equal_dials_pct']}%", "model estimate"),
                 ("Off-policy check", f"+{brief['off_policy_ips']['lift_pct']}%" if brief else "-",
                  f"95% CI {brief['off_policy_ips']['lift_ci95_pct'][0]} to {brief['off_policy_ips']['lift_ci95_pct'][1]}" if brief else ""),
                 ("15-minute rule", "CHANGE", "short redials lose in every segment")])
        source("backtest", "brief", extra="held-out September 2026 dials from Call Attempts Apr-Sep 2026.csv")
    st.divider()
    c1, c2 = st.columns([1.1, 1])
    with c1:
        st.subheader("The problem")
        st.markdown("""
- VANI calls sellers on a **fixed schedule** and redials unanswered calls after a **fixed 15 minutes**.
- It takes **~17 dials to fix one meeting**, and repeated calls irritate sellers
  (*"baar baar call mat kijiye"*).
- Optimising pickups alone doesn't produce meetings. **The goal is meetings fixed.**""")
        source("analysis", extra="Call Attempts Apr-Sep 2026.csv · ps07_call_turns.csv (frustration quotes)")
        st.subheader("What we built")
        st.markdown("""
1. **Timing model** – an ensemble (LightGBM + XGBoost + CatBoost) predicts P(answer) and **P(meeting)** for every seller × hour slot.
2. **Retry rules from the data** – gap curve, anti-irritation limits and a stop rule replace the 15-minute redial.
3. **Per-seller VANI prompt** – opening hook, tone, pace, language, busy handling and live adaptation, each backed by data.
4. **Seller memory (Global Context)** – `seller.md` from enquiries, WhatsApp, buyer calls and past calls, so VANI never re-asks.
5. **Allocator and lead tiers** – plans a whole queue under dialer capacity in ~14 ms per lead.""")
    with c2:
        st.subheader("How it works")
        st.graphviz_chart("""
digraph G { rankdir=TB; node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=11 color="#1F3A5F" fillcolor="#EEF2F6"];
  data [label="530k dials · 149k sellers\\n12.8k transcripts · 5k seller timelines"];
  feat [label="Features (past-only)\\nhistory · segment · slot · context"];
  model [label="Ensemble model\\nP(answer), P(meeting)" fillcolor="#1F3A5F" fontcolor="white"];
  mem [label="seller.md\\n(Global Context)"];
  pol [label="Policy\\ngap curve · guardrails · stop · tiers"];
  plan [label="Call plan\\nnext slot · windows · retry ladder" fillcolor="#E89F2E"];
  prompt [label="VANI prompt\\nhook · tone · memory · live adaptation" fillcolor="#E89F2E"];
  sarvam [label="Sarvam voice agent" fillcolor="#1C7C7D" fontcolor="white"];
  data -> feat -> model -> pol -> plan; data -> mem; mem -> pol; mem -> prompt; plan -> prompt -> sarvam;
  sarvam -> mem [label=" write-back" fontsize=9 style=dashed]; }""")
    st.info("Use the sidebar to follow the demo: data → demo sellers → talk to VANI → results.")


# ------------------------------------------------------------------ 2. analysis
def bar(df, x, y, title, fmt=".0%", color=NAVY, highlight=None, sort=None, height=230):
    df = df.copy()
    df["_c"] = [AMBER if highlight and highlight(r) else color for _, r in df.iterrows()]
    ch = alt.Chart(df).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X(f"{x}:N", sort=sort, title=None), y=alt.Y(f"{y}:Q", axis=alt.Axis(format=fmt), title=None),
        color=alt.Color("_c:N", scale=None), tooltip=[x, alt.Tooltip(f"{y}:Q", format=fmt)])
    text = ch.mark_text(dy=-7, fontSize=10, color="#333").encode(text=alt.Text(f"{y}:Q", format=fmt.replace("0%", "1%")))
    return (ch + text).properties(title=title, height=height)


def page_analysis():
    st.title("What the data says")
    t = ana["totals"]
    kpi_row([("Dials (Apr–Sep 2026)", f"{t['dials']:,}", None), ("Sellers", f"{t['sellers']:,}", None),
             ("Meetings fixed", f"{t['meetings']:,}", None), ("Answer rate", f"{t['answer_rate']:.1%}", None),
             ("Dials per meeting", f"{t['dials_per_meeting']}", None)])
    source("attempts", "sellers")
    st.divider()
    c1, c2 = st.columns(2)
    h = pd.DataFrame(ana["hour_first_attempt"]).assign(hour=lambda d: d.hour.astype(int).map(lambda x: f"{x}:00"))
    c1.altair_chart(bar(h, "hour", "meeting_rate", "1 · First calls: meeting rate by hour",
                        highlight=lambda r: r.hour in ("18:00", "19:00", "20:00"), sort=None), width="stretch")
    c1.caption("Evening (6–9 PM) converts best; 9 AM, mostly overnight backlog, is worst.")
    with c1:
        source("attempts", extra="first attempts only")
    att = pd.DataFrame(ana["by_attempt"]).assign(attempt=lambda d: d.call_attempt_count.map(lambda x: "8+" if x >= 8 else str(x)))
    c2.altair_chart(bar(att, "attempt", "share_of_all_meetings", "2 · Share of all meetings by attempt number",
                        highlight=lambda r: r.attempt == "1"), width="stretch")
    c2.caption("68% of meetings come on the first call; attempts 6+ add almost nothing.")
    with c2:
        source("attempts")
    c3, c4 = st.columns(2)
    g = pd.DataFrame(ana["retry_gap"])
    c3.altair_chart(bar(g, "gap", "meeting_rate", "3 · Retry after no-answer: meeting rate by gap", fmt=".1%",
                        highlight=lambda r: r.gap in ("1-2h", "4-8h"), sort=list(g.gap)), width="stretch")
    c3.caption("Under 30 min is worst; 1–2 h and 4–8 h on the same day are best; the next day is about half.")
    with c3:
        source("attempts", extra="retries after a Not Answered")
    f = pd.DataFrame(ana["frustration_by_dials_24h"]).assign(dials=lambda d: d.dials_24h.map(lambda x: "5+" if x >= 5 else str(int(x))))
    c4.altair_chart(bar(f, "dials", "frustration_rate", "4 · Seller frustration vs dials in the previous 24 h", fmt=".1%",
                        color=RED), width="stretch")
    c4.caption("Frustration phrases ('baar baar call', 'kitni baar') triple as dials pile up.")
    with c4:
        source("turns", "attempts")
    c5, c6 = st.columns(2)
    s = pd.DataFrame(ana["speed_to_lead"])
    c5.altair_chart(bar(s, "delay", "meeting_rate", "5 · Speed to lead: first-call meeting rate by delay", fmt=".1%",
                        highlight=lambda r: r.delay == "<30s", sort=list(s.delay)), width="stretch")
    c5.caption("Calling within 30 seconds of the trigger converts best.")
    with c5:
        source("attempts", extra="lead_sent_time vs call_start_time, first attempts from 10 AM")
    if rep and "tiers" in rep:
        tr = pd.DataFrame(rep["tiers"]).melt("tier", ["share_dials", "share_meetings"], var_name="what", value_name="share")
        c6.altair_chart(alt.Chart(tr).mark_bar().encode(
            x=alt.X("tier:N", title=None), xOffset="what:N", y=alt.Y("share:Q", axis=alt.Axis(format="%"), title=None),
            color=alt.Color("what:N", scale=alt.Scale(range=[GREY, TEAL]), legend=alt.Legend(orient="top", title=None)),
            tooltip=["tier", "what", alt.Tooltip("share:Q", format=".1%")]).properties(title="6 · Lead tiers (Sept): share of dials vs meetings", height=230),
            width="stretch")
        c6.caption("Tier D uses 47% of dials for 15% of meetings: that's where the stop rule saves dials.")
        with c6:
            source("backtest", "model")
    st.divider()
    st.subheader("Conversation findings (12.8k transcripts)")
    st.markdown("""
| Signal | Effect on meetings |
|---|---|
| Opening matched to the lead type (paid-services interest → "paid services" hook) | **26.9% vs 7.9%** with the wrong hook |
| Specific numbers ("80 se zyada enquiry") vs vague "kuch zyada" | 26.3% vs 23.0% |
| Seller says busy | meetings halve (13% vs 24%) → offer two concrete callback times |
| Seller asks the price | buying signal: 37% vs 22% |
| "nahi" alone | **not a refusal** (in 54% of calls that fixed a meeting); real negatives: "interest nahi" 0.31×, "call mat karo" 0.37× |
""")
    source("turns", "bot_calls", extra="hook types matched to lead type (redis_bucket) from Call Attempts")


# ------------------------------------------------------------------ 3. best time + 15-minute rule
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def page_best_time():
    warm()
    from src import windows as win
    st.title("Best time to call & the 15-minute rule")
    st.markdown("##### When should VANI call a seller, and what should it do when the call isn't picked up?")

    # ---- A. when to call
    st.header("1 · When to call")
    hd = pd.DataFrame(ana["hour_dow_first_attempt"])
    hd["day"] = hd.dow.map(lambda d: DAY_NAMES[int(d)])
    hd["hour_label"] = hd.hour.astype(int).map(lambda h: f"{h}:00")
    c1, c2 = st.columns([1.35, 1])
    with c1:
        heat = alt.Chart(hd).mark_rect().encode(
            x=alt.X("hour_label:O", sort=[f"{h}:00" for h in range(9, 21)], title="hour of day"),
            y=alt.Y("day:O", sort=DAY_NAMES, title=None, axis=alt.Axis(labelOverlap=False)),
            color=alt.Color("meeting_rate:Q", scale=alt.Scale(scheme="oranges"), legend=alt.Legend(format="%", title="meeting rate")),
            tooltip=["day", "hour_label", alt.Tooltip("meeting_rate:Q", format=".1%"), alt.Tooltip("answer_rate:Q", format=".0%"), "dials"])
        txt = alt.Chart(hd).mark_text(fontSize=9).encode(
            x=alt.X("hour_label:O", sort=[f"{h}:00" for h in range(9, 21)]), y=alt.Y("day:O", sort=DAY_NAMES),
            text=alt.Text("meeting_rate:Q", format=".0%"),
            color=alt.condition(alt.datum.meeting_rate > 0.115, alt.value("white"), alt.value("#333")))
        st.altair_chart((heat + txt).properties(height=320, title="First calls: meeting rate by hour × day (Apr–Sep 2026)"),
                        width="stretch")
        source("attempts", extra="first attempts only, so retries don't distort the hours")
    with c2:
        st.markdown("""
**What the heatmap says**
- **Evening (6–9 PM) converts best** on every day of the week.
- **9–10 AM is the worst hour**: mostly the overnight backlog dialled at once.
- **Saturdays and Sundays** convert as well as weekdays, or better.
- The model uses this pattern plus each seller's segment and history to rank every slot (sidebar seller → section 3 below).""")
        bw = pd.DataFrame(ana["best_window_by_segment"])
        bw = bw[bw.value != "NA"]
        n_eve = int((bw.best_window == "18-21").sum())
        st.metric("Segments whose best window is 6–9 PM", f"{n_eve} of {len(bw)}")
        st.caption("The exceptions matter: **limited companies convert best 10 AM–12 PM**; a few categories too.")
    seg_type = st.radio("Best window by segment", sorted(bw.segment.unique()), horizontal=True, index=1)
    show = bw[bw.segment == seg_type].sort_values("first_calls", ascending=False)
    st.dataframe(show.rename(columns={"value": seg_type, "first_calls": "first calls", "best_window": "best window",
                                      "best_meeting_rate": "meeting rate (best)", "second_best": "2nd best",
                                      "worst_window": "worst window", "worst_meeting_rate": "meeting rate (worst)"})
                 .drop(columns="segment").style.format({"meeting rate (best)": "{:.1%}", "meeting rate (worst)": "{:.1%}"}),
                 width="stretch", hide_index=True)
    source("attempts", "sellers", extra="first attempts; windows with at least 300 calls")

    # ---- B. the 15-minute rule
    st.header("2 · The 15-minute rule")
    v1, v2 = st.columns(2)
    with v1:
        st.markdown(f"""
<div style="background:#F6E7E6;border-radius:10px;padding:16px 20px;height:100%">
<div style="font-size:0.85em;color:{RED};font-weight:600">TODAY</div>
<div style="font-size:1.3em;font-weight:700;margin:4px 0 8px">Redial after a fixed 15 minutes</div>
• Same gap for every seller, every time of day<br>• No limit on dials per day<br>• No reason to stop<br>
• A missed call at 7:38 PM means calls at 7:53, 8:08, 8:23…
</div>""", unsafe_allow_html=True)
    with v2:
        st.markdown(f"""
<div style="background:#E3F1F1;border-radius:10px;padding:16px 20px;height:100%">
<div style="font-size:0.85em;color:{TEAL};font-weight:600">OUR RECOMMENDATION: CHANGE</div>
<div style="font-size:1.3em;font-weight:700;margin:4px 0 8px">Retry by evidence, not by a fixed clock</div>
• <b>No redial within 30 minutes</b><br>• Retry <b>same day, 1–2 h or 4–8 h later</b>, in the seller's best-scored slot<br>
• <b>Max 3 dials per 24 h, 5 per lead</b>; stop when P(meeting) &lt; 1%<br>• Callback requested → call at that time
</div>""", unsafe_allow_html=True)
    st.write("")
    g = pd.DataFrame(ana["retry_gap"])
    g["kind"] = g.gap.map(lambda x: "fixed rule zone" if x == "<30m" else "recommended" if x in ("1-2h", "4-8h") else "other")
    ch = alt.Chart(g).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("gap:N", sort=list(g.gap), title="time between a missed call and the retry"),
        y=alt.Y("meeting_rate:Q", axis=alt.Axis(format="%"), title="meeting rate of the retry"),
        color=alt.Color("kind:N", scale=alt.Scale(domain=["fixed rule zone", "recommended", "other"], range=[RED, TEAL, "#B8C2CE"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["gap", alt.Tooltip("meeting_rate:Q", format=".2%"), alt.Tooltip("answer_rate:Q", format=".0%"), "dials"])
    lab = ch.mark_text(dy=-7, fontSize=10, color="#333").encode(text=alt.Text("meeting_rate:Q", format=".1%"))
    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.altair_chart((ch + lab).properties(height=280, title="Retries after a no-answer: how long to wait"), width="stretch")
        source("attempts", extra="all retries after a 'Not Answered', Apr–Sep 2026")
    with c2:
        if brief:
            seg = pd.DataFrame(brief["short_redial_by_segment"])
            seg = seg[(seg.segment == "business_type") & (seg.value != "NA")].pivot_table(index="value", columns="gap", values="meeting").dropna()
            st.markdown("**Short redials lose in every segment** (meeting rate of the retry)")
            st.dataframe(seg[[c for c in ["<30 min", "30-60 min", "1-2 h"] if c in seg.columns]].style.format("{:.1%}"),
                         width="stretch")
            source("brief", "attempts", "sellers")
        f = pd.DataFrame(ana["frustration_by_dials_24h"])
        st.markdown(f"**And repeated dials irritate:** frustration in transcripts goes from "
                    f"**{f.frustration_rate.iloc[0]:.1%}** (no dial in the last 24 h) to **{f.frustration_rate.iloc[-1]:.1%}** (5+ dials).")
        source("turns", "attempts")
    if rep:
        b, comb = rep["retry_stop"], rep["combined"]
        c0 = b["baseline"]["answered"] / b["baseline"]["dials"]
        st.markdown("**What changes on held-out September 2026** (replay of 124,779 real dials)")
        tbl = pd.DataFrame([
            {"": "Dials", "Current schedule": f"{b['baseline']['dials']:,}", "Our rules": f"{comb['dials']:,}",
             "Change": f"{comb['dials_vs_baseline_pct']}%"},
            {"": "Meetings fixed", "Current schedule": f"{b['baseline']['meetings']:,}", "Our rules": f"~{comb['estimated_meetings']:,.0f}",
             "Change": f"{comb['meetings_vs_baseline_pct']:+}% (est.)"},
            {"": "Calls per meeting", "Current schedule": f"{b['baseline']['calls_per_meeting']}", "Our rules": f"{comb['calls_per_meeting']}",
             "Change": f"{100 * (comb['calls_per_meeting'] / b['baseline']['calls_per_meeting'] - 1):+.0f}%"},
            {"": "Connect rate", "Current schedule": f"{c0:.1%}", "Our rules": f"{b['default']['connect_rate']:.1%}",
             "Change": f"{100 * (b['default']['connect_rate'] - c0):+.1f} pp"},
            {"": "Dials to sellers already called 3+ times in 24 h", "Current schedule": f"{b['baseline']['dials_with_3plus_in_24h']:,}",
             "Our rules": "0", "Change": "−100%"}])
        st.dataframe(tbl, width="stretch", hide_index=True)
        source("backtest", extra="stop + anti-irritation rules replayed on actual Sept sequences; re-timing is a model estimate")

    # ---- C. this seller
    st.header("3 · For the seller under test")
    if not glid:
        st.info("Pick a demo seller in the sidebar.")
        return
    st.caption(mask(f"GLID {glid}") + (f" · {scenario['scenario']}" if scenario else "") + f" · as of {at:%a %d %b %Y %H:%M}")
    grid, meta = win.full_week_grid(int(glid), at)
    c1, c2 = st.columns([1.35, 1])
    with c1:
        grid["hour_label"] = grid.hour.map(lambda h: f"{h}:00")
        hm = alt.Chart(grid).mark_rect().encode(
            x=alt.X("hour_label:O", sort=[f"{h}:00" for h in range(9, 21)], title="hour of day"),
            y=alt.Y("day:O", sort=DAY_NAMES, title=None, axis=alt.Axis(labelOverlap=False)),
            color=alt.Color("p_meeting:Q", scale=alt.Scale(scheme="blues"), legend=alt.Legend(format=".1%", title="P(meeting)")),
            tooltip=["window", alt.Tooltip("p_meeting:Q", format=".2%"), alt.Tooltip("p_answer:Q", format=".0%"), "rank"])
        top = grid[grid["rank"] <= 3]
        ring = alt.Chart(top).mark_rect(fill=None, stroke=AMBER, strokeWidth=3).encode(
            x=alt.X("hour_label:O", sort=[f"{h}:00" for h in range(9, 21)]), y=alt.Y("day:O", sort=DAY_NAMES))
        st.altair_chart((hm + ring).properties(height=300, title="This seller's best windows (orange = top 3)"), width="stretch")
        source("model", "attempts", "sellers", extra=f"confidence: {meta['confidence']} ({meta['past_dials']} past dials)")
    with c2:
        st.markdown("**Top windows**")
        st.dataframe(grid.head(5)[["rank", "window", "p_meeting", "p_answer"]].style.format({"p_meeting": "{:.2%}", "p_answer": "{:.0%}"}),
                     width="stretch", hide_index=True)
    comp = win.ladder_comparison(int(glid), at)
    st.markdown("**If this seller doesn't pick up: fixed 15-minute rule vs our retry ladder**")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"<span style='color:{RED};font-weight:600'>Fixed 15-minute rule</span>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(comp["fixed_15min"])[["attempt", "when", "hours_after_previous", "p_meeting"]]
                     .style.format({"p_meeting": "{:.2%}"}), width="stretch", hide_index=True)
    with c2:
        st.markdown(f"<span style='color:{TEAL};font-weight:600'>Our ladder</span>", unsafe_allow_html=True)
        ours = pd.DataFrame(comp["ours"])
        if len(ours):
            st.dataframe(ours[["attempt", "when", "hours_after_previous", "p_meeting"]].style.format({"p_meeting": "{:.2%}"}),
                         width="stretch", hide_index=True)
        else:
            st.caption("Our plan stops here (see the Demo sellers page for why).")
    ef, eo = comp["expected_meetings_fixed"], comp["expected_meetings_ours"]
    if ef and eo:
        k = st.columns(3)
        k[0].metric("Expected meetings, fixed rule", f"{ef:.3f}")
        k[1].metric("Expected meetings, our ladder", f"{eo:.3f}", f"{100 * (eo / ef - 1):+.0f}%")
        k[2].metric("Dials within the first hour", f"{sum(1 for s in comp['fixed_15min'])} vs "
                    f"{sum(1 for s in comp['ours'] if (s['hours_after_previous'] or 0) < 1)}")
    source("model", extra="same time-of-day model and retry-gap factor for both ladders; the factor for <30 min is "
                          "shrunk to 0.57× (raw data: 0.05×), so this comparison favours the fixed rule")


# ------------------------------------------------------------------ 4. predict for any GLID
def page_predict():
    warm()
    from src import predict as pr
    st.title("Predict the best time to call (live)")
    st.markdown("##### Enter any seller GLID: the planner reads that seller's history and computes the plan right now.")
    cat = pr.catalog()
    n_tr = int((cat.in_training == "trained (Apr-Aug)").sum())
    n_un = int((cat.in_training == "unseen (Sept only)").sum())
    k = st.columns(3)
    k[0].metric("Sellers in the data", f"{len(cat):,}")
    k[1].metric("Model trained on (Apr–Aug dials)", f"{n_tr:,}")
    k[2].metric("Never seen in training (Sept only)", f"{n_un:,}")
    source("attempts", "sellers", extra="training split: Apr–Aug 2026; September held out")

    left, right = st.columns([1, 1.25])
    with right:
        st.markdown("**Not sure which GLID? Pick one**")
        t1, t2 = st.tabs(["Suggestions", "Browse all sellers"])
        with t1:
            sug = pr.suggestions(4)
            kind = st.selectbox("Kind of seller", list(dict.fromkeys(sug.kind)), key="sug_kind")
            show = sug[sug.kind == kind].drop(columns="kind")
            ev = st.dataframe(show if not st.session_state.get("mask") else show.drop(columns=["category"]),
                              width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key="sug_tbl")
            if ev.selection.rows:
                st.session_state["predict_glid"] = int(show.iloc[ev.selection.rows[0]].glid)
            st.caption("Click a row to use that GLID.")
        with t2:
            f1, f2, f3 = st.columns(3)
            tr = f1.selectbox("Training", ["any", "trained (Apr-Aug)", "unseen (Sept only)"])
            stt = f2.selectbox("State", ["any"] + sorted(cat.state.unique()))
            bt = f3.selectbox("Business type", ["any"] + sorted(cat.business_type.unique()))
            f4, f5 = st.columns(2)
            mind = f4.slider("Min dials (Apr–Aug)", 0, 20, 0)
            mem = f5.checkbox("Only sellers with memory (Global Context)")
            q = cat
            if tr != "any":
                q = q[q.in_training == tr]
            if stt != "any":
                q = q[q.state == stt]
            if bt != "any":
                q = q[q.business_type == bt]
            q = q[q.dials_apr_aug >= mind]
            if mem:
                q = q[q.memory]
            st.caption(f"{len(q):,} sellers match; showing 100.")
            view = q.head(100)[["glid", "in_training", "dials_apr_aug", "dials_sept", "pickup_rate", "meetings", "state",
                                "business_type", "turnover", "category", "memory"]]
            ev2 = st.dataframe(view if not st.session_state.get("mask") else view.drop(columns=["category"]),
                               width="stretch", hide_index=True, height=300, on_select="rerun",
                               selection_mode="single-row", key="cat_tbl")
            if ev2.selection.rows:
                st.session_state["predict_glid"] = int(view.iloc[ev2.selection.rows[0]].glid)
        source("attempts", "sellers", "gc")
    with left:
        with st.form("predict_form"):
            g_in = st.number_input("Seller GLID", value=int(st.session_state.get("predict_glid", 0)), step=1)
            live = st.radio("Plan as of", ["Now (live clock)", "A past moment"], horizontal=True)
            c1, c2 = st.columns(2)
            d_ = c1.date_input("Date", value=datetime(2026, 9, 15).date())
            t_ = c2.time_input("Time", value=time(11, 0))
            go = st.form_submit_button("⚡ Predict best time to call", type="primary")
        if go and g_in:
            at_ = datetime.now().replace(second=0, microsecond=0) if live.startswith("Now") else datetime.combine(d_, t_)
            if int(g_in) not in pg._attempts_by_seller():
                st.session_state.pop("predict_result", None)
                st.error(f"GLID {g_in} is not in our data (no dials and no seller profile), so there is nothing to base a "
                         "prediction on. Pick a GLID from the lists on the right.")
                return
            try:
                st.session_state["predict_result"] = pr.predict(int(g_in), at_)
            except Exception as e:
                st.error(f"Could not predict for GLID {g_in}: {e}")
    r = st.session_state.get("predict_result")
    if not r:
        st.info("Enter a GLID (or pick one on the right) and press **Predict**.")
        return
    st.divider()
    o, w, c = r["out"], r["out"]["when"], r["catalog"]
    st.subheader(mask(f"GLID {r['glid']}", r["glid"], r["at"]) + f" · as of {r['at']:%a %d %b %Y %H:%M}")
    clean = lambda v: "-" if v is None or str(v) in ("nan", "NA", "None", "") else v
    st.caption(f"{c.get('in_training', 'not in data')} · dials Apr–Aug {c.get('dials_apr_aug', 0)} · Sept {c.get('dials_sept', 0)} · "
               f"pickup {clean(c.get('pickup_rate'))} · meetings {c.get('meetings', 0)} · {clean(c.get('state'))} · "
               f"{clean(c.get('business_type'))} · turnover {clean(c.get('turnover'))} · memory: {'yes' if c.get('memory') else 'no'}")
    slot = datetime.strptime(w["slot"], "%a %d %b %Y, %I:%M %p").strftime("%a %d %b, %H:%M") if w["slot"] else "—"
    kpi_row([("Next action", w["action"].upper(), None), ("When", slot, None),
             ("P(answer)", f"{w['p_answer']:.0%}" if w["p_answer"] is not None else "—", None),
             ("P(meeting)", f"{w['p_meeting']:.1%}" if w["p_meeting"] is not None else "—", None),
             ("Lead tier", o.get("tier") or "—", None),
             ("Computed in", f"{r['timing']['total_ms']:.0f} ms", None)], widths=[1, 1.7, 1, 1, 0.8, 1])
    st.info(f"**Why:** {w['reason']}")
    source("model", "attempts", "sellers", extra="history up to the 'as of' moment only")
    c1, c2 = st.columns([1.35, 1])
    with c1:
        grid = r["grid"].copy()
        grid["hour_label"] = grid.hour.map(lambda h: f"{h}:00")
        hm = alt.Chart(grid).mark_rect().encode(
            x=alt.X("hour_label:O", sort=[f"{h}:00" for h in range(9, 21)], title="hour of day"),
            y=alt.Y("day:O", sort=DAY_NAMES, title=None, axis=alt.Axis(labelOverlap=False)),
            color=alt.Color("p_meeting:Q", scale=alt.Scale(scheme="blues"), legend=alt.Legend(format=".1%", title="P(meeting)")),
            tooltip=["window", alt.Tooltip("p_meeting:Q", format=".2%"), alt.Tooltip("p_answer:Q", format=".0%"), "rank"])
        ring = alt.Chart(grid[grid["rank"] <= 3]).mark_rect(fill=None, stroke=AMBER, strokeWidth=3).encode(
            x=alt.X("hour_label:O", sort=[f"{h}:00" for h in range(9, 21)]), y=alt.Y("day:O", sort=DAY_NAMES))
        st.altair_chart((hm + ring).properties(height=300, title="Best weekly windows for this seller (orange = top 3)"),
                        width="stretch")
        st.caption(f"Confidence: {r['meta']['confidence']} ({r['meta']['past_dials']} past dials)")
    with c2:
        st.markdown("**Top 5 windows**")
        st.dataframe(grid.head(5)[["rank", "window", "p_meeting", "p_answer"]].style.format({"p_meeting": "{:.2%}", "p_answer": "{:.0%}"}),
                     width="stretch", hide_index=True)
        st.markdown("**If the call isn't answered: retry ladder**")
        lad = pd.DataFrame(r["ladder"]).reindex(columns=["attempt", "action", "when", "hours_after_previous", "p_meeting", "reason"])
        calls, stops = lad[lad.action == "CALL"], lad[lad.action == "STOP"]
        if len(calls):
            st.dataframe(calls.drop(columns=["action", "reason"]).rename(columns={"hours_after_previous": "hours after previous"})
                         .astype({"hours after previous": float, "p_meeting": float})
                         .style.format({"p_meeting": "{:.2%}", "hours after previous": "{:.1f}"}), width="stretch", hide_index=True)
            if len(stops):
                st.caption(f"Then stop: {stops.reason.iloc[0]}")
        else:
            st.warning(f"No calls planned: {lad.reason.iloc[0]}")
    h = r["history"]
    with st.expander(f"History used for this prediction ({len(h)} dials before {r['at']:%d %b %Y})"):
        if len(h):
            st.dataframe(h[["call_start_time", "call_attempt_count", "disposition_label", "lead_call_duration"]].tail(15)
                         .rename(columns={"call_start_time": "When", "call_attempt_count": "Attempt", "disposition_label": "Outcome",
                                          "lead_call_duration": "Talk (s)"}), width="stretch", hide_index=True)
        else:
            st.caption("No past dials: segment patterns only.")
        source("attempts")
    with st.expander("VANI prompt block for this seller"):
        st.code(mask(o["vani_prompt_block"], r["glid"], r["at"]), language="markdown")
        if o.get("seller_md"):
            st.markdown(mask(o["seller_md"], r["glid"], r["at"]))
    t = r["timing"]
    st.caption(f"Timing: history {t['history_ms']:.0f} ms · plan + prompt {t['plan_ms']:.0f} ms · weekly windows + retry ladder "
               f"{t['windows_ms']:.0f} ms · total {t['total_ms']:.0f} ms (data stays loaded in memory).")


# ------------------------------------------------------------------ 3. demo sellers
def page_demo():
    warm()
    st.title("Demo sellers")
    with st.expander("All demo sellers (each shows a different part of the system)", expanded=scenario is None):
        tbl = ds.demo_table()
        st.dataframe(tbl.drop(columns="GLID") if st.session_state.get("mask") else tbl, width="stretch", hide_index=True)
        source("attempts", extra="each seller is real; the 'as of' moment is a real point in their call history")
    if not glid:
        st.info("Pick a demo seller in the sidebar, or enter a custom GLID.")
        return
    try:
        out, plan = pg.generate(int(glid), at)
    except Exception as e:
        st.error(f"Could not build a plan for GLID {glid}: {e}")
        return
    hdr = mask(f"GLID {glid}") + (f" · {scenario['scenario']}" if scenario else "")
    st.subheader(hdr)
    st.caption(f"As of {at:%a %d %b %Y %H:%M} · attempt #{out['attempt_no']} · lead type {out['lead_type']} · "
               f"last outcome {out['last_disposition'] or '—'}")
    w = out["when"]
    slot = datetime.strptime(w["slot"], "%a %d %b %Y, %I:%M %p").strftime("%a %d %b, %H:%M") if w["slot"] else "—"
    kpi_row([("Next action", w["action"].upper(), None), ("When", slot, None),
             ("P(answer)", f"{w['p_answer']:.0%}" if w["p_answer"] is not None else "—", None),
             ("P(meeting)", f"{w['p_meeting']:.1%}" if w["p_meeting"] is not None else "—", None),
             ("Lead tier", out.get("tier") or "—", None)], widths=[1, 2, 1, 1, 1])
    st.info(f"**Why:** {w['reason']}")
    source("model", "attempts", extra="guardrails and gap curve from src/policy.py")

    t0_, t1, t2, t3, t4 = st.tabs(["Data sources", "History", "Plan & windows", "Before vs after", "Prompt & memory"])
    with t0_:
        st.markdown(mask(f"**GLID {glid}**") + " - every source file that holds data for this seller, and what it is used for:")
        st.dataframe(ds.source_inventory(glid, at), width="stretch", hide_index=True)
        st.caption("Counts for dated sources are shown up to the demo moment where possible; nothing after it is used for the plan.")
    with t1:
        h = ds.history(glid, at)
        prof = out["jinja_vars"]
        c1, c2 = st.columns([1, 2])
        with c1:
            p = pg.seller_context(glid, at)[1]
            st.markdown("**Profile**")
            source("sellers")
            st.markdown(f"- {p.get('seller_state')} · {p.get('business_type')}\n- {p.get('nature_of_business')}\n"
                        f"- {p.get('top_category_group')}\n- GST since {int(p['gst_registration_year']) if pd.notna(p.get('gst_registration_year')) else '—'}")
            before = h[h.period == "before"] if len(h) else h
            st.markdown("**Call history before this moment**")
            source("attempts")
            if len(before):
                st.markdown(f"- {len(before)} dials · picked up {(before.disposition_label != 'Not Answered').mean():.0%}\n"
                            f"- meetings fixed: {(before.disposition_label == 'Meeting Fixed').sum()}\n"
                            f"- last outcome: {before.disposition_label.iloc[-1]}")
            else:
                st.markdown("- **No past dials:** a new seller, so the plan relies on segment patterns.")
            for k in ("seller_frustrated", "already_with_exec", "dnc_requested"):
                if prof.get(k):
                    st.warning(k.replace("_", " "))
        with c2:
            if len(h):
                ch = alt.Chart(h).mark_circle(size=140, opacity=0.9).encode(
                    x=alt.X("call_start_time:T", title=None), y=alt.Y("hour:Q", title="hour of day", scale=alt.Scale(domain=[8, 21])),
                    color=alt.Color("disposition_label:N", scale=OUTCOME_COLORS, legend=alt.Legend(orient="bottom", title=None)),
                    shape=alt.Shape("period:N", scale=alt.Scale(domain=["before", "after"], range=["circle", "triangle"]), legend=None),
                    tooltip=[alt.Tooltip("call_start_time:T", format="%d %b %H:%M"), "call_attempt_count", "disposition_label",
                             "lead_call_duration", "period"])
                rule = alt.Chart(pd.DataFrame({"t": [at]})).mark_rule(color=AMBER, strokeDash=[4, 3], size=2).encode(x="t:T")
                st.altair_chart((ch + rule).properties(height=260, title="Every VANI dial (● before, ▲ after the demo moment)"),
                                width="stretch")
                source("attempts")
            ev = ds.channel_events(glid, at)
            if len(ev):
                ev = ev[ev.ts > pd.Timestamp(at) - pd.Timedelta(days=90)]
                cnt = ev.assign(week=ev.ts.dt.to_period("W").dt.start_time).groupby(["week", "channel"]).size().reset_index(name="events")
                cnt["week_label"] = cnt.week.dt.strftime("%d %b")
                cnt = cnt.astype({"channel": object, "week_label": object, "events": int})
                st.write("")
                st.altair_chart(alt.Chart(cnt).mark_bar().encode(
                    x=alt.X("week_label:N", sort=list(dict.fromkeys(cnt.sort_values("week").week_label)), title=None,
                            axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("events:Q", title="events / week"),
                    color=alt.Color("channel:N", legend=alt.Legend(orient="bottom", title=None))
                ).properties(height=240, title="Activity on other channels (last 90 days, Global Context)"), width="stretch")
                source("gc", extra="gc_enquiries_received, gc_buyer_calls_received, gc_whatsapp_*, gc_buyleads_bought, gc_executive_calls")
        if len(h):
            st.dataframe(h.assign(call_start_time=h.call_start_time.dt.strftime("%a %d %b %H:%M")).rename(columns={
                "call_start_time": "When", "call_attempt_count": "Attempt", "disposition_label": "Outcome",
                "lead_call_duration": "Talk (s)", "hour": "Hour", "redis_bucket": "Lead type", "period": "Before / after"}),
                width="stretch", hide_index=True, height=220)
            source("attempts")
    with t2:
        if not plan.ranked.empty:
            r = plan.ranked.copy()
            r["slot_label"] = r.slot.dt.strftime("%a %H:%M")
            r["status"] = r.allowed.map({True: "allowed", False: "blocked (guardrail)"})
            st.altair_chart(alt.Chart(r).mark_bar().encode(
                x=alt.X("slot_label:N", sort=None, title="Candidate slots, next 48 h"),
                y=alt.Y("score:Q", title="P(meeting) × retry-gap factor"),
                color=alt.Color("status:N", scale=alt.Scale(domain=["allowed", "blocked (guardrail)"], range=[NAVY, "#D5DAE1"]),
                                legend=alt.Legend(orient="top", title=None)),
                tooltip=["slot_label", alt.Tooltip("p_meeting:Q", format=".2%"), alt.Tooltip("p_answer:Q", format=".0%"),
                         alt.Tooltip("gap_factor:Q", format=".2f"), "blocked_reason"]).properties(height=250), width="stretch")
            source("model", extra="gap curve learned on Apr-Aug retries (models/gap_curve.json); guardrails in src/policy.py")
        from src import windows as win
        c1, c2 = st.columns([1, 1.3])
        wk, meta = win.weekly_windows(int(glid), at)
        c1.markdown(f"**Best weekly windows** · confidence: {meta['confidence']}")
        c1.dataframe(wk.assign(p_meeting=lambda d: d.p_meeting.map("{:.2%}".format),
                               p_answer=lambda d: d.p_answer.map("{:.0%}".format)), width="stretch", hide_index=True)
        c2.markdown("**Retry ladder if calls keep going unanswered**")
        c2.dataframe(pd.DataFrame(win.retry_ladder(int(glid), at)), width="stretch", hide_index=True)
        source("model", "attempts", extra="src/windows.py")
    with t3:
        actual, ours = ds.before_after(glid, at)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### What actually happened (current system)")
            if actual:
                st.dataframe(pd.DataFrame(actual), width="stretch", hide_index=True)
            else:
                st.caption("No further dials in the data.")
            source("attempts", extra="the dials that actually followed this moment")
        with c2:
            st.markdown("#### Our plan at the same moment")
            st.markdown(f"**{ours['action'].upper()}** {ours['when'] or ''}  \n{ours['reason']}")
            if ours["p_meeting"] is not None:
                st.markdown(f"P(answer) **{ours['p_answer']:.0%}** · P(meeting) **{ours['p_meeting']:.1%}** · tier **{ours['tier']}**")
            source("model", extra="history up to this moment only")
        st.caption("Single cases illustrate the logic; the measured effect over all of September is on the Results page.")
    with t4:
        if out.get("seller_md"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### seller.md: what VANI knows before it speaks")
                st.markdown(mask(out["seller_md"]))
                source("gc", "attempts")
            with c2:
                st.markdown("#### VANI prompt block (sent to Sarvam)")
                st.code(mask(out["vani_prompt_block"]), language="markdown")
                source("model", "persona", "gc", extra="evidence from ps07_call_turns.csv")
            with st.form("writeback"):
                st.markdown("**Simulate the end of a call:** VANI writes the result back and the plan updates at once.")
                a1, a2, a3 = st.columns([1, 1, 2])
                outcome = a1.selectbox("Outcome", ["Call Later / Busy", "Meeting Fixed", "Not Interested", "General (talked)"])
                cb = a2.time_input("Callback time", value=time(17, 0))
                summ = a3.text_input("Summary", "Seller was driving, asked to call back in the evening")
                if st.form_submit_button("Write back"):
                    sm.writeback(int(glid), at, outcome, summ, datetime.combine(at.date(), cb) if outcome.startswith("Call Later") else None)
                    st.rerun()
            if sm.WRITEBACK.exists() and st.button("Clear demo write-backs"):
                sm.WRITEBACK.unlink()
                st.rerun()
        else:
            st.caption("Outside the 5,000-seller Global Context sample: VANI uses the standard prompt (no seller.md).")
            st.code(mask(out["vani_prompt_block"]), language="markdown")
        st.markdown("#### Why each instruction")
        source("turns", "persona", "sellers", extra="each 'evidence' line below names the finding it comes from")
        for k, v in out["how"].items():
            st.markdown(f"**{k.replace('_', ' ').capitalize()}** – {mask(v['instruction'])}  \n<span style='color:{GREY}'>evidence: {v['reason']}</span>",
                        unsafe_allow_html=True)


# ------------------------------------------------------------------ 4. talk to VANI
def mask(text, g=None, at_=None):
    """Recording mode: hide seller-specific products, buyer cities, company and GLID on screen."""
    import re
    if not st.session_state.get("mask") or not isinstance(text, str):
        return text
    g, at_ = int(g or glid), at_ or at
    names = set()
    if sm.has_context(g):
        _, f = sm.build(g, at_)
        for key in ("enquiry_products_30d", "enquiry_cities_30d", "sourcing_products", "buylead_products"):
            names |= {re.sub(r" \(\d+\)$", "", x).strip() for x in (f.get(key) or "").split(", ") if x.strip()}
        names.add(str(f.get("city") or ""))
        prof = sm._profile().loc[g]
        names |= {str(prof.get(k)) for k in ("top_category_1", "top_category_2", "top_category_3", "company_name")}
    for n in sorted((n for n in names if n and n != "nan" and len(n) > 2), key=len, reverse=True):
        text = text.replace(n, "[hidden]")
    return re.sub(r"GLID \d+", "GLID ••••", text)


def page_talk():
    warm()
    from src import sarvam_live as sl
    st.title("Talk to VANI on Sarvam")
    if not glid:
        st.info("Pick a demo seller in the sidebar first.")
        return
    default_company = (scenario or {}).get("demo_company") or "Sharma Traders"
    if scenario is None and not st.session_state.get("mask") and sm.has_context(int(glid)):
        real = sm._profile().loc[int(glid)].get("company_name")
        default_company = real if isinstance(real, str) else default_company
    company = st.text_input("Company name VANI uses (demo sellers use the same made-up name as their Sarvam agent)",
                            value=default_company, key=f"company_{glid}")
    sess = sl.build_session(int(glid), at, company or None)
    w = sess["plan"]["when"]
    st.caption(mask(f"GLID {glid}") + f" · as of {at:%d %b %H:%M} · plan: {w['action'].upper()} {w['slot'] or ''} · "
               f"language {sess['language']} · pace {sess['pace']}")
    left, right = st.columns([1.1, 1])
    with right:
        st.markdown("**Try these as the seller**")
        exp = {"memory / hook": "Gives the real-number hook, asks for a time", "busy -> best times": "Stops and offers the 2 best windows",
               "'nahi' guard": "Does NOT end the call", "irritated": "Apologises once, offers a callback",
               "rushed": "Asks for the time directly", "confused": "Repeats in simpler words", "language switch": "Switches to English (and back)",
               "time capture": "Reads back '4 se 5 ke beech'", "identity": "Honest one-liner, then the ask",
               "refusal": "Thanks and ends politely", "do-not-call": "Apologises, ends, tags do_not_call"}
        st.dataframe(pd.DataFrame([{"you say": v, "VANI should": exp[k]} for k, v in sl.TEST_LINES]),
                     width="stretch", hide_index=True, height=420,
                     column_config={"you say": st.column_config.TextColumn(width="medium"),
                                    "VANI should": st.column_config.TextColumn(width="medium")})
        source("turns", extra="expected behaviour comes from the transcript findings (page 2)")
        with st.expander("Prompt block VANI receives"):
            st.code(mask(sess["variables"]["seller_block"]), language="markdown")
    with left:
        from src.vani_engine import VaniConversation, LLM_MODEL, STT_MODEL
        if not sarvam.available():
            st.warning("Set SARVAM_API_KEY before starting the dashboard (your sk_ key works).")
            return
        key = f"conv_{glid}_{at:%Y%m%d%H%M}_{company}"
        conv = st.session_state.get(key)
        b1, b2, b3 = st.columns([1.2, 1, 1])
        speak = b3.toggle("🔊 Speak replies", value=True)
        if b1.button("▶ Start conversation" if conv is None else "↺ Restart", type="primary"):
            conv = VaniConversation(sess, company or None)
            st.session_state[key] = conv
            st.session_state.pop("last_audio", None)
            if speak:
                try:
                    st.session_state["last_audio"] = conv.speak(sess["greeting"])
                except Exception as e:
                    st.error(f"Sarvam TTS failed: {e}")
        if conv is not None:
            b2.download_button("Save transcript", conv.transcript(), file_name=f"vani_conversation_{glid}.txt")

        def turn(text, stt_lang=None):
            try:
                with st.spinner("VANI is replying…"):
                    reply = conv.send(text, stt_lang)
                    if speak:
                        st.session_state["last_audio"] = conv.speak(reply)
            except Exception as e:
                st.session_state["turn_error"] = f"{type(e).__name__}: {e}"
            st.rerun()

        if st.session_state.get("turn_error"):
            st.error(st.session_state.pop("turn_error"))
        msgs = conv.messages if conv else [("VANI", sess["greeting"], sess["language"])]
        for who, text, lang in msgs:
            with st.chat_message("assistant" if who == "VANI" else "user", avatar="📞" if who == "VANI" else "🧑‍💼"):
                st.write(mask(text))
                if who == "SELLER":
                    st.caption(f"detected: {lang}")
        if st.session_state.get("last_audio"):
            st.audio(st.session_state.pop("last_audio"), format="audio/wav", autoplay=True)
        if conv is None:
            st.info("Press **▶ Start conversation**, then speak or type as the seller.")
        else:
            voice = st.audio_input("🎙 Speak as the seller (Hindi, Hinglish or English)", key=f"mic_{key}_{len(conv.messages)}")
            if voice is not None:
                try:
                    with st.spinner("Transcribing (Saaras)…"):
                        text, lang_code = VaniConversation.transcribe(voice.getvalue())
                except Exception as e:
                    st.error(f"Sarvam speech-to-text failed: {e}")
                    text = ""
                if text.strip():
                    turn(text, lang_code)
            qcols = st.columns(4)
            for i, (label, line) in enumerate(sl.TEST_LINES):
                if qcols[i % 4].button(label, key=f"q{i}"):
                    turn(line)
            said = st.chat_input("…or type as the seller")
            if said:
                turn(said)
            lat = sorted(conv.latency)
            st.caption(f"Median reply time {lat[len(lat) // 2]:.2f}s" if lat else "No replies yet"
                       + (f" · outcome tags: {', '.join(sorted(conv.tags))}" if conv.tags else ""))
        st.divider()
        st.markdown("#### 🔗 Test live on the Sarvam platform")
        agent_id = (scenario or {}).get("sarvam_agent_id")
        if agent_id:
            st.markdown(f"This seller has its own agent on Sarvam, pre-loaded with the same prompt "
                        f"(company **{scenario['demo_company']}**, this seller's hook, best times, language and pace).")
            st.code(f"{scenario['sarvam_agent_name']}\nAgent ID: {agent_id}", language=None)
            st.link_button("Open Sarvam (indus.sarvam.ai) ↗", "https://indus.sarvam.ai", type="secondary")
            st.caption("On Sarvam: **Build → Agents** → open the agent named above → **Test agent** → allow the microphone and "
                       "talk to VANI by voice. Same test lines as on the right.")
        elif scenario and scenario.get("scenario", "").startswith("Stop rule"):
            st.info("No Sarvam agent for this seller: our plan says **stop calling** (5 attempts reached), so there is no call to test.")
        else:
            st.markdown("Custom GLIDs run here on the Sarvam APIs above. To test one on the Sarvam platform, paste its prompt "
                        "(expander on the right) into an agent on [indus.sarvam.ai](https://indus.sarvam.ai) and use **Test agent**.")
        st.caption(f"Runs on Sarvam: speech-to-text {STT_MODEL} (language auto-detect) → LLM {LLM_MODEL} with the "
                   f"same VANI prompt as the Sarvam agents → text-to-speech bulbul:v3 at this seller's pace. "
                   f"Language is re-detected on every seller turn.")


# ------------------------------------------------------------------ 8. live GLID test (runtime)
@st.cache_resource
def voice_server():
    """Hands-free call server (src/voice_server.py), started once inside this process."""
    from src import voice_server as vs
    return vs.start()


@st.cache_resource
def sdk_bridge():
    """Bridge from the browser to Sarvam's Agents SDK runtime (src/sdk_bridge.py), started once."""
    from src import sdk_bridge as sb
    return sb.start()


def page_live():
    warm()
    from src import live_runtime as lr
    from src import sarvam_live as sl
    from src.vani_engine import VaniConversation, LLM_MODEL, STT_MODEL
    st.title("🧪 Live GLID test (runtime)")
    st.markdown("##### One GLID in → best time to call, seller memory, VANI prompt and a live conversation, "
                "all generated now. Nothing is pre-built per seller.")
    with st.form("live_form"):
        c1, c2, c3 = st.columns([1.2, 1.3, 1.5])
        g = c1.number_input("Seller GLID", value=int(st.session_state.get("live_glid", 2000059)), step=1)
        when = c2.radio("Plan as of", ["Now (live clock)", "A past moment"], horizontal=True)
        d_, t_ = c3.columns(2)
        dd = d_.date_input("Date", value=datetime(2026, 9, 18).date())
        tt = t_.time_input("Time", value=time(19, 38))
        comp = st.text_input("Company name VANI uses (blank = from seller data, else 'aapki company')", value="")
        go = st.form_submit_button("⚡ Generate everything now", type="primary")
    if go:
        if int(g) not in pg._attempts_by_seller():
            st.error(f"GLID {g} is not in our data (no dials, no profile). Try one from page 4's lists.")
            return
        at_ = datetime.now().replace(second=0, microsecond=0) if when.startswith("Now") else datetime.combine(dd, tt)
        with st.spinner("Generating plan, memory and prompt…"):
            st.session_state["live_res"] = lr.run(int(g), at_, comp.strip() or None)
        st.session_state["live_glid"] = int(g)
        st.session_state.pop("live_conv", None)
    r = st.session_state.get("live_res")
    if not r:
        st.info("Enter a GLID and press **Generate everything now**. Any of the 148,833 sellers works; "
                "page 4 lists trained and unseen sellers to try.")
        return
    p, o, w = r["predict"], r["predict"]["out"], r["predict"]["out"]["when"]
    c = p["catalog"]
    st.caption(mask(f"GLID {r['glid']}", r["glid"], r["at"]) + f" · as of {r['at']:%a %d %b %Y %H:%M} · "
               f"{c.get('in_training', '-')} · {c.get('state', '-')} · {c.get('business_type', '-')} · "
               f"memory: {'yes' if c.get('memory') else 'no'} · generated in {r['timing']['total_ms']} ms")
    t1, t2, t3, t4 = st.tabs(["⏰ Best time to call", "🧠 Memory & prompt", "🎙 Talk to VANI", "🔗 Test on Sarvam platform"])
    with t1:
        slot = datetime.strptime(w["slot"], "%a %d %b %Y, %I:%M %p").strftime("%a %d %b, %H:%M") if w["slot"] else "—"
        kpi_row([("Next action", w["action"].upper(), None), ("When", slot, None),
                 ("P(answer)", f"{w['p_answer']:.0%}" if w["p_answer"] is not None else "—", None),
                 ("P(meeting)", f"{w['p_meeting']:.1%}" if w["p_meeting"] is not None else "—", None),
                 ("Lead tier", o.get("tier") or "—", None)], widths=[1, 1.7, 1, 1, 0.8])
        st.info(f"**Why:** {w['reason']}")
        grid = p["grid"].copy()
        grid["hour_label"] = grid.hour.map(lambda h: f"{h}:00")
        a1, a2 = st.columns([1.35, 1])
        with a1:
            hm = alt.Chart(grid).mark_rect().encode(
                x=alt.X("hour_label:O", sort=[f"{h}:00" for h in range(9, 21)], title="hour of day"),
                y=alt.Y("day:O", sort=DAY_NAMES, title=None, axis=alt.Axis(labelOverlap=False)),
                color=alt.Color("p_meeting:Q", scale=alt.Scale(scheme="blues"), legend=alt.Legend(format=".1%", title="P(meeting)")),
                tooltip=["window", alt.Tooltip("p_meeting:Q", format=".2%"), alt.Tooltip("p_answer:Q", format=".0%")])
            ring = alt.Chart(grid[grid["rank"] <= 3]).mark_rect(fill=None, stroke=AMBER, strokeWidth=3).encode(
                x=alt.X("hour_label:O", sort=[f"{h}:00" for h in range(9, 21)]), y=alt.Y("day:O", sort=DAY_NAMES))
            st.altair_chart((hm + ring).properties(height=300, title="Best weekly windows (orange = top 3)"), width="stretch")
        with a2:
            st.markdown("**Top 5 windows**")
            st.dataframe(grid.head(5)[["rank", "window", "p_meeting", "p_answer"]].style.format({"p_meeting": "{:.2%}", "p_answer": "{:.0%}"}),
                         width="stretch", hide_index=True)
            lad = pd.DataFrame(p["ladder"]).reindex(columns=["attempt", "action", "when", "hours_after_previous", "p_meeting", "reason"])
            calls = lad[lad.action == "CALL"]
            st.markdown("**If not answered: retry ladder**")
            if len(calls):
                st.dataframe(calls[["attempt", "when", "hours_after_previous", "p_meeting"]].astype({"hours_after_previous": float, "p_meeting": float})
                             .style.format({"p_meeting": "{:.2%}", "hours_after_previous": "{:.1f}"}), width="stretch", hide_index=True)
            else:
                st.warning(f"No calls planned: {lad.reason.iloc[0]}")
        source("model", "attempts", "sellers", extra="computed now from history up to the 'as of' moment")
    with t2:
        b1, b2 = st.columns(2)
        with b1:
            st.markdown("**seller.md (generated now)**")
            if r["seller_md"]:
                st.markdown(mask(r["seller_md"], r["glid"], r["at"]))
                source("gc", "attempts")
            else:
                st.caption("Not in the 5,000-seller Global Context sample: no cross-channel memory, so the prompt uses "
                           "call history, profile and segment rules only.")
        with b2:
            st.markdown("**Seller block (this seller's part of the prompt)**")
            st.code(mask(r["sess"]["variables"]["seller_block"], r["glid"], r["at"]), language="markdown")
        with st.expander("Full prompt VANI runs on (base prompt + seller block)"):
            st.code(mask(r["full_prompt"], r["glid"], r["at"]), language="markdown")
        st.download_button("Download full prompt (.md)", r["full_prompt"], file_name=f"vani_prompt_{r['glid']}.md")
        source("persona", "sellers", "gc", extra="rules in src/prompt_gen.py; base prompt outputs/vani_agent_prompt_template.md")
    with t3:
        from src import sdk_bridge as sb
        from src import voice_server as vs
        modes = ["🟢 Sarvam live runtime (Agents SDK)", "🎧 Hands-free voice call", "⌨️ Push-to-talk & typing"]
        mode = st.radio("Mode", modes, index=0 if sb.available() else 1, horizontal=True,
                        key="live_mode", label_visibility="collapsed")
        key = (r["glid"], r["at"], r["company"])
        if st.session_state.get("live_voice_key") != key:
            st.session_state["live_voice_tok"] = vs.register(r["sess"], r["company"], r["glid"])
            st.session_state["live_voice_key"] = key
        tok = st.session_state["live_voice_tok"]
        host = (st.context.headers.get("host") or "localhost").split(":")[0]
        if mode == modes[0]:
            if not sb.available():
                st.warning("Sarvam's live runtime needs an **Agents API key** from indus.sarvam.ai "
                           "(the `sk_` developer key is refused by the agents runtime). Start the dashboard with "
                           "`SARVAM_AGENT_API_KEY=<key>` set, then reload. Until then use 🎧 Hands-free.")
            elif not sdk_bridge():
                st.error(f"Bridge port {sb.PORT} is busy. Free it and reload.")
            else:
                st.components.v1.html(sb.embed_html(tok, f"ws://{host}:{sb.PORT}"), height=560, scrolling=True)
                st.caption(f"Press **Start call** and talk naturally. This is Sarvam's own voice runtime (the same one as "
                           f"*Test agent*), running agent `{lr.LIVE_AGENT_ID}` with this seller's prompt passed in as "
                           f"variables at call time. The key stays on this machine. Mic needs **localhost**.")
        elif not sarvam.available():
            st.warning("Set SARVAM_API_KEY before starting the dashboard.")
        elif mode == modes[1]:
            if not voice_server():
                st.error(f"Voice server port {vs.PORT} is busy. Free it and reload.")
            else:
                api = f"http://{host}:{vs.PORT}"
                st.components.v1.html(vs.embed_html(tok, api), height=560, scrolling=True)
                st.caption(f"Press **Start call** and just talk, no buttons between turns. VANI hears when you stop, "
                           f"answers out loud, and stops if you talk over her. Mic needs **localhost**. "
                           f"[Open in its own tab]({api}/?t={tok}) · Runs on Sarvam: {STT_MODEL} → {LLM_MODEL} → bulbul:v3.")
        else:
            conv = st.session_state.get("live_conv")
            x1, x2, x3 = st.columns([1.2, 1, 1])
            spk = x3.toggle("🔊 Speak replies", value=True, key="live_speak")
            if x1.button("▶ Start conversation" if conv is None else "↺ Restart", type="primary", key="live_start"):
                conv = VaniConversation(r["sess"], r["company"])
                st.session_state["live_conv"] = conv
                if spk:
                    st.session_state["live_audio"] = conv.speak(r["sess"]["greeting"])
            if conv is not None:
                x2.download_button("Save transcript", conv.transcript(), file_name=f"vani_live_{r['glid']}.txt")

            def turn(text, lang=None):
                try:
                    with st.spinner("VANI is replying…"):
                        rep = conv.send(text, lang)
                        if spk:
                            st.session_state["live_audio"] = conv.speak(rep)
                except Exception as e:
                    st.session_state["live_err"] = f"{type(e).__name__}: {e}"
                st.rerun()

            if st.session_state.get("live_err"):
                st.error(st.session_state.pop("live_err"))
            for who, text, lang in (conv.messages if conv else [("VANI", r["sess"]["greeting"], r["sess"]["language"])]):
                with st.chat_message("assistant" if who == "VANI" else "user", avatar="📞" if who == "VANI" else "🧑‍💼"):
                    st.write(mask(text, r["glid"], r["at"]))
                    if who == "SELLER":
                        st.caption(f"detected: {lang}")
            if st.session_state.get("live_audio"):
                st.audio(st.session_state.pop("live_audio"), format="audio/wav", autoplay=True)
            if conv is None:
                st.info("Press **▶ Start conversation**, then speak or type as the seller.")
            else:
                v = st.audio_input("🎙 Speak as the seller", key=f"live_mic_{r['glid']}_{len(conv.messages)}")
                if v is not None:
                    try:
                        txt, code = VaniConversation.transcribe(v.getvalue())
                    except Exception as e:
                        st.error(f"Sarvam speech-to-text failed: {e}")
                        txt = ""
                    if txt.strip():
                        turn(txt, code)
                qc = st.columns(4)
                for i, (label, line) in enumerate(sl.TEST_LINES):
                    if qc[i % 4].button(label, key=f"live_q{i}"):
                        turn(line)
                said = st.chat_input("…or type as the seller", key="live_chat")
                if said:
                    turn(said)
            st.caption(f"Runs now on Sarvam: {STT_MODEL} speech-to-text → {LLM_MODEL} with this seller's prompt → bulbul:v3 voice.")
    with t4:
        st.markdown(f"**One agent on Sarvam for every GLID:** `{lr.LIVE_AGENT_NAME}` (ID `{lr.LIVE_AGENT_ID}`)")
        st.markdown("""
Sarvam does not offer an API to edit agents with our key, so the generated prompt is handed to that one agent:

1. Open **indus.sarvam.ai → Build → Agents → "VANI - Live runtime test (any GLID)" → Variables tab**.
2. Paste the **company name** and the **seller block** below into the two variables (`company_name`, `seller_block`) and save.
3. Click **Test agent** and talk to VANI by voice.

*Or ask Claude in the editor: "push GLID … to the live Sarvam agent" — it updates the agent through the Sarvam connector in seconds.*""")
        st.link_button("Open Sarvam (indus.sarvam.ai) ↗", "https://indus.sarvam.ai")
        st.markdown("`company_name`")
        st.code(r["company"], language=None)
        st.markdown("`seller_block`")
        st.code(r["sess"]["variables"]["seller_block"], language="markdown")
    st.caption(f"Timing: plan + windows {r['timing']['plan_and_windows_ms']} ms · prompt {r['timing']['prompt_ms']} ms · "
               f"total {r['timing']['total_ms']} ms")


# ------------------------------------------------------------------ 5. results
def page_results():
    st.title("Results & validation")
    b, comb, a = rep["retry_stop"], rep["combined"], rep["retiming"]
    t1, t2, t3, t4 = st.tabs(["Backtest (Sept)", "15-minute verdict", "Model & checks", "Global Context"])
    with t1:
        c0 = b["baseline"]["answered"] / b["baseline"]["dials"]
        kpi_row([("Dials", f"{comb['dials']:,}", f"{comb['dials_vs_baseline_pct']}%", "inverse"),
                 ("Meetings (est.)", f"{comb['estimated_meetings']:,.0f}", f"{comb['meetings_vs_baseline_pct']:+}%", "normal"),
                 ("Calls per meeting", comb["calls_per_meeting"], f"{comb['calls_per_meeting'] - comb['baseline_calls_per_meeting']:.2f}", "inverse"),
                 ("Connect rate", f"{b['default']['connect_rate']:.1%}", f"{100 * (b['default']['connect_rate'] - c0):+.1f} pp", "normal"),
                 ("Meetings at equal dials", f"+{a['lift_equal_dials_pct']}%", "model estimate")])
        source("backtest", extra="replay of 124,779 September dials from Call Attempts Apr-Sep 2026.csv")
        ev = a["empirical_validation"]
        rows = [dict(r, kind=k) for k in ("first attempt", "retry") for r in ev[k]]
        st.markdown("**Is the time-of-day signal real?** Calls that *happened* in the model's best slots vs its worst (actual September outcomes):")
        st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_bar(color=NAVY).encode(
            x=alt.X("quintile:N", title=None), y=alt.Y("meeting_rate:Q", axis=alt.Axis(format="%"), title="meeting rate"),
            column=alt.Column("kind:N", title=None), tooltip=["n", alt.Tooltip("meeting_rate:Q", format=".2%")]
        ).properties(width=330, height=200).resolve_scale(y="independent"))
        st.caption(f"Best vs worst fifth: first calls +{ev['first attempt Q5_vs_Q1_meeting_lift_pct']}% "
                   f"(95% CI {ev['first attempt Q5_vs_Q1_ci95'][0]} to {ev['first attempt Q5_vs_Q1_ci95'][1]}), retries "
                   f"+{ev['retry Q5_vs_Q1_meeting_lift_pct']}% (CI {ev['retry Q5_vs_Q1_ci95'][0]} to {ev['retry Q5_vs_Q1_ci95'][1]}).")
        source("backtest", "model")
        if brief:
            ip = brief["off_policy_ips"]
            st.markdown(f"**Off-policy check (inverse-propensity weighting):** moving retries to their best hour → "
                        f"**+{ip['lift_pct']}% meetings** (95% CI {ip['lift_ci95_pct'][0]} to {ip['lift_ci95_pct'][1]}).")
            source("brief")
        mix = pd.DataFrame({"actual": a["actual_hour_mix"], "recommended": a["recommended_hour_mix"]}).reset_index(names="hour")
        mix["hour"] = mix.hour.astype(int)
        st.altair_chart(alt.Chart(mix.melt("hour", var_name="schedule", value_name="share")).mark_bar().encode(
            x=alt.X("hour:O", sort="ascending", title="hour of day"), xOffset="schedule:N",
            y=alt.Y("share:Q", axis=alt.Axis(format="%"), title="share of dials"),
            color=alt.Color("schedule:N", scale=alt.Scale(range=[GREY, AMBER]), legend=alt.Legend(orient="top", title=None))
        ).properties(height=280, title="Where the dials go: actual vs recommended"), width="stretch")
        source("backtest")
        with st.expander("Stop-rule trade-off grid (48 settings)"):
            st.dataframe(pd.DataFrame(b["grid"]), width="stretch", hide_index=True)
            source("backtest")
    with t2:
        st.markdown("## Verdict: **CHANGE**")
        st.markdown("""
1. **No redial within 30 minutes.** Short redials fix 0–3% vs 3–5% at 30 min–2 h, in **every** segment.
2. **Retry on the same day, 1–2 h or 4–8 h later,** in the seller's best-scored slot (next day ≈ 0.5×).
3. **Max 3 dials per 24 h and 5 per lead;** stop when P(meeting) < 1%.
4. **Call Later = call at the asked time;** when busy, offer the seller's 2 best windows.""")
        if brief:
            seg = pd.DataFrame(brief["short_redial_by_segment"])
            seg = seg[seg.segment == "business_type"].pivot_table(index="value", columns="gap", values="meeting")
            st.markdown("**Meeting rate after a no-answer, by redial gap and business type**")
            st.dataframe(seg.style.format("{:.1%}"), width="stretch")
            source("brief", "attempts", "sellers")
        c = rep["rule_15min"]
        st.caption("All retries after a 'Not Answered', by hours since that dial")
        st.dataframe(pd.DataFrame(c["retry_after_not_answered_by_gap_hours"]), width="stretch", hide_index=True)
        source("backtest", "attempts")
        st.caption("Assumption to confirm with the organisers: the 15-minute redial happens inside one logged attempt "
                   "(dial-to-report times peak at ~7 and ~22 min); logged retries are 45+ min apart.")
    with t3:
        cmp_ = OUT_DIR / "model_comparison.csv"
        if cmp_.exists():
            st.markdown("**Model bake-off** (same features and split; ensemble in production)")
            cols = ["model", "meeting_auc", "meeting_logloss", "answer_auc", "slot_check_retry_Q5_vs_Q1_pct", "train_seconds"]
            st.dataframe(pd.read_csv(cmp_)[cols], width="stretch", hide_index=True)
            source("model", extra="outputs/model_comparison.csv (src/compare_models.py)")
        if brief:
            st.markdown("**Confidence vs amount of history** (new sellers fall back to segment patterns)")
            st.dataframe(pd.DataFrame(brief["confidence_by_history"]), width="stretch", hide_index=True)
            source("brief")
        lc = load_json("label_check.json")
        if lc:
            st.markdown(f"**Label check:** {lc['false_meeting_rate']:.1%} of evaluated meetings weren't real, flat by hour; "
                        f"AUC with the corrected label {lc['test_auc_clean_label']} (unchanged), hour ranking correlation "
                        f"{lc['hour_ranking_correlation']}.")
            source("evaluator", extra="outputs/label_check.json")
        m = mrep["meeting"]
        st.altair_chart(alt.Chart(pd.DataFrame(m["calibration"])).mark_line(point=True, color=NAVY).encode(
            x=alt.X("pred:Q", title="predicted P(meeting)"), y=alt.Y("obs:Q", title="observed")
        ).properties(height=220, width=380, title=f"Calibration on September (AUC {m['test_auc']})"))
        source("model")
    with t4:
        ge, gv = load_json("gc_eval.json"), load_json("gc_validation.json")
        if ge:
            kpi_row([("seller.md size", f"~{ge['compactness']['approx_tokens_median']} tokens", None),
                     ("Build time", f"{ge['build_ms_median']} ms", None),
                     ("Write-back → updated", f"{ge['freshness_ms_writeback_to_updated_file']} ms", None),
                     ("Real-number openings", f"{ge['coverage']['real_number_opening']:.0%}", None)])
        if gv:
            w3 = gv["warm_moment_within_seller_3h"]
            st.markdown(f"""
- **Warm moment (used):** active on another channel in the last 3 h → **{w3['answer_diff_pp']:+} pp pickup** within the same seller (95% CI {w3['answer_diff_ci95_pp'][0]} to {w3['answer_diff_ci95_pp'][1]}).
- **WhatsApp pushes:** no harm to pickup, so they don't count toward the irritation limit.
- **Executive spoke today:** too rare to test → cautious "skip today" rule.
- **Seller's usual activity hour:** no effect, so not used.""")
            source("gc_eval", "gc", "attempts")


{PAGES[0]: page_overview, PAGES[1]: page_analysis, PAGES[2]: page_best_time, PAGES[3]: page_predict,
 PAGES[4]: page_demo, PAGES[5]: page_talk, PAGES[6]: page_results, PAGES[7]: page_live}[page]()
st.sidebar.divider()
with st.sidebar.expander("📁 Data sources"):
    for k, (name, what) in ds.SOURCES.items():
        st.markdown(f"**{name}**  \n<span style='font-size:0.8em;color:{GREY}'>{what}</span>", unsafe_allow_html=True)
st.sidebar.caption("All data stays on this machine. Only the seller's prompt block goes to Sarvam during a live chat.")
