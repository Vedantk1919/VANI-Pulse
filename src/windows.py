"""Problem-3 brief outputs that the planner alone does not give.

  weekly_windows(glid)   ranked hour x day-of-week windows with a score (brief 3.1)
  retry_ladder(glid)     the full retry plan if calls keep going unanswered (brief 3.2)
  confidence by history  model accuracy and window stability vs amount of history (FAQ Q5)
  off-policy check       inverse-propensity estimate of the re-timed schedule (brief 3.5)
  15-min by segment      does the short-redial evidence differ by segment? (keep/change/supplement)

Run:  python -m src.windows            (writes outputs/brief_report.json)
      python -m src.windows <glid>     (prints that seller's weekly windows and retry ladder)
"""
import json
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from .config import CALL_HOURS, OUT_DIR, TEST_START, band_of
from . import policy
from . import prompt_gen as pg

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def weekly_windows(glid, at=None, top=10):
    """Score every hour x weekday for this seller's next attempt (time-of-day score)."""
    at = at or datetime.fromisoformat(TEST_START)
    hist, profile, _ = pg.seller_context(glid, at)
    attempt_no, *_ = pg._episode_state(hist, at)
    monday = (at - timedelta(days=at.weekday())).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=7)
    c = policy.build_candidates(hist, profile, monday, attempt_no, days=6)
    c = c[c.slot >= monday]
    p = pg._model().predict_slot(c)
    c["p_meeting"], c["p_answer"] = p.p_meeting.to_numpy(), p.p_answer.to_numpy()
    c["day"] = c.slot.dt.dayofweek.map(lambda d: DAYS[d])
    t = c[["day", "hour", "p_meeting", "p_answer"]].sort_values("p_meeting", ascending=False).reset_index(drop=True)
    t["window"] = t.day + " " + t.hour.map(lambda h: f"{h:02d}:00-{h + 1:02d}:00")
    t["rank"] = np.arange(1, len(t) + 1)
    n_hist = len(hist)
    conf = "low (segment pattern)" if n_hist == 0 else "medium" if n_hist < 5 else "high"
    return t.head(top)[["rank", "window", "p_meeting", "p_answer"]], {"past_dials": n_hist, "confidence": conf,
                                                                      "attempt_no": attempt_no}


def retry_ladder(glid, at=None, max_steps=policy.MAX_ATTEMPTS):
    """Plan attempt by attempt, assuming each call goes unanswered (brief 3.2)."""
    at = at or datetime.fromisoformat(TEST_START)
    hist, profile, persona = pg.seller_context(glid, at)
    attempt_no, last_disp, callback, bucket = pg._episode_state(hist, at)
    h = hist.copy()
    now, steps = at, []
    while attempt_no <= max_steps:
        plan = policy.plan_next_call(pg._model(), h, profile, now, attempt_no, lead_sent=now if attempt_no == 1 else None,
                                     bucket=str(bucket or "PUA"), callback_at=callback, last_disposition=last_disp,
                                     do_not_call=persona.get("do_not_call_requested") == 1)
        if plan.action == "stop":
            steps.append({"attempt": attempt_no, "action": "STOP", "reason": plan.reason})
            break
        gap = (plan.slot - now).total_seconds() / 3600
        steps.append({"attempt": attempt_no, "action": "CALL", "when": plan.slot.strftime("%a %d %b %H:%M"),
                      "hours_after_previous": round(gap, 1), "p_meeting": round(plan.p_meeting, 4),
                      "p_answer": round(plan.p_answer, 3), "reason": plan.reason})
        # pretend it was not answered: append a Not Answered dial and continue
        fake = h.iloc[-1:].copy() if len(h) else pg._attempts().iloc[:1].copy()
        fake["call_start_time"] = pd.Timestamp(plan.slot)
        fake["disposition_label"], fake["ans"], fake["mf"], fake["ni"], fake["cb"] = "Not Answered", 0, 0, 0, 0
        fake["call_attempt_count"], fake["band"] = attempt_no, band_of(plan.slot.hour)
        h = pd.concat([h, fake], ignore_index=True)
        now, attempt_no, last_disp, callback = plan.slot + timedelta(minutes=1), attempt_no + 1, "Not Answered", None
    else:
        steps.append({"attempt": attempt_no, "action": "STOP", "reason": f"{policy.MAX_ATTEMPTS} attempts reached"})
    return steps


