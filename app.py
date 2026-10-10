"""VANI Best-Time-to-Call dashboard.   Run:  streamlit run app.py"""
import json
from datetime import datetime, time

import altair as alt
import pandas as pd
import streamlit as st

from src.config import OUT_DIR
from src import prompt_gen as pg
from src import sarvam
from src import seller_md as sm

st.set_page_config(page_title="VANI Best Time to Call", layout="wide")
st.title("VANI: Best Time to Call")
st.caption("When to call each seller, how to retry without irritating them, and how VANI should open the call. "
           "Trained Apr-Aug 2026, validated on held-out September 2026.")


@st.cache_data
def report():
    return json.load(open(OUT_DIR / "backtest_report.json"))


@st.cache_data
def model_report():
    return json.load(open(OUT_DIR / "model_report.json"))


@st.cache_resource
def warm():
    pg._attempts(); pg._persona(); pg._model()
    return True


rep, mrep = report(), model_report()
tab_plan, tab_bt, tab_rule, tab_gc, tab_model = st.tabs(
    ["Seller call plan", "Backtest (Sept)", "15-minute rule", "Global Context", "Model"])

# ---------------------------------------------------------------- seller plan
def render_plan():
    warm()
    c1, c2, c3 = st.columns([2, 2, 1])
    glid = c1.number_input("Seller GLID", value=0, step=1, help="Enter a seller GLID from the attempts data")
    d = c2.date_input("Plan as of (date)", value=datetime(2026, 9, 15).date())
    t = c3.time_input("time", value=time(11, 0))
    now = datetime.combine(d, t)
    if not glid:
        st.info("Enter a seller GLID to build their call plan (sample GLIDs: outputs/plans/INDEX.md after ./run_all.sh).")
        return
    try:
        out, plan = pg.generate(int(glid), now)
    except Exception as e:                                     # unknown GLID etc.
        st.error(f"Could not build a plan: {e}")
        return
    w = out["when"]
    k1, k2, k3, k4, k5 = st.columns(5)
    k5.metric("Lead tier", out.get("tier") or "-")
    k1.metric("Next action", w["action"].upper())
    k2.metric("Slot", w["slot"] or "-")
    k3.metric("P(answer)", f"{w['p_answer']:.0%}" if w["p_answer"] is not None else "-")
    k4.metric("P(meeting)", f"{w['p_meeting']:.1%}" if w["p_meeting"] is not None else "-")
    st.info(w["reason"])
    st.caption(f"Attempt #{out['attempt_no']} | lead type {out['lead_type']} | past dials {out['past_dials']} | "
               f"past answer rate {out['past_answer_rate']} | last outcome {out['last_disposition']}")

    if not plan.ranked.empty:
        r = plan.ranked.copy()
        r["slot_label"] = r.slot.dt.strftime("%a %H:%M")
        r["status"] = r.allowed.map({True: "allowed", False: "blocked (guardrail)"})
        ch = alt.Chart(r).mark_bar().encode(
            x=alt.X("slot_label:N", sort=None, title="Candidate slot (next 48h)"),
            y=alt.Y("score:Q", title="Score = P(meeting) x retry-gap factor"),
            color=alt.Color("status:N", scale=alt.Scale(domain=["allowed", "blocked (guardrail)"],
                                                         range=["#2a6fdb", "#c8c8c8"])),
            tooltip=["slot_label", alt.Tooltip("p_meeting:Q", format=".2%"), alt.Tooltip("p_answer:Q", format=".0%"),
                     alt.Tooltip("gap_factor:Q", format=".2f"), "blocked_reason"]).properties(height=260)
        st.altair_chart(ch, width="stretch")

    st.subheader("How VANI should talk to this seller")
    for k, v in out["how"].items():
        st.markdown(f"**{k.replace('_', ' ').capitalize()}**: {v['instruction']}  \n<span style='color:gray'>why: {v['reason']}</span>",
                    unsafe_allow_html=True)
    if out.get("seller_md"):
        st.subheader("Seller memory: seller.md (Global Context)")
        st.caption("What VANI knows before it speaks: built from enquiries, buyer calls, WhatsApp, buyleads, "
                   "past VANI and executive calls. No raw message text or phone numbers.")
        st.markdown(out["seller_md"])
        with st.form("writeback"):
            st.markdown("**Write back a call result** (VANI does this after every call; seller.md updates at once)")
            c1, c2 = st.columns(2)
            outcome = c1.selectbox("Outcome", ["Call Later / Busy", "Meeting Fixed", "Not Interested", "General (talked)"])
            cb = c2.time_input("Callback time (if Call Later)", value=time(17, 0))
            summary = st.text_input("One-line summary", "Seller was driving, asked to call back in the evening")
            if st.form_submit_button("Write back"):
                cb_at = datetime.combine(now.date(), cb) if outcome == "Call Later / Busy" else None
                sm.writeback(int(glid), now, outcome, summary, cb_at)
                st.rerun()
    elif glid:
        st.caption("This seller is outside the 5,000-seller Global Context sample, so VANI uses the standard prompt.")

    with st.expander("Production prompt: Jinja2 variables and rendered scheduler blocks"):
        st.caption("For the production VANI Jinja2 template: include templates/vani_scheduler_blocks.j2 and pass these variables.")
        st.json(out["jinja_vars"], expanded=False)
        st.code(pg.render_jinja(out["jinja_vars"]), language="markdown")

    st.subheader("Prompt block for VANI")
    st.code(out["vani_prompt_block"], language="markdown")
    st.download_button("Download plan (.md)", pg.to_markdown(out), file_name=f"plan_{glid}.md")

    st.subheader("Hear the opening (Sarvam Bulbul)")
    script = sarvam.opening_script(out)
    st.write(script)
    if sarvam.available():
        if st.button("Speak with this seller's pace"):
            try:
                st.audio(sarvam.tts(script, sarvam.language_from_design(out["how"]), sarvam.pace_from_design(out["how"])),
                         format="audio/wav")
            except Exception as e:
                st.error(f"Sarvam TTS failed: {e}")
    else:
        st.caption("Set SARVAM_API_KEY to play the audio.")


