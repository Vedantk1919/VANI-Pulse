"""seller.md - what VANI already knows about a seller before it speaks (Problem 2),
plus the timing signals that feed the call planner (Problem 3).

Lookback: counts over 90 days, a "new in the last 7 days" section, and the last 3
conversations whatever their age. The file is rebuilt from the timeline on demand (or when a
write-back event arrives), so it is always as fresh as the newest event.

Run:  python -m src.seller_md <glid> [YYYY-MM-DDTHH:MM]     (writes outputs/seller_md/<glid>.md)
"""
import json
import sys
from datetime import datetime, timedelta
from functools import lru_cache

import pandas as pd

from .config import OUT_DIR, WORK_DIR
from .timeline import TIMELINE, WRITEBACK, GC_DIR, scrub

MD_DIR = OUT_DIR / "seller_md"
MD_DIR.mkdir(parents=True, exist_ok=True)

LOOKBACK_DAYS = 90
NEW_DAYS = 7
WARM_HOURS = 3                 # within-seller test: +4.4 pp pickup if active in the last 3 h
WARM_FACTOR = 1.08             # 4.4 pp on a ~52% base ~ +8% relative


@lru_cache(maxsize=1)
def _timeline():
    t = pd.read_parquet(TIMELINE)
    return {g: d.reset_index(drop=True) for g, d in t.groupby("glid")}


@lru_cache(maxsize=1)
def _profile():
    p = pd.read_csv(GC_DIR / "gc_seller_profile.csv", low_memory=False)
    return p.drop_duplicates("fk_glusr_usr_id").set_index("fk_glusr_usr_id")


@lru_cache(maxsize=1)
def _vani_dials():
    a = pd.read_parquet(WORK_DIR / "attempts_features.parquet",
                        columns=["fk_glusr_usr_id", "call_start_time", "disposition_label", "lead_tbro_time"])
    return {g: d for g, d in a[a.fk_glusr_usr_id.isin(_profile().index)].groupby("fk_glusr_usr_id")}


def _writebacks(glid):
    if not WRITEBACK.exists():
        return pd.DataFrame()
    rows = [json.loads(x) for x in WRITEBACK.read_text().splitlines() if x.strip()]
    w = pd.DataFrame([r for r in rows if int(r["glid"]) == int(glid)])
    if w.empty:
        return w
    w["ts"] = pd.to_datetime(w.ts)
    return w


def has_context(glid):
    return int(glid) in _profile().index


def events(glid, now):
    t = _timeline().get(int(glid), pd.DataFrame(columns=["ts"]))
    w = _writebacks(glid)
    if not w.empty:
        t = pd.concat([t, w], ignore_index=True).sort_values("ts")
    return t[t.ts <= pd.Timestamp(now)]


def timing_signals(glid, now):
    """Signals the planner uses (validated in gc_validation.py)."""
    if not has_context(glid):
        return {}
    e = events(glid, now)
    act = e[e.by_seller == 1]
    mins = (pd.Timestamp(now) - act.ts.max()).total_seconds() / 60 if len(act) else None
    ex = e[(e.event == "exec_call_answered") & (e.ts > pd.Timestamp(now) - timedelta(hours=24))]
    cb = None
    wb = e[e.event == "vani_writeback"] if len(e) else e
    if len(wb) and isinstance(wb.iloc[-1].get("callback_at"), str):
        t_cb = pd.Timestamp(wb.iloc[-1].callback_at)
        cb = t_cb.to_pydatetime() if t_cb > pd.Timestamp(now) else None
    return {"mins_since_activity": mins, "callback_at": cb,
            "warm": mins is not None and mins <= WARM_HOURS * 60,
            "last_activity": act.iloc[-1].event if len(act) else None,
            "exec_answered_24h": len(ex) > 0}


def _top(s, n=3):
    s = s.dropna().astype(str)
    s = s[s.str.len() > 1]
    return ", ".join(f"{k} ({v})" for k, v in s.value_counts().head(n).items())


