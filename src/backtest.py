"""Backtest the policy on held-out September 2026 against what actually happened.

Part A - slot re-timing: move each Sept attempt to its best feasible hour on the same day.
         (A1) model-estimated meetings, unconstrained and under hourly dialer capacity
         (A2) empirical check: observed meeting rate of attempts that *happened* to fall in the
              model's top hours vs the rest, standardised by attempt number
Part B - retry/stop guardrails replayed on actual Sept call sequences.
Part C - evidence on the 15-minute rule.

Run:  python -m src.backtest
"""
import json

import numpy as np
import pandas as pd

from .config import WORK_DIR, OUT_DIR, TEST_START, CALL_HOURS, BANDS
from .features import hour_band
from .model import TimingModel, load
from . import policy

H = np.array(CALL_HOURS)


def add_band_history(df):
    """Per-seller cumulative attempts/answers in every band, before each row."""
    df = df.sort_values(["fk_glusr_usr_id", "call_start_time"]).copy()
    g = df.groupby("fk_glusr_usr_id", sort=False)
    for _, _, b in BANDS:
        is_b = (df.band.astype(str) == b).astype(int)
        df[f"bn_{b}"] = is_b.groupby(df.fk_glusr_usr_id).cumsum() - is_b
        df[f"ba_{b}"] = (is_b * df.ans).groupby(df.fk_glusr_usr_id).cumsum() - is_b * df.ans
    return df


def retime_scores(te, model):
    """Slot score for every same-day hour; -inf where infeasible or not movable.

    Score = time-of-day P(meeting) (lead delay / retry gap pinned, see TimingModel.predict_slot)
            x retry-gap factor for the new gap.  Only retries are movable: first attempts stay
    where they are (speed-to-lead says call now)."""
    n = len(te)
    pm = np.full((n, len(H)), -np.inf)
    pmeet = np.full((n, len(H)), np.nan)
    pa = np.full((n, len(H)), np.nan)
    actual_h = te.hour.to_numpy()
    first = (te.call_attempt_count == 1).to_numpy()
    for j, h in enumerate(H):
        X = te.copy()
        dh = h - actual_h
        X["hour"] = h
        X["band"] = hour_band(np.full(n, h))
        bn = np.select([X.band == b for _, _, b in BANDS], [te[f"bn_{b}"] for _, _, b in BANDS])
        ba = np.select([X.band == b for _, _, b in BANDS], [te[f"ba_{b}"] for _, _, b in BANDS])
        X["band_n"] = bn
        X["band_ans_rate"] = np.where(bn > 0, ba / np.maximum(bn, 1), np.nan)
        X["band_ans_lift"] = X.band_ans_rate - X.hist_ans_rate
        p = model.predict_slot(X)
        new_gap = te.hrs_since_prev.to_numpy() + dh
        gf = np.where(first, 1.0, model.gap_factor(np.nan_to_num(new_gap, nan=99)))
        feasible = ~first & (np.nan_to_num(new_gap, nan=99) >= policy.MIN_GAP_HRS)
        feasible |= dh == 0                                   # the actual slot is always feasible
        score = p.p_meeting.to_numpy() * gf
        pm[:, j] = np.where(feasible, score, -np.inf)
        pmeet[:, j], pa[:, j] = score, p.p_answer.to_numpy()
    return pm, pa, pmeet


def capacity_assign(te, pm, slack=1.15):
    """Greedy per-day assignment with hourly capacity = actual volume * slack."""
    hour_idx = te.hour.to_numpy() - H[0]
    choice = hour_idx.copy()
    for d, idx in te.groupby(te.date).indices.items():
        cap = np.bincount(hour_idx[idx], minlength=len(H)) * slack
        sub = pm[idx]
        gain = sub.max(1) - sub[np.arange(len(idx)), hour_idx[idx]]
        for k in np.argsort(-gain):
            row = idx[k]
            for j in np.argsort(-pm[row]):
                if pm[row, j] == -np.inf:
                    break
                if cap[j] >= 1:
                    cap[j] -= 1
                    choice[row] = j
                    break
    return choice


