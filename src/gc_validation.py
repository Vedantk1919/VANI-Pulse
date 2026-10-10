"""Test whether Global Context signals should change *when* VANI calls (Problem 2 -> Problem 3).

  1. Warm moment     - is a seller more likely to pick up if they were active on another
                       channel (WhatsApp, enquiry read/reply, buyer call, buylead) shortly before?
  2. Cross-channel   - do IndiaMART contacts on other channels in the previous 24 h (executive
     contact load     calls, WhatsApp pushes) make VANI calls worse?
  3. Usual peak hour - does the seller's usual activity hour predict pickup?

Every comparison is shown three ways: raw, standardised by attempt number and past pickup rate,
and within the same seller (warm vs cold calls to the same person). Only signals that survive
the within-seller check are used by the planner.

Run:  python -m src.gc_validation      (writes outputs/gc_validation.json)
"""
import json

import numpy as np
import pandas as pd

from .config import WORK_DIR, OUT_DIR
from .timeline import TIMELINE

WARM_BINS = [-1, 15, 60, 180, 24 * 60, 7 * 24 * 60, 1e9]
WARM_LABELS = ["<15 min", "15-60 min", "1-3 h", "3-24 h", "1-7 days", ">7 days"]


def load():
    t = pd.read_parquet(TIMELINE)
    a = pd.read_parquet(WORK_DIR / "attempts_features.parquet",
                        columns=["fk_glusr_usr_id", "call_start_time", "ans", "mf", "ni", "hour",
                                 "call_attempt_count", "hist_ans_rate"])
    a = a[a.fk_glusr_usr_id.isin(t.glid.unique())].rename(columns={"fk_glusr_usr_id": "glid"})
    return t, a.sort_values("call_start_time").reset_index(drop=True)


def last_event_before(a, ev, name):
    """Minutes since the seller's latest event in `ev` strictly before each attempt."""
    ev = ev[["glid", "ts"]].sort_values("ts").rename(columns={"ts": name})
    m = pd.merge_asof(a[["glid", "call_start_time"]].reset_index(), ev, left_on="call_start_time",
                      right_on=name, by="glid", allow_exact_matches=False, direction="backward")
    return ((m.call_start_time - m[name]).dt.total_seconds() / 60).set_axis(m["index"]).sort_index()


def count_in_window(a, ev, hours=24):
    """How many events in `ev` fell in the `hours` before each attempt."""
    out = np.zeros(len(a), dtype=int)
    ev_by = {g: np.sort(d.ts.to_numpy()) for g, d in ev.groupby("glid")}
    for i, (g, t) in enumerate(zip(a.glid.to_numpy(), a.call_start_time.to_numpy())):
        arr = ev_by.get(g)
        if arr is not None:
            out[i] = np.searchsorted(arr, t) - np.searchsorted(arr, t - np.timedelta64(hours, "h"))
    return out


def compare(a, col, order):
    """Raw rates, rates standardised by attempt number x past-pickup band, and within-seller deltas."""
    a = a.copy()
    a["att"] = a.call_attempt_count.clip(upper=4)
    a["pband"] = pd.cut(a.hist_ans_rate.fillna(-1), [-2, -0.5, .25, .5, .75, 1.01], labels=False)
    w = a.groupby(["att", "pband"]).size() / len(a)
    rows = []
    for k in order:
        g = a[a[col] == k]
        if g.empty:
            continue
        cell = g.groupby(["att", "pband"]).agg(ans=("ans", "mean"), mf=("mf", "mean"))
        cw = w.reindex(cell.index).fillna(0)
        rows.append({"group": k, "n": int(len(g)), "answer": round(g.ans.mean(), 4), "meeting": round(g.mf.mean(), 4),
                     "not_interested": round(g.ni.mean(), 4),
                     "answer_std": round(float((cell.ans * cw).sum() / cw.sum()), 4),
                     "meeting_std": round(float((cell.mf * cw).sum() / cw.sum()), 4)})
    return rows