def _when(ts, now):
    d = (pd.Timestamp(now).normalize() - pd.Timestamp(ts).normalize()).days
    return "today" if d == 0 else "yesterday" if d == 1 else f"{d} days ago"


def build(glid, now=None, plan_windows=None):
    """Return (markdown, facts) for one seller as of `now`."""
    glid, now = int(glid), now or datetime(2026, 9, 30, 10, 0)
    if not has_context(glid):
        return None, {}
    p = _profile().loc[glid]
    e = events(glid, now)
    lb = e[e.ts > pd.Timestamp(now) - timedelta(days=LOOKBACK_DAYS)]
    new = e[e.ts > pd.Timestamp(now) - timedelta(days=NEW_DAYS)]
    m30 = e[e.ts > pd.Timestamp(now) - timedelta(days=30)]
    f = {"glid": glid, "as_of": pd.Timestamp(now).isoformat(), "company": p.get("company_name"),
         "city": p.get("seller_city"), "state": p.get("seller_state")}

    enq30 = m30[m30.event == "enquiry_received"]
    f["enquiries_30d"] = int(len(enq30))
    f["unread_enquiries_30d"] = int((enq30.value == 0).sum())
    f["enquiry_products_30d"] = _top(enq30["product"])
    f["enquiry_cities_30d"] = _top(enq30["city"])
    enq90 = lb[lb.event == "enquiry_received"]
    replied = lb[lb.event == "enquiry_replied"]
    f["enquiries_90d"] = int(len(enq90))
    f["reply_rate_90d"] = round(min(len(replied) / len(enq90), 1), 2) if len(enq90) else None
    bc = lb[lb.channel == "buyer_call"]
    f["buyer_calls_90d"] = int(len(bc))
    f["buyer_calls_missed_90d"] = int((bc.event == "buyer_call_missed").sum())
    f["buyer_calls_missed_7d"] = int((new.event == "buyer_call_missed").sum())
    f["buyleads_bought_90d"] = int((lb.event == "buylead_bought").sum())
    f["buylead_products"] = _top(lb[lb.event == "buylead_bought"]["product"], 2)
    f["sourcing_products"] = _top(lb[lb.event == "called_a_supplier"]["product"], 2)
    wa = lb[lb.channel == "whatsapp"]
    f["wa_seller_messages_90d"] = int(wa.event.isin(["wa_message_from_seller", "wa_chat"]).sum())
    pushes = wa[wa.event == "wa_push_from_indiamart"]
    f["wa_push_read_rate_90d"] = round((wa.event == "wa_push_read").sum() / len(pushes), 2) if len(pushes) else None

    # VANI history: every dial (attempts data) + answered-call summaries (timeline)
    d = _vani_dials().get(glid, pd.DataFrame(columns=["call_start_time", "disposition_label", "lead_tbro_time"]))
    d = d[d.call_start_time <= pd.Timestamp(now)]
    f["vani_dials_90d"] = int((d.call_start_time > pd.Timestamp(now) - timedelta(days=LOOKBACK_DAYS)).sum())
    f["vani_dials_24h"] = int((d.call_start_time > pd.Timestamp(now) - timedelta(hours=24)).sum())
    f["vani_answer_rate"] = round((d.disposition_label != "Not Answered").mean(), 2) if len(d) else None

    # open threads
    threads = []
    if len(d):
        last = d.iloc[-1]
        if last.disposition_label == "Call Later / Busy" and pd.notna(last.lead_tbro_time):
            when = "is due" if last.lead_tbro_time > pd.Timestamp(now) else "was due"
            threads.append(f"VANI promised a callback at {last.lead_tbro_time:%d %b %I:%M %p} ({when}) - "
                           f"seller was busy on {last.call_start_time:%d %b}.")
        if last.disposition_label == "Meeting Fixed" and pd.notna(last.lead_tbro_time) and last.lead_tbro_time > pd.Timestamp(now):
            threads.append(f"A meeting is already fixed for {last.lead_tbro_time:%d %b %I:%M %p} - confirm it, do not re-pitch.")
    cb = new[(new.event == "wa_chat") & (new.detail == "asked for a callback")]
    if len(cb):
        threads.append(f"Asked for a callback on WhatsApp {_when(cb.ts.max(), now)}.")
    wb = e[e.channel == "vani_writeback"] if "channel" in e else pd.DataFrame()
    if len(wb) and isinstance(wb.iloc[-1].get("callback_at"), str):
        threads.append(f"Seller asked to be called at {pd.Timestamp(wb.iloc[-1].callback_at):%d %b %I:%M %p} (last call).")
    ex = lb[lb.event == "exec_call_answered"]
    if len(ex) or p.get("already_in_touch_with_executive") == 1:
        when = f" ({_when(ex.ts.max(), now)}, {ex.iloc[-1].detail})" if len(ex) else ""
        threads.append(f"Already spoke to an IndiaMART executive{when} - offer the same executive, don't introduce a new one.")
    if f["unread_enquiries_30d"]:
        u = f["unread_enquiries_30d"]
        threads.append(f"{u} buyer {'enquiry' if u == 1 else 'enquiries'} from the last 30 days {'is' if u == 1 else 'are'} still unread.")
    if f["buyer_calls_missed_7d"]:
        k = f["buyer_calls_missed_7d"]
        threads.append(f"Missed {k} buyer {'call' if k == 1 else 'calls'} in the last 7 days.")
    f["open_threads"] = threads

    # last 3 conversations (any channel, seller actually engaged)
    conv = e[e.event.isin(["vani_call_answered", "exec_call_answered", "wa_chat", "vani_writeback"])].tail(12)
    lines = []
    for _, r in conv.iloc[::-1].iterrows():
        if r.event in ("vani_call_answered", "vani_writeback"):
            s = r.get("summary") or ""
            lines.append(f"[VANI call, {r.ts:%d %b}] {r.detail}: {scrub(s, 140)}")
        elif r.event == "exec_call_answered":
            lines.append(f"[Executive call, {r.ts:%d %b}] {r.detail}, {int(r.value or 0)} s")
        elif r.event == "wa_chat" and not any(x.startswith(f"[WhatsApp, {r.ts:%d %b}]") for x in lines):
            lines.append(f"[WhatsApp, {r.ts:%d %b}] {r.detail}")
        if len(lines) == 3:
            break
    f["last_conversations"] = lines

    sig = timing_signals(glid, now)
    f["timing_signals"] = sig
    f["signals"] = {k: p.get(k) for k in ("is_paid", "listing_status", "gst_verified_flag", "showed_frustration",
                                         "asked_if_talking_to_bot", "do_not_call_requested", "past_objections")}
    return to_markdown(f, p, plan_windows, now), f


