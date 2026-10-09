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
    (pg.PLAN_DIR / "INDEX.md").write_text("\n".join(idx) + "\n")


if __name__ == "__main__":
    main()
