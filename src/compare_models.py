"""Model bake-off: same features, same Apr-Aug training data, same September test.

Candidates: logistic regression (baseline), LightGBM, XGBoost, CatBoost, and an ensemble
(average of the three boosted models).

Scored on September 2026:
  * accuracy  - AUC, log-loss, Brier score, top-decile rate / lift   (both heads)
  * the thing we actually use the model for - ranking time slots: the empirical
    slot-quality check from the backtest (observed meeting rate, best vs worst quintile)
    and the capacity-constrained re-timing estimate.

Run:  python -m src.compare_models
"""
import json
import time

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, log_loss, brier_score_loss, average_precision_score

from .config import OUT_DIR, TEST_START, CALL_HOURS
from .families import ALL, ENSEMBLE_MEMBERS, Ensemble
from .model import load, category_levels, split, TARGETS, TimingModel
from . import backtest

H = CALL_HOURS


class Wrapped:
    """Gives any family the TimingModel interface so the backtest can use it unchanged."""

    def __init__(self, fns):
        self.fns = fns
        self._tm = TimingModel()                     # reuse gap curve + slot-pinning logic

    def predict(self, X):
        return pd.DataFrame({f"p_{k}": f(X) for k, f in self.fns.items()}, index=X.index)

    def predict_slot(self, X):
        return TimingModel.predict_slot(self, X)

    def gap_factor(self, hrs):
        return self._tm.gap_factor(hrs)


def metrics(y, p):
    dec = pd.qcut(p, 10, labels=False, duplicates="drop")
    top = float(y[dec == dec.max()].mean())
    return {"auc": round(roc_auc_score(y, p), 4), "pr_auc": round(average_precision_score(y, p), 4),
            "logloss": round(log_loss(y, p), 4), "brier": round(brier_score_loss(y, p), 5),
            "top_decile_rate": round(top, 4), "top_decile_lift": round(top / y.mean(), 2)}


def main():
    df = load()
    levels = category_levels(df)
    tr, fit, val, _ = split(df)
    te = backtest.add_band_history(df)
    te = te[(te.call_start_time >= TEST_START) & te.hour.between(H[0], H[-1])].reset_index(drop=True)

    fitted, secs = {}, {}
    for fam, cls in ALL.items():
        t0 = time.time()
        fitted[fam] = {head: cls().fit(fit, val, y, levels) for head, y in TARGETS.items()}
        secs[fam] = round(time.time() - t0, 1)
        print(f"{fam}: trained in {secs[fam]}s")
    names = [c.name for c in ENSEMBLE_MEMBERS]
    fitted["ensemble"] = {h: Ensemble([fitted[n][h] for n in names]) for h in TARGETS}
    secs["ensemble"] = round(sum(secs[n] for n in names), 1)

    results = []
    for fam, heads in fitted.items():
        r = {"model": fam, "train_seconds": secs[fam]}
        for head, y in TARGETS.items():
            for k, v in metrics(te[y].to_numpy(), heads[head].predict(te)).items():
                r[f"{head}_{k}"] = v
        a, _ = backtest.part_a(te, Wrapped({h: m.predict for h, m in heads.items()}))
        ev = a["empirical_validation"]
        for kind, tag in (("first attempt", "first"), ("retry", "retry")):
            r[f"slot_check_{tag}_Q5_vs_Q1_pct"] = ev[f"{kind} Q5_vs_Q1_meeting_lift_pct"]
            r[f"slot_check_{tag}_ci95"] = ev[f"{kind} Q5_vs_Q1_ci95"]
        r["retiming_lift_capacity_pct"] = a["lift_capacity_pct"]
        results.append(r)
        print(r)
    res = pd.DataFrame(results)
    res.to_csv(OUT_DIR / "model_comparison.csv", index=False)
    json.dump(results, open(OUT_DIR / "model_comparison.json", "w"), indent=2, default=float)
    cols = ["model", "meeting_auc", "meeting_logloss", "meeting_top_decile_lift", "answer_auc", "answer_logloss",
            "slot_check_first_Q5_vs_Q1_pct", "slot_check_first_ci95", "slot_check_retry_Q5_vs_Q1_pct",
            "slot_check_retry_ci95", "retiming_lift_capacity_pct", "train_seconds"]
    print(res[cols].to_string(index=False))


if __name__ == "__main__":
    main()