def confidence_by_history(te, p):
    """FAQ Q5: model quality by how much history a seller has at the time of the call."""
    te = te.assign(p=p, hb=pd.cut(te.hist_n, [-1, 0, 2, 5, 1e9], labels=["0 (new)", "1-2", "3-5", "6+"]))
    rows = []
    for k, g in te.groupby("hb", observed=True):
        rows.append({"past_dials": str(k), "attempts": int(len(g)), "meeting_rate": round(g.mf.mean(), 4),
                     "auc": round(roc_auc_score(g.mf, g.p), 4) if g.mf.nunique() > 1 else None,
                     "calibration_pred_vs_obs": [round(g.p.mean(), 4), round(g.mf.mean(), 4)]})
    return rows


def window_stability(sample=300):
    """How stable is a seller's top-3 weekly window as history grows? (overlap between using the
    first half of their history and all of it)."""
    a = pg._attempts()
    sel = a[a.call_start_time < TEST_START].groupby("fk_glusr_usr_id").size()
    out = []
    for lo, hi, label in [(1, 2, "1-2"), (3, 5, "3-5"), (6, 1000, "6+")]:
        ids = sel[(sel >= lo) & (sel <= hi)].sample(min(sample // 3, (sel.between(lo, hi)).sum()), random_state=7).index
        ov = []
        for g in ids:
            rows = pg._attempts_by_seller()[g]
            rows = rows[rows.call_start_time < TEST_START]
            mid = rows.call_start_time.iloc[len(rows) // 2] if len(rows) > 1 else rows.call_start_time.iloc[0]
            w1, _ = weekly_windows(g, mid.to_pydatetime(), top=3)
            w2, _ = weekly_windows(g, datetime.fromisoformat(TEST_START), top=3)
            ov.append(len(set(w1.window) & set(w2.window)) / 3)
        out.append({"past_dials": label, "sellers": len(ids), "top3_window_overlap": round(float(np.mean(ov)), 3)})
    return out


def off_policy(te, model):
    """Inverse-propensity estimate of the meeting rate if each retry were placed in its model-best
    same-day hour. Propensity = P(hour | context) under the old schedule (multinomial logit)."""
    from .backtest import retime_scores
    r = te[te.call_attempt_count > 1].reset_index(drop=True)
    X = pd.get_dummies(pd.DataFrame({"dow": r.dow.astype(str), "att": r.call_attempt_count.clip(upper=5).astype(str),
                                     "prev": r.prev_disp.astype(str), "bucket": r.redis_bucket.astype(str),
                                     "state": r.seller_state.astype(str)}), dtype=float)
    X["gap"] = np.log1p(r.hrs_since_prev.fillna(48).clip(0, 500))
    clf = LogisticRegression(max_iter=300).fit(X, r.hour)
    prop = clf.predict_proba(X)
    cls = list(clf.classes_)
    pm, _, _ = retime_scores(r, model)
    best_h = np.array(CALL_HOURS)[pm.argmax(1)]
    match = best_h == r.hour.to_numpy()
    p_act = prop[np.arange(len(r)), [cls.index(h) for h in r.hour]]
    w = np.where(match, 1 / np.clip(p_act, 0.02, None), 0)
    ips = float((w * r.mf).sum() / w.sum())                   # self-normalised IPS
    base = float(r.mf.mean())
    rng = np.random.default_rng(7)
    boots = []
    for _ in range(300):
        i = rng.integers(0, len(r), len(r))
        boots.append((w[i] * r.mf.to_numpy()[i]).sum() / w[i].sum() / r.mf.to_numpy()[i].mean() - 1)
    return {"retries": int(len(r)), "share_already_in_best_hour": round(float(match.mean()), 3),
            "meeting_rate_current": round(base, 4), "meeting_rate_policy_ips": round(ips, 4),
            "lift_pct": round(100 * (ips / base - 1), 1),
            "lift_ci95_pct": [round(100 * float(np.percentile(boots, 2.5)), 1), round(100 * float(np.percentile(boots, 97.5)), 1)],
            "effective_sample_size": int(w.sum() ** 2 / (w ** 2).sum())}


def short_redial_by_segment(df):
    """Retries after Not Answered: < 30 min vs 1-2 h, by segment - is there a segment where a
    short redial is as good (which would argue 'supplement' instead of 'change')?"""
    r = df[(df.call_attempt_count > 1) & (df.prev_disp.astype(str) == "Not Answered")].copy()
    r["gap"] = pd.cut(r.hrs_since_prev, [0, 0.5, 1, 2], labels=["<30 min", "30-60 min", "1-2 h"])
    out = []
    for col in ("business_type", "annual_turnover", "redis_bucket"):
        t = r.groupby([col, "gap"], observed=True).agg(n=("mf", "size"), answer=("ans", "mean"), meeting=("mf", "mean"))
        t = t[t.n >= 30].round(4).reset_index()
        t.insert(0, "segment", col)
        t = t.rename(columns={col: "value"})
        out += t.astype({"value": str, "gap": str}).to_dict("records")
    return out


def main():
    if len(sys.argv) > 1:
        g = int(sys.argv[1])
        w, meta = weekly_windows(g)
        print(f"Seller {g}: {meta}\n{w.to_string(index=False)}\n")
        for s in retry_ladder(g):
            print(s)
        return
    from .model import load, TimingModel
    from .backtest import add_band_history
    model = TimingModel()
    df = add_band_history(load())
    te = df[(df.call_start_time >= TEST_START) & df.hour.between(9, 20)].reset_index(drop=True)
    rep = {"confidence_by_history": confidence_by_history(te, model.predict(te).p_meeting.to_numpy())}
    print("confidence:", rep["confidence_by_history"])
    rep["window_stability"] = window_stability()
    print("stability:", rep["window_stability"])
    rep["off_policy_ips"] = off_policy(te, model)
    print("IPS:", rep["off_policy_ips"])
    rep["short_redial_by_segment"] = short_redial_by_segment(df)
    from .demo_sellers import DEMO
    if DEMO:                                                # example seller from the local (git-ignored) demo list
        ex = DEMO[0]
        rep["example_weekly_windows"] = weekly_windows(ex["glid"], datetime.fromisoformat(ex["at"]))[0].to_dict("records")
        rep["example_retry_ladder"] = retry_ladder(ex["glid"], datetime.fromisoformat(ex["at"]))
    json.dump(rep, open(OUT_DIR / "brief_report.json", "w"), indent=2, default=str)


if __name__ == "__main__":
    main()


def full_week_grid(glid, at=None):
    """Every hour x weekday slot for this seller's next attempt, scored (for a heatmap)."""
    w, meta = weekly_windows(glid, at, top=7 * len(CALL_HOURS))
    w = w.assign(day=w.window.str[:3], hour=w.window.str[4:6].astype(int))
    return w, meta


def fifteen_minute_ladder(glid, at=None, attempts=policy.MAX_ATTEMPTS):
    """What the fixed rule does: redial every 15 minutes after a no-answer. Each dial is scored with
    the same time-of-day model x retry-gap factor as our plan, so the two ladders are comparable."""
    at = at or datetime.fromisoformat(TEST_START)
    hist, profile, _ = pg.seller_context(glid, at)
    attempt_no, *_ = pg._episode_state(hist, at)
    model = pg._model()
    steps, t = [], at
    for i in range(attempts):
        n = attempt_no + i
        c = policy.build_candidates(hist, profile, t, n, lead_sent=t if n == 1 else None, days=0)
        row = c.iloc[[0]].copy()
        p = model.predict_slot(row)
        gap = None if i == 0 else 0.25
        factor = 1.0 if gap is None else float(model.gap_factor([gap])[0])
        steps.append({"attempt": n, "when": t.strftime("%a %d %b %H:%M"),
                      "hours_after_previous": gap,
                      "p_answer": round(float(p.p_answer.iloc[0]), 3),
                      "p_meeting": round(float(p.p_meeting.iloc[0]) * factor, 4)})
        t = t + timedelta(minutes=15)
    return steps


def ladder_comparison(glid, at=None):
    """Fixed 15-minute rule vs our retry ladder for the same seller and moment."""
    ours = [s for s in retry_ladder(glid, at) if s["action"] == "CALL"]
    fixed = fifteen_minute_ladder(glid, at, attempts=max(len(ours), 1))
    return {"fixed_15min": fixed, "ours": ours,
            "expected_meetings_fixed": round(sum(s["p_meeting"] for s in fixed), 4),
            "expected_meetings_ours": round(sum(s["p_meeting"] for s in ours), 4)}