def part_a(te, model):
    pm, pa, pmeet = retime_scores(te, model)
    ai = te.hour.to_numpy() - H[0]
    rows = np.arange(len(te))
    p_actual = pm[rows, ai]
    best = pm.argmax(1)
    cap_choice = capacity_assign(te, pm)
    eq_choice = capacity_assign(te, pm, slack=1.0)          # exactly the dials actually made per (day, hour)
    movable = np.isfinite(pm).sum(1) > 1
    res = {
        "attempts": int(len(te)), "movable_attempts": int(movable.sum()),
        "observed_meetings": int(te.mf.sum()),
        "model_expected_meetings_actual_schedule": round(float(p_actual.sum()), 1),
        "model_expected_meetings_best_slot": round(float(pm[rows, best].sum()), 1),
        "model_expected_meetings_capacity_constrained": round(float(pm[rows, cap_choice].sum()), 1),
        "model_expected_meetings_equal_dials_per_hour": round(float(pm[rows, eq_choice].sum()), 1),
        "share_attempts_moved_capacity": round(float((cap_choice != ai).mean()), 3),
        "answer_rate_actual_est": round(float(pa[rows, ai].mean()), 4),
        "answer_rate_capacity_est": round(float(pa[rows, cap_choice].mean()), 4),
    }
    for k, num in [("lift_equal_dials_pct", "model_expected_meetings_equal_dials_per_hour"),
                   ("lift_unconstrained_pct", "model_expected_meetings_best_slot"),
                   ("lift_capacity_pct", "model_expected_meetings_capacity_constrained")]:
        res[k] = round(100 * (res[num] / res["model_expected_meetings_actual_schedule"] - 1), 1)
    res["recommended_hour_mix"] = pd.Series(H[cap_choice]).value_counts(normalize=True).sort_index().round(3).to_dict()
    res["actual_hour_mix"] = te.hour.value_counts(normalize=True).sort_index().round(3).to_dict()

    # A2 empirical validation on real Sept outcomes: score of the hour the call actually happened at,
    # relative to the same attempt's average over all hours (seller/context effects cancel out).
    # If the time-of-day signal is real, observed meeting rate must rise with this ratio.
    relq = pmeet[rows, ai] / np.nanmean(pmeet, axis=1)
    e = te[["mf", "ans", "call_attempt_count"]].copy()
    e["relq"] = relq
    e["kind"] = np.where(te.call_attempt_count == 1, "first attempt", "retry")
    val = {}
    for k, g in e.groupby("kind"):
        g = g.copy()
        g["quintile"] = pd.qcut(g.relq, 5, labels=["Q1 worst", "Q2", "Q3", "Q4", "Q5 best"])
        t = g.groupby("quintile", observed=True).agg(n=("mf", "size"), relative_slot_score=("relq", "mean"),
                                                    meeting_rate=("mf", "mean"), answer_rate=("ans", "mean"))
        val[k] = t.round(4).reset_index().to_dict("records")
        val[k + " Q5_vs_Q1_meeting_lift_pct"] = round(100 * (t.meeting_rate.iloc[-1] / t.meeting_rate.iloc[0] - 1), 1)
        # 95% bootstrap interval of the Q5-vs-Q1 lift
        rng = np.random.default_rng(7)
        q1 = g.mf[g.quintile == "Q1 worst"].to_numpy()
        q5 = g.mf[g.quintile == "Q5 best"].to_numpy()
        boots = [rng.choice(q5, len(q5)).mean() / max(rng.choice(q1, len(q1)).mean(), 1e-9) - 1 for _ in range(1000)]
        val[k + " Q5_vs_Q1_ci95"] = [round(100 * float(np.percentile(boots, 2.5)), 1),
                                     round(100 * float(np.percentile(boots, 97.5)), 1)]
    res["empirical_validation"] = val
    return res, pm


DEFAULT_POLICY = {"max_attempts": policy.MAX_ATTEMPTS, "stop_p_meeting": policy.STOP_P_MEETING,
                  "stop_after_not_interested": False}


def prepare_replay(te, model):
    te = te.sort_values(["fk_glusr_usr_id", "call_start_time"]).reset_index(drop=True)
    te["p_meeting"] = model.predict(te).p_meeting.to_numpy()
    te["ep"] = (te.call_attempt_count == 1).groupby(te.fk_glusr_usr_id).cumsum()
    return te


def simulate(te, max_attempts, stop_p_meeting, stop_after_not_interested):
    """Replay actual Sept sequences; return a mask of dials the policy would still make.
    Dropped dials lose whatever they produced (conservative: no credit for re-allocation)."""
    sid, ep = te.fk_glusr_usr_id.to_numpy(), te.ep.to_numpy()
    t = te.call_start_time.to_numpy().astype("datetime64[s]").astype(np.int64)
    att, pmv, disp = te.call_attempt_count.to_numpy(), te.p_meeting.to_numpy(), te.disposition_label.to_numpy()
    keep = np.zeros(len(te), bool)
    kept_times, cur, stopped = [], None, False
    for i in range(len(te)):
        if cur != (sid[i], ep[i]):
            if cur is None or cur[0] != sid[i]:
                kept_times = []
            cur, stopped = (sid[i], ep[i]), False
        if stopped:
            continue
        if att[i] > max_attempts or (att[i] > 1 and pmv[i] < stop_p_meeting):
            stopped = True
            continue
        if kept_times and t[i] - kept_times[-1] < policy.MIN_GAP_HRS * 3600:
            continue
        if sum(1 for k in kept_times[-policy.MAX_DIALS_24H:] if t[i] - k < 86400) >= policy.MAX_DIALS_24H:
            continue
        keep[i] = True
        kept_times.append(t[i])
        if stop_after_not_interested and disp[i] == "Not Interested":
            stopped = True
    return keep


