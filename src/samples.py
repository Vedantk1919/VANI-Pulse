"""Generate sample call plans for contrasting sellers at real September moments.

Run:  python -m src.samples      (writes outputs/plans/*.md|json and outputs/plans/INDEX.md)
"""
from datetime import timedelta

import pandas as pd

from . import prompt_gen as pg

SCENARIOS = [
    ("Limited company, retry after Not Answered", lambda a: (a.business_type == "Limited Company") & (a.disposition_label == "Not Answered") & (a.call_attempt_count == 1), 20),
    ("Small new proprietor (GST 2023+), retry after Not Answered", lambda a: (a.business_type == "Proprietorship") & (a.gst_registration_year >= 2023) & (a.turnover_ord == 0) & (a.disposition_label == "Not Answered") & (a.call_attempt_count == 1), 20),
    ("South India seller, retry after Not Answered", lambda a: a.seller_state.isin(["Tamil Nadu", "Karnataka", "Telangana"]) & (a.disposition_label == "Not Answered") & (a.call_attempt_count == 1), 20),
    ("Seller asked to call later", lambda a: (a.disposition_label == "Call Later / Busy") & a.lead_tbro_time.notna() & (a.lead_tbro_time > a.call_start_time + pd.Timedelta(hours=2)), 10),
    ("Already dialled 3 times today", lambda a: (a.dials_today == 2) & (a.disposition_label == "Not Answered") & (a.call_attempt_count == 3), 35),
    ("Attempt 5 not answered (stop rule)", lambda a: (a.call_attempt_count == 5) & (a.disposition_label == "Not Answered"), 20),
]


def _first_match(cands, test, limit=400):
    for glid, now in cands[:limit]:
        o, _ = pg.generate(glid, now, write=False)
        if test(o):
            return glid, now
    return None


def gc_scenarios():
    """Global Context moments where the new rules apply: a warm seller in an active retry,
    and a seller an executive spoke to today."""
    t = pd.read_parquet(pg.sm.TIMELINE)
    a = pg._attempts()
    na = a[(a.call_start_time >= "2026-08-01") & (a.disposition_label == "Not Answered")][["fk_glusr_usr_id", "call_start_time"]]
    na = na.rename(columns={"fk_glusr_usr_id": "glid", "call_start_time": "dial"})
    out = []
    act = t[(t.by_seller == 1) & t.event.isin(["wa_message_from_seller", "wa_chat", "enquiry_read", "buyer_call_answered"])]
    m = act.merge(na, on="glid")
    m = m[(m.ts > m.dial + pd.Timedelta(minutes=30)) & (m.ts < m.dial + pd.Timedelta(hours=6)) & m.ts.dt.hour.between(10, 16)]
    cands = [(int(r.glid), (r.ts + timedelta(minutes=20)).to_pydatetime()) for r in m.drop_duplicates("glid").itertuples()]
    hit = _first_match(cands, lambda o: "warm moment" in (o["when"]["reason"] or ""))
    if hit:
        out.append(("Global Context: missed VANI earlier, active on another channel 20 min ago (warm moment)", *hit))
    ex = t[t.event == "exec_call_answered"].merge(na, on="glid")
    ex = ex[(ex.ts > ex.dial) & (ex.ts < ex.dial + pd.Timedelta(hours=24)) & ex.ts.dt.hour.between(10, 15)]
    cands = [(int(r.glid), (r.ts + timedelta(hours=1)).to_pydatetime()) for r in ex.drop_duplicates("glid").itertuples()]
    hit = _first_match(cands, lambda o: "executive already spoke" in (o["when"]["reason"] or ""))
    if hit:
        out.append(("Global Context: executive spoke to the seller 1 h ago", *hit))
    return out


def main():
    a = pg._attempts()
    a = a[a.call_start_time >= "2026-09-05"]
    idx = ["# Sample call plans (September 2026 moments)", ""]
    for name, cond, mins in SCENARIOS:
        r = a[cond(a)].iloc[3]
        now = (r.call_start_time + timedelta(minutes=mins)).to_pydatetime()
        o, _ = pg.generate(int(r.fk_glusr_usr_id), now)
        w = o["when"]
        idx.append(f"- **{name}** - GLID {o['glid']} as of {now:%d %b %H:%M}: **{w['action'].upper()}** "
                   f"{w['slot'] or ''} - {w['reason']} -> [{o['glid']}.md]({o['glid']}.md)")
        print(idx[-1][:220])
    for name, glid, now in gc_scenarios():
        o, _ = pg.generate(glid, now)
        w = o["when"]
        idx.append(f"- **{name}** - GLID {glid} as of {now:%d %b %H:%M}: **{w['action'].upper()}** "
                   f"{w['slot'] or ''} - {w['reason']} -> [{glid}.md]({glid}.md), seller.md in ../seller_md/{glid}.md")
        print(idx[-1][:260])
    (pg.PLAN_DIR / "INDEX.md").write_text("\n".join(idx) + "\n")


if __name__ == "__main__":
    main()