with tab_plan:
    render_plan()

# ---------------------------------------------------------------- backtest
with tab_bt:
    b, comb, a = rep["retry_stop"], rep["combined"], rep["retiming"]
    st.subheader("Policy vs current schedule on September 2026 (held out)")
    k = st.columns(4)
    k[0].metric("Dials", f"{comb['dials']:,}", f"{comb['dials_vs_baseline_pct']}%", delta_color="inverse")
    k[1].metric("Meetings (est.)", f"{comb['estimated_meetings']:,.0f}", f"{comb['meetings_vs_baseline_pct']:+}%")
    k[2].metric("Calls per meeting", comb["calls_per_meeting"], f"{comb['calls_per_meeting'] - comb['baseline_calls_per_meeting']:.2f}",
                delta_color="inverse")
    k[3].metric("Dials to sellers already called 3+ times in 24h", "0",
                f"-{b['baseline']['dials_with_3plus_in_24h']:,}", delta_color="inverse")
    st.markdown(f"""
* **Stop + anti-irritation rules** (replayed on actual Sept sequences, no model assumptions):
  {b['default']['dials_saved_pct']}% fewer dials, {b['default']['meetings_retained_pct']}% of meetings kept.
* **Re-timing retries** (model estimate, hourly dialer capacity respected): {a['lift_capacity_pct']:+}% meetings on the same dials.
* Combined: about {comb['meetings_vs_baseline_pct']:+}% meetings with {abs(comb['dials_vs_baseline_pct'])}% fewer dials.
  The {b['baseline']['dials'] - comb['dials']:,} freed dials can go to fresh leads (first attempts fix ~10%).""")

    st.markdown(f"**Same dials, better slots:** with exactly the dials actually made in each hour of September, re-timing "
                f"retries gives **{a.get('lift_equal_dials_pct', 0):+}% meetings** (model estimate).")
    if "tiers" in rep:
        st.subheader("Lead tiers (cut points learned on Apr-Aug, shown on September)")
        st.dataframe(pd.DataFrame(rep["tiers"]), width="stretch", hide_index=True)
        st.caption("Tier D uses almost half the dials for ~15% of meetings - this is where the stop rule saves dials.")

    st.subheader("Is the time-of-day signal real? (empirical check on actual Sept outcomes)")
    st.caption("Each Sept call is scored by how good its actual hour was vs the same call's average over all hours "
               "(seller effects cancel). If the model is right, the observed meeting rate rises across quintiles.")
    ev = a["empirical_validation"]
    rows = [dict(r, kind=kind) for kind in ("first attempt", "retry") for r in ev[kind]]
    ch = alt.Chart(pd.DataFrame(rows)).mark_bar().encode(
        x=alt.X("quintile:N", title="Model slot-quality quintile"), y=alt.Y("meeting_rate:Q", axis=alt.Axis(format="%")),
        column=alt.Column("kind:N", title=None), tooltip=["n", alt.Tooltip("meeting_rate:Q", format=".2%")]
    ).properties(width=300, height=220).resolve_scale(y="independent")
    st.altair_chart(ch)
    ci1, ci2 = ev.get("first attempt Q5_vs_Q1_ci95", ["?", "?"]), ev.get("retry Q5_vs_Q1_ci95", ["?", "?"])
    st.write(f"Best vs worst quintile: first attempts **{ev['first attempt Q5_vs_Q1_meeting_lift_pct']:+}%** "
             f"(95% CI {ci1[0]}% to {ci1[1]}%), retries **{ev['retry Q5_vs_Q1_meeting_lift_pct']:+}%** "
             f"(95% CI {ci2[0]}% to {ci2[1]}%) meeting rate.")

    st.subheader("Where dials go: actual vs recommended hour mix")
    mix = pd.DataFrame({"actual": a["actual_hour_mix"], "recommended": a["recommended_hour_mix"]}).reset_index(names="hour")
    mix = mix.melt("hour", var_name="schedule", value_name="share")
    st.altair_chart(alt.Chart(mix).mark_bar().encode(x="hour:O", xOffset="schedule:N", y=alt.Y("share:Q", axis=alt.Axis(format="%")),
                                                     color="schedule:N").properties(height=240), width="stretch")

    st.subheader("Stop-rule trade-off grid")
    g = pd.DataFrame(b["grid"])
    st.dataframe(g, width="stretch", hide_index=True)

