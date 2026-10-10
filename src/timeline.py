"""Global Context: one event timeline per seller GLID across every channel.

Sources (Global Context seller dataset, 5,000 sellers, Apr-Oct 2026) stand in for the
production APIs. Each source becomes rows of:

    glid, ts, channel, event, by_seller (1 = seller-initiated activity), detail, product, city, value

Free text is never copied: enquiry replies and chat messages contain phone numbers and names.
Only products, cities, intents, counts and VANI call outcomes are kept; VANI call summaries
are scrubbed of digits before use.

Run:  python -m src.timeline        (writes data/work/gc_timeline.parquet)
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT, WORK_DIR

GC_DIR = Path(__import__("os").environ.get("BTC_GC_DIR", ROOT / "data" / "gc"))
TIMELINE = WORK_DIR / "gc_timeline.parquet"
WRITEBACK = WORK_DIR / "gc_writeback.jsonl"        # events written back by VANI after a call

# WhatsApp chatbot intents -> readable labels (seller-side meaning)
INTENT_LABELS = {
    "Msite_BL": "posted a buy requirement", "Msite_BL_Quantity": "posted a buy requirement",
    "Msite_BL_Spec": "posted a buy requirement", "Msite_BL|Free_FLOW": "posted a buy requirement",
    "WA_Call_Feedback": "gave call feedback", "WA_Callback_Connect_Q": "asked for a callback",
    "WA_Callback_Pick_Seller_Q": "asked for a callback", "update_company_details": "asked to update company details",
    "Delete BuyLead": "deleted a buy requirement", "Buy_Product": "looked to buy a product",
    "no_call_nudge_ccs_seller": "got a 'missed calls' nudge",
}


def _read(name, **kw):
    return pd.read_csv(GC_DIR / name, low_memory=False, **kw)


def scrub(text, n=160):
    """Short, digit-free text: phone numbers, amounts and ids are removed."""
    if not isinstance(text, str):
        return ""
    t = re.sub(r"\d", "#", text)
    t = re.sub(r"#{3,}", "###", t)
    return (t[: n - 1] + "…") if len(t) > n else t


def build():
    ev = []

    e = _read("gc_enquiries_received.csv", parse_dates=["enquiry_date", "first_read_date"])
    ev.append(pd.DataFrame({"glid": e.seller_glid, "ts": e.enquiry_date, "channel": "enquiry",
                            "event": "enquiry_received", "by_seller": 0, "product": e.product_name,
                            "city": e.buyer_city, "value": (e.first_read_date.notna()).astype(int)}))
    r = e[e.first_read_date.notna()]
    ev.append(pd.DataFrame({"glid": r.seller_glid, "ts": r.first_read_date, "channel": "enquiry",
                            "event": "enquiry_read", "by_seller": 1, "product": r.product_name, "city": r.buyer_city}))

    m = _read("gc_enquiry_messages.csv", parse_dates=["reply_date"])
    m = m[m.message_from == "seller"]
    ev.append(pd.DataFrame({"glid": m.seller_glid, "ts": m.reply_date, "channel": "enquiry",
                            "event": "enquiry_replied", "by_seller": 1}))

    b = _read("gc_buyer_calls_received.csv", parse_dates=["call_datetime"])
    conn = (b.call_status == "Connected").astype(int)
    ev.append(pd.DataFrame({"glid": b.seller_glid, "ts": b.call_datetime, "channel": "buyer_call",
                            "event": np.where(conn == 1, "buyer_call_answered", "buyer_call_missed"),
                            "by_seller": conn, "city": b.caller_circle, "value": b.talk_sec}))

    bl = _read("gc_buyleads_bought.csv", parse_dates=["purchase_date"])
    kw = bl.keyword.astype(str).str.split("_").str[0].replace("nan", np.nan)
    ev.append(pd.DataFrame({"glid": bl.seller_glid, "ts": bl.purchase_date, "channel": "buylead",
                            "event": "buylead_bought", "by_seller": 1, "product": kw, "value": bl.credits_used}))

    w = _read("gc_whatsapp_messages.csv", parse_dates=["sent_at", "read_at"])
    u = w[w.message_sender == "USER"]
    ev.append(pd.DataFrame({"glid": u.glid, "ts": u.sent_at, "channel": "whatsapp",
                            "event": "wa_message_from_seller", "by_seller": 1}))
    o = w[w.message_sender == "API"]
    ev.append(pd.DataFrame({"glid": o.glid, "ts": o.sent_at, "channel": "whatsapp",
                            "event": "wa_push_from_indiamart", "by_seller": 0, "detail": o.campaign_name}))
    rd = o[o.read_at.notna()]
    ev.append(pd.DataFrame({"glid": rd.glid, "ts": rd.read_at, "channel": "whatsapp",
                            "event": "wa_push_read", "by_seller": 1}))

    c = _read("gc_whatsapp_chatbot_conversations.csv", parse_dates=["entry_date"])
    c = c[c.action_type.isin(["typed", "clicked", "pre-filled", "image/jpeg", "document", "DOCUMENT", "pdf", "video"])]
    ev.append(pd.DataFrame({"glid": c.glid, "ts": c.entry_date, "channel": "whatsapp",
                            "event": "wa_chat", "by_seller": 1,
                            "detail": c.intent.map(INTENT_LABELS).fillna("chatted with the WhatsApp bot")}))

    x = _read("gc_buyer_call_extractions.csv", parse_dates=["call_date"])
    ev.append(pd.DataFrame({"glid": x.glid, "ts": x.call_date, "channel": "pns_call",
                            "event": np.where(x.seller_role_on_call == "BUYER", "called_a_supplier", "spoke_to_a_buyer"),
                            "by_seller": 1, "product": x.products_discussed}))

    v = _read("gc_bot_calls.csv", parse_dates=["call_start_time"])
    ev.append(pd.DataFrame({"glid": v.fk_glusr_usr_id, "ts": v.call_start_time, "channel": "vani",
                            "event": "vani_call_answered", "by_seller": 0, "detail": v.disposition_label,
                            "value": v.lead_call_duration, "summary": v.lead_call_summary.map(scrub)}))

    xc = _read("gc_executive_calls.csv", parse_dates=["call_start_time"])
    ev.append(pd.DataFrame({"glid": xc.fk_glusr_usr_id, "ts": xc.call_start_time, "channel": "executive",
                            "event": np.where(xc.status == "Answered", "exec_call_answered", "exec_call_missed"),
                            "by_seller": 0, "value": xc.call_duration_customer, "detail": xc.module}))

    t = pd.concat(ev, ignore_index=True)
    for col in ("detail", "product", "city", "summary"):
        if col not in t:
            t[col] = None
        t[col] = t[col].astype("string")
    t["value"] = pd.to_numeric(t["value"], errors="coerce")
    t = t.dropna(subset=["glid", "ts"])
    t["glid"] = t.glid.astype("int64")
    t = t.sort_values(["glid", "ts"]).reset_index(drop=True)
    t.to_parquet(TIMELINE, index=False)
    print("timeline:", t.shape, "sellers:", t.glid.nunique())
    print(t.groupby(["channel", "event"]).agg(events=("glid", "size"), sellers=("glid", "nunique")))
    return t


if __name__ == "__main__":
    build()
