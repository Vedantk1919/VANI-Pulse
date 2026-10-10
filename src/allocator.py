"""Batch allocator: assign a queue of leads to dial slots under hourly dialer capacity.

For every lead in the queue: build its candidate slots (next 48 h), score them in one batch
(time-of-day P(meeting) x retry-gap factor x warm-moment boost), drop slots that break the
anti-irritation guardrails, then fill hourly capacity greedily - leads with the most to gain
from their best slot go first. Each lead also gets a tier (A-D) from its predicted P(meeting)
per dial; cut points are learned on the training period (Apr-Aug), never on the test month.

Run:  python -m src.allocator          (fits tiers, then plans one September morning's queue)
"""
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .config import MODEL_DIR, OUT_DIR, TEST_START
from .model import TimingModel, load
from . import policy
from . import prompt_gen as pg
from . import seller_md as sm

TIER_QUANTILES = {"A": 0.90, "B": 0.70, "C": 0.40}      # A = top 10%, B = next 20%, C = next 30%, D = rest
TIER_FILE = MODEL_DIR / "tiers.json"


def fit_tiers(df=None, model=None):
    """Tier cut points from predicted P(meeting) on the training period."""
    df = load() if df is None else df
    model = model or TimingModel()
    tr = df[df.call_start_time < TEST_START]
    p = model.predict(tr).p_meeting.to_numpy()
    cuts = {k: float(np.quantile(p, q)) for k, q in TIER_QUANTILES.items()}
    json.dump(cuts, open(TIER_FILE, "w"), indent=2)
    return cuts


def tier_of(p, cuts):
    p = np.asarray(p)
    return np.select([p >= cuts["A"], p >= cuts["B"], p >= cuts["C"]], ["A", "B", "C"], "D")


def tier_report(te, p, cuts):
    """Share of dials and meetings per tier on held-out data."""
    t = pd.DataFrame({"tier": tier_of(p, cuts), "mf": te.mf.to_numpy()})
    r = t.groupby("tier").agg(dials=("mf", "size"), meetings=("mf", "sum"))
    r["share_dials"] = (r.dials / r.dials.sum()).round(3)
    r["share_meetings"] = (r.meetings / r.meetings.sum()).round(3)
    r["meeting_rate"] = (r.meetings / r.dials).round(4)
    return r.reset_index().to_dict("records")