def within_seller(a, flag):
    """Sellers with both flagged and unflagged attempts: mean difference in answer / meeting rate."""
    g = a.groupby(["glid", flag]).agg(ans=("ans", "mean"), mf=("mf", "mean"), n=("ans", "size")).unstack(flag)
    g = g.dropna()
    if g.empty:
        return {"sellers": 0}
    d_ans = g[("ans", True)] - g[("ans", False)]
    d_mf = g[("mf", True)] - g[("mf", False)]
    rng = np.random.default_rng(7)
    boots = [d_ans.sample(len(d_ans), replace=True, random_state=rng.integers(1e9)).mean() for _ in range(1000)]
    return {"sellers": int(len(g)), "answer_diff_pp": round(100 * d_ans.mean(), 2),
            "answer_diff_ci95_pp": [round(100 * np.percentile(boots, 2.5), 2), round(100 * np.percentile(boots, 97.5), 2)],
            "meeting_diff_pp": round(100 * d_mf.mean(), 2)}


def main():
    t, a = load()
    rep = {"attempts_tested": int(len(a)), "sellers": int(a.glid.nunique())}

    # 1. warm moment
    act = t[t.by_seller == 1]
    a["mins_since_activity"] = last_event_before(a, act, "last_act")
    a["warm"] = pd.cut(a.mins_since_activity, WARM_BINS, labels=WARM_LABELS).astype(str).replace("nan", "no activity")
    rep["warm_moment"] = compare(a, "warm", WARM_LABELS + ["no activity"])
    a["warm_60"] = a.mins_since_activity <= 60
    a["warm_180"] = a.mins_since_activity <= 180
    rep["warm_moment_within_seller_60min"] = within_seller(a, "warm_60")
    rep["warm_moment_within_seller_3h"] = within_seller(a, "warm_180")

    # 2. cross-channel contact load in the previous 24 h
    a["exec_24h"] = count_in_window(a, t[t.channel == "executive"])
    a["wa_push_24h"] = count_in_window(a, t[t.event == "wa_push_from_indiamart"])
    exec_period = a[a.call_start_time >= "2026-08-01"]                      # exec data covers Aug-Sep only
    exec_period = exec_period.assign(exec_flag=np.where(exec_period.exec_24h > 0, "exec call in prev 24h", "none"))
    rep["exec_call_24h"] = compare(exec_period, "exec_flag", ["none", "exec call in prev 24h"])
    rep["exec_call_24h_within_seller"] = within_seller(exec_period.assign(f=exec_period.exec_24h > 0), "f")
    a["wa_flag"] = pd.cut(a.wa_push_24h, [-1, 0, 2, 1e9], labels=["0", "1-2", "3+"]).astype(str)
    rep["wa_push_24h"] = compare(a, "wa_flag", ["0", "1-2", "3+"])
    rep["wa_push_24h_within_seller"] = within_seller(a.assign(f=a.wa_push_24h > 0), "f")

    # 3. usual activity hour
    act_h = act[act.ts.dt.hour.between(9, 20)].assign(h=lambda d: d.ts.dt.hour)
    peak = act_h.groupby("glid").h.agg(lambda x: x.mode().iloc[0])
    n = act_h.groupby("glid").size()
    peak = peak[n >= 5]
    b = a[a.glid.isin(peak.index)].copy()
    b["dist"] = pd.cut((b.hour - b.glid.map(peak)).abs(), [-1, 0, 2, 12], labels=["at peak hour", "within 2 h", "3+ h away"]).astype(str)
    rep["usual_peak_hour"] = compare(b, "dist", ["at peak hour", "within 2 h", "3+ h away"])

    json.dump(rep, open(OUT_DIR / "gc_validation.json", "w"), indent=2, default=float)
    pd.set_option("display.width", 200)
    for k, v in rep.items():
        print(f"\n== {k}")
        print(pd.DataFrame(v).to_string(index=False) if isinstance(v, list) else v)


if __name__ == "__main__":
    main()