# ---------------------------------------------------------------- global context
with tab_gc:
    st.subheader("Global Context: memory across channels, feeding the call plan")
    gv_path, ge_path = OUT_DIR / "gc_validation.json", OUT_DIR / "gc_eval.json"
    if ge_path.exists():
        ge = json.load(open(ge_path))
        k = st.columns(4)
        k[0].metric("seller.md size (median)", f"~{ge['compactness']['approx_tokens_median']} tokens")
        k[1].metric("Build time", f"{ge['build_ms_median']} ms")
        k[2].metric("Write-back -> updated file", f"{ge['freshness_ms_writeback_to_updated_file']} ms")
        k[3].metric("Openings with real numbers", f"{ge['coverage']['real_number_opening']:.0%}")
        st.caption("Lookback choice: share of sellers with activity, and of all events, inside each window")
        st.dataframe(pd.DataFrame(ge["lookback"]), width="stretch", hide_index=True)
    if gv_path.exists():
        gv = json.load(open(gv_path))
        st.subheader("Does other-channel activity change the best time to call?")
        w60, w3 = gv["warm_moment_within_seller_60min"], gv["warm_moment_within_seller_3h"]
        st.markdown(f"""
* **Warm moment - used.** Same seller, called within 3 h of activity on another channel vs not:
  **{w3['answer_diff_pp']:+} pp pickup** (95% CI {w3['answer_diff_ci95_pp'][0]} to {w3['answer_diff_ci95_pp'][1]}, {w3['sellers']} sellers).
  Within 60 min alone: {w60['answer_diff_pp']:+} pp (CI {w60['answer_diff_ci95_pp'][0]} to {w60['answer_diff_ci95_pp'][1]}) - not significant.
  The planner boosts slots inside the 3 h window by x1.08.
* **WhatsApp pushes - not counted as irritation.** Sellers with IndiaMART WhatsApp messages in the previous 24 h did not pick up less.
* **Executive spoke today - cautious rule.** Only {gv['exec_call_24h'][-1]['n'] if len(gv['exec_call_24h']) > 1 else 0} cases in the data, so untested; VANI skips that day.
* **Usual activity hour - not used.** Pickup is flat whether we call at the seller's usual hour or not.""")
        st.caption("Warm moment: raw and standardised rates by time since last activity")
        st.dataframe(pd.DataFrame(gv["warm_moment"]), width="stretch", hide_index=True)
    if WB := sm.WRITEBACK:
        if WB.exists() and st.button("Clear demo write-backs"):
            WB.unlink()
            st.rerun()

