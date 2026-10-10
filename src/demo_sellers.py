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
