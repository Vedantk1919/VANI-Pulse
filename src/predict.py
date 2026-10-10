"""Real-time 'best time to call' for any seller GLID.

predict(glid, at)  -> everything the planner says about one seller at one moment, computed on the
                      spot (history up to `at` only), with the time it took.
catalog()          -> one row per seller: whether the model was trained on them (Apr-Aug dials),
                      how much history they have, and their segment - for picking GLIDs to try.

Run:  python -m src.predict <glid> [--at 2026-10-10T16:00]
"""
import argparse
import time
from datetime import datetime
from functools import lru_cache

import numpy as np
import pandas as pd

from .config import TEST_START, WORK_DIR
from . import prompt_gen as pg
from . import seller_md as sm
from . import windows as win

CATALOG = WORK_DIR / "seller_catalog.parquet"
SOUTH = {"Tamil Nadu", "Karnataka", "Kerala", "Andhra Pradesh", "Telangana", "Puducherry"}


def build_catalog():
    a = pd.read_parquet(WORK_DIR / "attempts_features.parquet",
                        columns=["fk_glusr_usr_id", "call_start_time", "ans", "mf", "seller_state", "business_type",
                                 "annual_turnover", "nature_of_business", "top_category_1", "top_category_group"])
    a["train"] = a.call_start_time < TEST_START
    g = a.groupby("fk_glusr_usr_id")
    c = pd.DataFrame({
        "dials_apr_aug": g.train.sum().astype(int),
        "dials_sept": (~a.train).groupby(a.fk_glusr_usr_id).sum().astype(int),
        "pickup_rate": g.ans.mean().round(2),
        "meetings": g.mf.sum().astype(int),
        "last_dial": g.call_start_time.max(),
        "state": g.seller_state.last(), "business_type": g.business_type.last(),
        "turnover": g.annual_turnover.last(), "nature": g.nature_of_business.last(),
        "category": g.top_category_1.last(), "category_group": g.top_category_group.last()})
    c["in_training"] = np.where(c.dials_apr_aug > 0, "trained (Apr-Aug)", "unseen (Sept only)")
    c["memory"] = c.index.isin(set(sm._profile().index))
    c = c.reset_index().rename(columns={"fk_glusr_usr_id": "glid"})
    for col in ("state", "business_type", "turnover", "nature", "category", "category_group"):
        c[col] = c[col].astype(str)
    c.to_parquet(CATALOG, index=False)
    return c


@lru_cache(maxsize=1)
def catalog():
    return pd.read_parquet(CATALOG) if CATALOG.exists() else build_catalog()


def suggestions(n=4, seed=7):
    """A few GLIDs per kind, so the demo shows contrasting cases."""
    c = catalog()
    rng = np.random.default_rng(seed)
    picks = {
        "Trained, long history (8+ dials)": c[(c.in_training.str.startswith("trained")) & (c.dials_apr_aug >= 8)],
        "Trained, has fixed a meeting before": c[(c.in_training.str.startswith("trained")) & (c.meetings > 0)],
        "Never seen in training (Sept only)": c[c.in_training.str.startswith("unseen")],
        "Has seller memory (Global Context)": c[c.memory & (c.dials_apr_aug > 0)],
        "Limited company": c[c.business_type == "Limited Company"],
        "South India (English first)": c[c.state.isin(SOUTH)],
    }
    rows = []
    for kind, d in picks.items():
        if len(d):
            for _, r in d.iloc[rng.choice(len(d), size=min(n, len(d)), replace=False)].iterrows():
                rows.append({"kind": kind, **r[["glid", "in_training", "dials_apr_aug", "dials_sept", "pickup_rate",
                                                 "meetings", "state", "business_type", "category"]].to_dict()})
    return pd.DataFrame(rows)


def predict(glid, at=None):
    """Run the whole planner for one seller now. Returns a dict plus timings in ms."""
    glid, at = int(glid), at or datetime.now().replace(second=0, microsecond=0)
    t = {}
    t0 = time.perf_counter()
    hist, profile, persona = pg.seller_context(glid, at)
    t["history_ms"] = (time.perf_counter() - t0) * 1000
    known = glid in pg._attempts_by_seller()
    t1 = time.perf_counter()
    out, plan = pg.generate(glid, at, write=False)
    t["plan_ms"] = (time.perf_counter() - t1) * 1000
    t2 = time.perf_counter()
    grid, meta = win.full_week_grid(glid, at)
    ladder = win.retry_ladder(glid, at)
    t["windows_ms"] = (time.perf_counter() - t2) * 1000
    t["total_ms"] = (time.perf_counter() - t0) * 1000
    c = catalog().set_index("glid")
    row = c.loc[glid].to_dict() if glid in c.index else {}
    return {"glid": glid, "at": at, "known": known, "catalog": row, "out": out, "plan": plan, "grid": grid,
            "meta": meta, "ladder": ladder, "history": hist, "timing": {k: round(v, 1) for k, v in t.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glid", type=int)
    ap.add_argument("--at", default=None, help="default: now")
    a = ap.parse_args()
    r = predict(a.glid, datetime.fromisoformat(a.at) if a.at else None)
    w = r["out"]["when"]
    print(f"GLID {r['glid']} as of {r['at']:%d %b %Y %H:%M} | {r['catalog'].get('in_training', 'not in data')}")
    print(f"NEXT: {w['action'].upper()} {w['slot'] or ''} | P(answer) {w['p_answer']} | P(meeting) {w['p_meeting']} | "
          f"tier {r['out'].get('tier')}\n  why: {w['reason']}")
    print("Top weekly windows:", ", ".join(r["grid"].head(3).window))
    for s in r["ladder"]:
        print("  ", s)
    print("timing ms:", r["timing"])


if __name__ == "__main__":
    main()
