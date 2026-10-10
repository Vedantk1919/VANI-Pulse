"""Curated demo sellers: one real seller per scenario, at a real moment from the data.

Each entry says what the demo should show. `history()` and `before_after()` give the seller's
call history and a comparison of what the current system actually did next vs our plan.
"""
import json
from datetime import datetime

import pandas as pd

from .config import ROOT
from . import prompt_gen as pg
from . import seller_md as sm

# The curated list holds real seller GLIDs, so it lives in data/ (git-ignored), not in the code.
# Format: [{"glid": int, "at": "YYYY-MM-DDTHH:MM", "scenario": str, "show": str}, ...]
DEMO_FILE = ROOT / "data" / "demo_sellers.json"
DEMO = json.load(open(DEMO_FILE)) if DEMO_FILE.exists() else []


def demo_table():
    rows = []
    for d in DEMO:
        rows.append({"GLID": d["glid"], "Scenario": d["scenario"], "As of": d["at"].replace("T", " "),
                     "Memory (seller.md)": "yes" if sm.has_context(d["glid"]) else "-", "What it shows": d["show"]})
    return pd.DataFrame(rows)


def history(glid, until=None):
    """Every VANI dial to this seller (optionally up to a moment)."""
    rows = pg._attempts_by_seller().get(int(glid))
    if rows is None:
        return pd.DataFrame(columns=["call_start_time", "call_attempt_count", "disposition_label", "lead_call_duration"])
    h = rows[["call_start_time", "call_attempt_count", "disposition_label", "lead_call_duration", "hour", "redis_bucket"]]
    if until is not None:
        h = h.assign(period=["before" if t < pd.Timestamp(until) else "after" for t in h.call_start_time])
    return h.reset_index(drop=True)


def channel_events(glid, until=None):
    """Other-channel activity (Global Context sellers only)."""
    if not sm.has_context(glid):
        return pd.DataFrame()
    e = sm._timeline().get(int(glid), pd.DataFrame())
    if until is not None and len(e):
        e = e[e.ts <= pd.Timestamp(until)]
    return e[["ts", "channel", "event", "by_seller"]].reset_index(drop=True) if len(e) else e


def before_after(glid, at):
    """What the current system actually did next (from the data) vs our plan at the same moment."""
    at = pd.Timestamp(at)
    h = history(glid)
    nxt = h[h.call_start_time > at].head(3)
    out, _ = pg.generate(int(glid), at.to_pydatetime(), write=False)
    w = out["when"]
    actual = [{"when": f"{r.call_start_time:%a %d %b %H:%M}", "hours_after": round((r.call_start_time - at).total_seconds() / 3600, 1),
               "attempt": int(r.call_attempt_count), "outcome": r.disposition_label} for r in nxt.itertuples()]
    ours = {"action": w["action"], "when": w["slot"], "reason": w["reason"],
            "p_meeting": w["p_meeting"], "p_answer": w["p_answer"], "tier": out.get("tier")}
    return actual, ours


def at_of(glid):
    for d in DEMO:
        if d["glid"] == int(glid):
            return datetime.fromisoformat(d["at"])
    return None