def to_markdown(f, p, windows, now):
    paid = "paid" if p.get("is_paid") == 1 else "free"
    L = [f"# seller.md - {f['company']} (GLID {f['glid']})",
         f"_as of {pd.Timestamp(now):%d %b %Y %H:%M} | lookback {LOOKBACK_DAYS} days_", "",
         "## Who", f"- {f['city']}, {f['state']} | {p.get('business_type')} | {p.get('annual_turnover')} | "
                   f"{p.get('nature_of_business')} | {paid} listing",
         f"- Sells: {', '.join(str(x) for x in [p.get('top_category_1'), p.get('top_category_2'), p.get('top_category_3')] if pd.notna(x))}"]
    if f["sourcing_products"] or f["buylead_products"]:
        L.append(f"- Also buying / sourcing: {f['sourcing_products'] or f['buylead_products']}")
    L += ["", "## Open threads (act on these, don't re-ask)"]
    L += [f"- {x}" for x in f["open_threads"]] or ["- none"]
    L += ["", "## Business activity",
          f"- Enquiries: {f['enquiries_30d']} in 30 days ({f['unread_enquiries_30d']} unread), {f['enquiries_90d']} in 90 days"
          + (f"; replies to {f['reply_rate_90d']:.0%}" if f["reply_rate_90d"] is not None else ""),
          f"- Top enquiry products (30 d): {f['enquiry_products_30d'] or '-'} | buyer cities: {f['enquiry_cities_30d'] or '-'}",
          f"- Buyer calls (90 d): {f['buyer_calls_90d']} ({f['buyer_calls_missed_90d']} missed) | buyleads bought: {f['buyleads_bought_90d']}",
          f"- WhatsApp: {f['wa_seller_messages_90d']} seller messages in 90 days"
          + (f"; reads {f['wa_push_read_rate_90d']:.0%} of IndiaMART messages" if f["wa_push_read_rate_90d"] is not None else ""),
          "", "## Last conversations"]
    L += [f"- {x}" for x in f["last_conversations"]] or ["- none"]
    s, sig = f["signals"], f["timing_signals"]
    L += ["", "## Best time to call (from the timing model)",
          f"- VANI dials: {f['vani_dials_90d']} in 90 days, {f['vani_dials_24h']} in the last 24 h"
          + (f"; picks up {f['vani_answer_rate']:.0%} of dials" if f["vani_answer_rate"] is not None else "")]
    if windows:
        L.append("- Best windows: " + "; ".join(w["slot"] for w in windows[:3]))
    if sig.get("mins_since_activity") is not None:
        m = sig["mins_since_activity"]
        ago = f"{m:.0f} min" if m < 120 else f"{m / 60:.1f} h" if m < 48 * 60 else f"{m / 1440:.0f} days"
        L.append(f"- Last active on another channel: {ago} ago ({sig['last_activity'].replace('_', ' ')})"
                 + (" -> WARM: good moment to call" if sig["warm"] else ""))
    if sig.get("exec_answered_24h"):
        L.append("- An executive already spoke to this seller in the last 24 h -> do not dial VANI today")
    flags = [k for k in ("showed_frustration", "asked_if_talking_to_bot", "do_not_call_requested") if s.get(k) == 1]
    L += ["", "## Signals", f"- Flags: {', '.join(flags) or 'none'}"
          + (f" | past objections: {s['past_objections']}" if isinstance(s.get("past_objections"), str) else "")]
    return "\n".join(L) + "\n"