def plan_queue(queue, now, capacity_per_hour, model=None):
    """queue: list of GLIDs due for a dial. Returns one row per lead with its assigned slot."""
    model = model or pg._model()
    cuts = json.load(open(TIER_FILE))
    t0 = time.perf_counter()
    cands, meta = [], {}
    for g in queue:
        hist, profile, persona = pg.seller_context(g, now)
        attempt_no, last_disp, callback, bucket = pg._episode_state(hist, now)
        signals = sm.timing_signals(g, now)
        stop = (persona.get("do_not_call_requested") == 1 or last_disp in ("Meeting Fixed", "Not Interested")
                or attempt_no > policy.MAX_ATTEMPTS)
        meta[g] = {"attempt_no": attempt_no, "last_disposition": last_disp, "callback": callback or signals.get("callback_at"),
                   "stop": stop}
        if stop:
            continue
        c = policy.build_candidates(hist, profile, now, attempt_no, now if attempt_no == 1 else None, str(bucket or "PUA"))
        c["glid"] = g
        c = policy.apply_guardrails(c, hist, attempt_no)
        c["_signals"] = [signals] * len(c)
        cands.append(c)
    t_build = time.perf_counter()
    C = pd.concat(cands, ignore_index=True)
    p = model.predict_slot(C)
    C["p_meeting"], C["p_answer"] = p.p_meeting.to_numpy(), p.p_answer.to_numpy()
    C["gap_factor"] = np.where(C.hrs_since_prev.isna(), 1.0, model.gap_factor(C.hrs_since_prev.fillna(0)))
    C["score"] = C.p_meeting * C.gap_factor
    C = pd.concat([policy.apply_context(g_.drop(columns="_signals"), now, g_["_signals"].iloc[0])
                   for _, g_ in C.groupby("glid", sort=False)], ignore_index=True)
    t_score = time.perf_counter()

    # greedy fill under hourly capacity: biggest gain between best and next-best slot goes first
    cap = defaultdict(lambda: capacity_per_hour)
    rows = []
    allowed = C[C.allowed]
    best = allowed.sort_values("score", ascending=False).groupby("glid")
    order = sorted(best.groups, key=lambda g: -best.get_group(g).score.iloc[0])
    for g in order:
        opts = best.get_group(g)
        m = meta[g]
        if m["callback"] is not None:
            slot = max(pd.Timestamp(m["callback"]) - timedelta(minutes=5), pd.Timestamp(now))
            rows.append({"glid": g, "slot": slot, "reason": "callback requested", "p_meeting": float(opts.p_meeting.iloc[0])})
            continue
        if m["attempt_no"] > 1 and opts.p_meeting.iloc[0] < policy.STOP_P_MEETING:
            rows.append({"glid": g, "slot": None, "reason": "stop: P(meeting) below 1%", "p_meeting": float(opts.p_meeting.iloc[0])})
            continue
        if m["attempt_no"] == 1:
            opts = opts.sort_values("slot")                    # fresh lead: earliest allowed slot (speed-to-lead)
        for _, o in opts.iterrows():
            key = (o.slot.date(), o.slot.hour)
            if cap[key] >= 1:
                cap[key] -= 1
                rows.append({"glid": g, "slot": o.slot, "reason": "warm moment" if o.get("warm") else
                             ("fresh lead - call now" if m["attempt_no"] == 1 else "best scored slot"),
                             "p_meeting": float(o.p_meeting)})
                break
        else:
            rows.append({"glid": g, "slot": None, "reason": "no capacity in 48 h", "p_meeting": float(opts.p_meeting.iloc[0])})
    for g, m in meta.items():
        if m["stop"]:
            rows.append({"glid": g, "slot": None, "reason": "stop: DNC / meeting fixed / not interested / 5 attempts",
                         "p_meeting": None})
    out = pd.DataFrame(rows)
    out["tier"] = np.where(out.p_meeting.notna(), tier_of(out.p_meeting.fillna(0), cuts), "-")
    t_end = time.perf_counter()
    timing = {"leads": len(queue), "build_ms_per_lead": round(1000 * (t_build - t0) / len(queue), 1),
              "score_ms_per_lead": round(1000 * (t_score - t_build) / len(queue), 1),
              "total_ms_per_lead": round(1000 * (t_end - t0) / len(queue), 1)}
    return out, timing


def main():
    df = load()
    model = TimingModel()
    cuts = fit_tiers(df, model)
    print("tier cut points (P(meeting) per dial):", {k: round(v, 4) for k, v in cuts.items()})
    # demo: every seller VANI dialled on the morning of 22 Sep, planned at 10:00 with capacity 60 dials/hour
    now = datetime(2026, 9, 22, 10, 0)
    a = pg._attempts()
    queue = a[(a.call_start_time >= now) & (a.call_start_time < now + timedelta(hours=1))].fk_glusr_usr_id.unique().tolist()[:300]
    pg._attempts_by_seller(); pg._persona(); sm._timeline(); sm._profile(); sm._vani_dials()   # warm caches (startup cost)
    plan, timing = plan_queue(queue, now, capacity_per_hour=60, model=model)
    print("timing:", timing)
    print(plan.reason.value_counts().to_dict())
    print(plan.tier.value_counts().sort_index().to_dict())
    plan.slot = pd.to_datetime(plan.slot)
    print(plan.dropna(subset=["slot"]).slot.dt.hour.value_counts().sort_index().to_dict())
    json.dump({"tier_cuts": cuts, "demo_queue": {"as_of": now.isoformat(), "capacity_per_hour": 60, **timing,
               "reasons": plan.reason.value_counts().to_dict(), "tiers": plan.tier.value_counts().to_dict()}},
              open(OUT_DIR / "allocator_report.json", "w"), indent=2, default=str)


if __name__ == "__main__":
    main()