# ------------------------------------------------------------------ data sources
SOURCES = {
    "attempts": ("Best-Time-to-Call / Call Attempts Apr-Sep 2026.csv",
                 "every VANI dial: time, attempt no., outcome, duration (warehouse table data_hotlead_disposition_dtl)"),
    "sellers": ("Best-Time-to-Call / Sellers.csv",
                "profile: city, state, business type, turnover, nature of business, GST year, categories"),
    "persona": ("Persona Files / ps07_seller_files_part1-2.csv",
                "engagement history, past objections and questions, frustration / do-not-call flags"),
    "bot_calls": ("Persona Files / ps07_bot_calls_*.csv", "answered VANI calls with call summaries"),
    "turns": ("Persona Files / ps07_call_turns.csv", "turn-by-turn transcripts (12.8k calls)"),
    "evaluator": ("Persona Files / ps07_evaluator_outputs_*.csv", "incorrect_mf checks of 'meeting fixed' labels"),
    "gc": ("Global Context - Seller Dataset (gc_*.csv, 5,000 sellers)",
           "enquiries, enquiry replies, buyer calls, buyleads, WhatsApp, executive calls, seller profile"),
    "model": ("Our ensemble model (LightGBM + XGBoost + CatBoost, trained Apr-Aug 2026)",
              "P(answer), P(meeting) per slot; outputs/model_report.json"),
    "backtest": ("Our September 2026 backtest", "outputs/backtest_report.json"),
    "brief": ("Our brief checks (src/windows.py)", "outputs/brief_report.json"),
    "analysis": ("Our aggregates over the call attempts (src/analysis.py)", "outputs/analysis.json"),
    "gc_eval": ("Our Global Context tests (src/gc_validation.py, src/gc_eval.py)",
                "outputs/gc_validation.json, outputs/gc_eval.json"),
}
GC_FILES = {"enquiry_received": "gc_enquiries_received.csv", "enquiry_read": "gc_enquiries_received.csv",
            "enquiry_replied": "gc_enquiry_messages.csv", "buyer_call_answered": "gc_buyer_calls_received.csv",
            "buyer_call_missed": "gc_buyer_calls_received.csv", "buylead_bought": "gc_buyleads_bought.csv",
            "wa_message_from_seller": "gc_whatsapp_messages.csv", "wa_push_from_indiamart": "gc_whatsapp_messages.csv",
            "wa_push_read": "gc_whatsapp_messages.csv", "wa_chat": "gc_whatsapp_chatbot_conversations.csv",
            "called_a_supplier": "gc_buyer_call_extractions.csv", "spoke_to_a_buyer": "gc_buyer_call_extractions.csv",
            "vani_call_answered": "gc_bot_calls.csv", "exec_call_answered": "gc_executive_calls.csv",
            "exec_call_missed": "gc_executive_calls.csv"}


def _persona_counts():
    """Per-seller record counts in the persona call files (read once, ids only)."""
    from functools import lru_cache

    @lru_cache(maxsize=1)
    def load():
        import glob
        from .config import PERSONA_DIR
        bc = pd.concat(pd.read_csv(f, usecols=["fk_glusr_usr_id"]) for f in glob.glob(str(PERSONA_DIR / "ps07_bot_calls_*.csv")))
        tu = pd.read_csv(PERSONA_DIR / "ps07_call_turns.csv", usecols=["attempt_id", "fk_glusr_usr_id"]).drop_duplicates("attempt_id")
        return bc.fk_glusr_usr_id.value_counts().to_dict(), tu.fk_glusr_usr_id.value_counts().to_dict()
    return load()


def source_inventory(glid, at=None):
    """Which source files hold data for this seller, and how much (records up to `at` where dated)."""
    g = int(glid)
    rows = []
    h = history(g)
    n_before = int((h.call_start_time < pd.Timestamp(at)).sum()) if at is not None and len(h) else len(h)
    rows.append({"Source file": SOURCES["attempts"][0], "Used for": "call history, model features, before vs after",
                 "Records for this seller": f"{len(h)} dials ({n_before} before the demo moment)"})
    rows.append({"Source file": SOURCES["sellers"][0], "Used for": "profile and segment features (model)",
                 "Records for this seller": "1 profile row" if g in pg._attempts_by_seller() else "—"})
    p = pg._persona()
    rows.append({"Source file": SOURCES["persona"][0], "Used for": "tone, pace, objections, frustration / DNC flags",
                 "Records for this seller": "1 seller row" if g in p.index else "—"})
    bc, tu = _persona_counts()
    rows.append({"Source file": SOURCES["bot_calls"][0], "Used for": "answered-call summaries (context)",
                 "Records for this seller": f"{bc.get(g, 0)} answered calls"})
    rows.append({"Source file": SOURCES["turns"][0], "Used for": "conversation evidence (hooks, busy, 'nahi')",
                 "Records for this seller": f"{tu.get(g, 0)} transcribed calls"})
    if sm.has_context(g):
        e = sm._timeline().get(g, pd.DataFrame(columns=["event", "ts"]))
        if at is not None and len(e):
            e = e[e.ts <= pd.Timestamp(at)]
        counts = e.event.map(GC_FILES).value_counts()
        rows.append({"Source file": "Global Context / gc_seller_profile.csv", "Used for": "company, KYC / paid status (seller.md)",
                     "Records for this seller": "1 profile row"})
        for f, n in counts.items():
            rows.append({"Source file": f"Global Context / {f}", "Used for": "seller.md, warm moment, executive rule",
                         "Records for this seller": f"{n} events"})
    else:
        rows.append({"Source file": SOURCES["gc"][0], "Used for": "seller.md memory",
                     "Records for this seller": "not in the 5,000-seller sample"})
    rows.append({"Source file": SOURCES["model"][0], "Used for": "slot scores, tier, P(answer), P(meeting)",
                 "Records for this seller": "computed live"})
    return pd.DataFrame(rows)