def personal_hook(f):
    """Opening hook with real numbers, or None if there is nothing concrete to say."""
    if f.get("enquiries_30d", 0) >= 2:
        prod = f["enquiry_products_30d"].split(" (")[0] if f["enquiry_products_30d"] else "aapke products"
        cities = ", ".join(c.split(" (")[0] for c in f["enquiry_cities_30d"].split(", ")[:2]) if f["enquiry_cities_30d"] else ""
        unread = f" - {f['unread_enquiries_30d']} abhi tak padhi nahi gayi" if f["unread_enquiries_30d"] else ""
        return (f"Pichhle 30 din mein {prod} ke liye aapko {f['enquiries_30d']} buyer enquiry aayi hain"
                + (f", zyada tar {cities} se" if cities else "") + f"{unread}. Hamare sales executive 15-20 minute mein "
                "dikha denge ki inhe order mein kaise badlein.")
    if f.get("buyer_calls_missed_90d", 0) >= 3:
        return (f"Pichhle 3 mahine mein {f['buyer_calls_missed_90d']} buyer calls miss ho gayi hain. Hamare sales executive "
                "15-20 minute mein batayenge ki koi buyer chhoote nahi.")
    return None


def writeback(glid, ts, outcome, summary="", callback_at=None):
    """VANI writes the call result back to the timeline (append-only)."""
    rec = {"glid": int(glid), "ts": pd.Timestamp(ts).isoformat(), "channel": "vani_writeback", "event": "vani_writeback",
           "by_seller": 0, "detail": outcome, "summary": scrub(summary, 200),
           "callback_at": pd.Timestamp(callback_at).isoformat() if callback_at else None}
    with open(WRITEBACK, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


if __name__ == "__main__":
    g = int(sys.argv[1]) if len(sys.argv) > 1 else int(_profile().index[0])
    now = datetime.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else None
    md, f = build(g, now)
    (MD_DIR / f"{g}.md").write_text(md)
    print(md)
    print("hook:", personal_hook(f))