def part_b(te, taus=(0, 0.005, 0.01, 0.015, 0.02, 0.03), caps=(4, 5, 6, 99)):
    mf, ans = te.mf.to_numpy(), te.ans.to_numpy()
    base = {"dials": int(len(te)), "meetings": int(mf.sum()), "answered": int(ans.sum()),
            "calls_per_meeting": round(len(te) / mf.sum(), 2),
            "dials_with_3plus_in_24h": int((te.dials_24h >= 3).sum()),
            "attempts_6plus": int((te.call_attempt_count >= 6).sum())}
    out = {"baseline": base, "grid": []}
    for cap in caps:
        for tau in taus:
            for stop_ni in (False, True):
                keep = simulate(te, cap, tau, stop_ni)
                r = {"max_attempts": cap, "stop_p_meeting": tau, "stop_after_not_interested": stop_ni,
                     "dials": int(keep.sum()), "meetings": int(mf[keep].sum()), "answered": int(ans[keep].sum())}
                r["dials_saved_pct"] = round(100 * (1 - r["dials"] / base["dials"]), 1)
                r["meetings_retained_pct"] = round(100 * r["meetings"] / base["meetings"], 1)
                r["calls_per_meeting"] = round(r["dials"] / max(r["meetings"], 1), 2)
                r["connect_rate"] = round(r["answered"] / max(r["dials"], 1), 4)
                out["grid"].append(r)
    keep = simulate(te, **DEFAULT_POLICY)
    out["default"] = next(r for r in out["grid"] if all(r[k] == v for k, v in DEFAULT_POLICY.items()))
    return out, keep


def part_d(te, keep, model):
    """Default stop rules + re-timing of the remaining retries (capacity-constrained)."""
    kept = te[keep].reset_index(drop=True)
    a, _ = part_a(kept, model)
    ratio = a["model_expected_meetings_capacity_constrained"] / a["model_expected_meetings_actual_schedule"]
    meetings = kept.mf.sum() * ratio
    return {"dials": int(len(kept)), "observed_meetings_kept": int(kept.mf.sum()),
            "retiming_ratio": round(float(ratio), 4), "estimated_meetings": round(float(meetings), 0),
            "meetings_vs_baseline_pct": round(100 * (meetings / te.mf.sum() - 1), 1),
            "dials_vs_baseline_pct": round(100 * (len(kept) / len(te) - 1), 1),
            "calls_per_meeting": round(len(kept) / meetings, 2),
            "baseline_calls_per_meeting": round(len(te) / te.mf.sum(), 2),
            "answer_rate_est": a["answer_rate_capacity_est"]}


def part_c(df):
    """Evidence for the 15-minute rule."""
    raw = pd.read_parquet(WORK_DIR / "attempts_features.parquet",
                          columns=["fk_glusr_usr_id", "call_start_time", "prev_disp", "hrs_since_prev",
                                   "ans", "mf", "ni", "call_attempt_count", "dials_24h", "band"])
    r = raw[(raw.call_attempt_count > 1)].copy()
    bins = [0, .25, .5, 1, 1.5, 2, 3, 4, 8, 24, 48, 1e5]
    r["gap"] = pd.cut(r.hrs_since_prev, bins)
    def tab(x):
        t = x.groupby("gap", observed=True).agg(n=("ans", "size"), answer=("ans", "mean"), meeting=("mf", "mean"))
        ansd = x[x.ans == 1].groupby("gap", observed=True).agg(meeting_per_answered=("mf", "mean"),
                                                              not_interested_per_answered=("ni", "mean"))
        return t.join(ansd).round(3).reset_index().astype({"gap": str}).to_dict("records")
    after_na = r[r.prev_disp == "Not Answered"]
    an = raw[raw.ans == 1]
    dens = an.groupby(an.dials_24h.clip(upper=5)).agg(n=("mf", "size"), meeting_per_answered=("mf", "mean"),
                                                      not_interested=("ni", "mean")).round(3)
    return {"retry_after_not_answered_by_gap_hours": tab(after_na),
            "all_retries_by_gap_hours": tab(r),
            "answered_by_dials_in_prev_24h": dens.reset_index().to_dict("records")}


def main():
    model = TimingModel()
    df = add_band_history(load())
    te = df[(df.call_start_time >= TEST_START) & df.hour.between(H[0], H[-1])]
    te = prepare_replay(te, model)
    a, _ = part_a(te, model)
    print("A:", {k: v for k, v in a.items() if "mix" not in k and k != "empirical_validation"})
    b, keep = part_b(te)
    print("B baseline:", b["baseline"], "\nB default:", b["default"])
    d = part_d(te, keep, model)
    print("D combined:", d)
    from .allocator import fit_tiers, tier_report
    cuts = fit_tiers(df, model)                               # always refit: cut points follow the current model
    tiers = tier_report(te, te.p_meeting.to_numpy(), cuts)
    print("tiers:", tiers)
    c = part_c(df)
    rep = {"test_period": f"{TEST_START} .. 2026-09-30", "retiming": a, "retry_stop": b, "combined": d, "tiers": tiers,
           "rule_15min": c}
    json.dump(rep, open(OUT_DIR / "backtest_report.json", "w"), indent=2, default=str)
    pd.DataFrame(b["grid"]).to_csv(OUT_DIR / "retry_policy_grid.csv", index=False)


if __name__ == "__main__":
    main()