# ---------------------------------------------------------------- 15 min rule
with tab_rule:
    c = rep["rule_15min"]
    st.subheader("Recommendation: replace the fixed 15-minute redial")
    st.markdown("""
1. **No redial within 30 minutes.** Answered redials under 30 min fix meetings 2.5-3.2% of the time vs 11.5% at 1-2 h,
   and frustration ("baar baar call mat kijiye") rises with every extra dial in 24 h.
2. **Retry on the same day, 1-2 h or 4-8 h later, in the seller's best-scoring slot.** Next-day retries are worth about half.
3. **At most 3 dials per seller in any 24 h, at most 5 attempts per lead**, and stop early when P(meeting) < 1%.
4. **Call Later = call at the time the seller asked** (dial 5 min early). If the seller is busy, VANI offers two
   concrete times taken from this seller's best windows.
""")
    st.caption("Retries after a 'Not Answered', by hours since that dial (Apr-Sep)")
    st.dataframe(pd.DataFrame(c["retry_after_not_answered_by_gap_hours"]), width="stretch", hide_index=True)
    st.caption("Answered calls by how many times the seller was already dialled in the previous 24 h")
    st.dataframe(pd.DataFrame(c["answered_by_dials_in_prev_24h"]), width="stretch", hide_index=True)

# ---------------------------------------------------------------- model
with tab_model:
    st.caption(f"Production model: {mrep.get('model', 'ensemble')} (mean probability).")
    lc_path = OUT_DIR / "label_check.json"
    if lc_path.exists():
        lc = json.load(open(lc_path))
        st.subheader("Is the 'meeting fixed' label reliable?")
        st.write(f"The incorrect_mf evaluator re-read {lc['meetings_evaluated']:,} meeting calls: "
                 f"**{lc['false_meeting_rate']:.1%}** were not real meetings, at the same rate at every hour "
                 f"and attempt. With the corrected label the Sept AUC stays {lc['test_auc_clean_label']} "
                 f"and the hour ranking is unchanged (correlation {lc['hour_ranking_correlation']}).")
    cmp_path = OUT_DIR / "model_comparison.csv"
    if cmp_path.exists():
        st.subheader("Model bake-off (Sept 2026, same features and split)")
        st.dataframe(pd.read_csv(cmp_path), width="stretch", hide_index=True)
    for name in ("meeting", "answer"):
        m = mrep[name]
        st.subheader(f"P({name}) model")
        k = st.columns(4)
        k[0].metric("Test AUC (Sept)", m["test_auc"])
        k[1].metric("Base rate", f"{m['base_rate']:.1%}")
        k[2].metric("Top-decile rate", f"{m['top_decile_rate']:.1%}")
        k[3].metric("Bottom-decile rate", f"{m['bottom_decile_rate']:.1%}")
        cal = pd.DataFrame(m["calibration"])
        st.altair_chart(alt.Chart(cal).mark_line(point=True).encode(x=alt.X("pred:Q", title="predicted"),
                        y=alt.Y("obs:Q", title="observed")).properties(height=200, width=320))
        st.write("Top features (share of gain):", m["top_features"])
