"""Train the two-head timing model on Apr-Aug, evaluate on September.

  p_answer  = P(seller picks up | seller, slot, attempt context)
  p_meeting = P(meeting fixed on this attempt | ...)   <- the objective we optimise

Each head is an ensemble (mean probability) of LightGBM, XGBoost and CatBoost. It won every
accuracy metric in the bake-off (src/compare_models.py, outputs/model_comparison.csv).

Run:  python -m src.model
"""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, log_loss

from .config import WORK_DIR, MODEL_DIR, OUT_DIR, TEST_START
from .features import CAT_FEATURES
from .families import ENSEMBLE_MEMBERS, Ensemble

TARGETS = {"answer": "ans", "meeting": "mf"}


def load():
    df = pd.read_parquet(WORK_DIR / "attempts_features.parquet")
    for c in CAT_FEATURES:
        df[c] = df[c].astype("category")
    return df


def category_levels(df):
    return {c: list(df[c].cat.categories) for c in CAT_FEATURES}


def split(df):
    """Apr-Aug train (last 3 weeks of it = early-stopping validation), September test."""
    tr = df[df.call_start_time < TEST_START]
    te = df[df.call_start_time >= TEST_START]
    cut = tr.call_start_time.max() - pd.Timedelta(days=21)
    return tr, tr[tr.call_start_time < cut], tr[tr.call_start_time >= cut], te


def evaluate(y, p):
    dec = pd.qcut(p, 10, labels=False, duplicates="drop")
    calib = pd.DataFrame({"pred": p, "obs": y, "dec": dec}).groupby("dec").mean()
    return {"test_auc": round(roc_auc_score(y, p), 4), "test_logloss": round(log_loss(y, p), 4),
            "base_rate": round(float(y.mean()), 4),
            "top_decile_rate": round(float(calib.obs.iloc[-1]), 4),
            "bottom_decile_rate": round(float(calib.obs.iloc[0]), 4),
            "calibration": calib.round(4).reset_index().to_dict("records")}


def train(df=None):
    df = load() if df is None else df
    levels = category_levels(df)
    json.dump(levels, open(MODEL_DIR / "category_levels.json", "w"))
    tr, fit, val, te = split(df)
    report = {"n_train": len(tr), "n_test": len(te), "model": "ensemble: " + ", ".join(m.name for m in ENSEMBLE_MEMBERS)}
    for head, y in TARGETS.items():
        members, per_member, imps = [], {}, []
        for cls in ENSEMBLE_MEMBERS:
            m = cls().fit(fit, val, y, levels)
            m.save(MODEL_DIR / f"{head}_{cls.name}.{cls.ext}")
            per_member[cls.name] = round(roc_auc_score(te[y], m.predict(te)), 4)
            imp = m.importance()
            imps.append(imp / imp.sum())
            members.append(m)
        p = Ensemble(members).predict(te)
        imp = pd.concat(imps, axis=1).mean(axis=1).sort_values(ascending=False)
        report[head] = evaluate(te[y].to_numpy(), p)
        report[head]["member_test_auc"] = per_member
        report[head]["top_features"] = imp.head(12).round(3).to_dict()
        print(head, {k: v for k, v in report[head].items() if k != "calibration"})
    report["gap_curve"] = fit_gap_curve(tr)
    json.dump(report, open(OUT_DIR / "model_report.json", "w"), indent=2, default=str)
    return report


GAP_BINS = [0, 0.5, 1, 2, 4, 8, 24, 48, 24 * 60]
# Reference values used when scoring slots: the model ranks *time of day*; how long after the
# lead / last dial is handled by explicit rules, because those features are confounded by the
# current scheduler and do not extrapolate safely.
REF_DELAY_MIN = 0.5
REF_GAP_HRS = 1.5


def fit_gap_curve(tr):
    """Meeting rate of retries after a 'Not Answered', by hours since that dial (training period),
    relative to the 1-2 h bucket. Used as an explicit multiplier on slot scores."""
    r = tr[(tr.call_attempt_count > 1) & (tr.prev_disp.astype(str) == "Not Answered")]
    b = pd.cut(r.hrs_since_prev, GAP_BINS)
    rate = r.groupby(b, observed=False).mf.mean()
    n = r.groupby(b, observed=False).size()
    ref = rate.iloc[GAP_BINS.index(1)]                   # the (1, 2] hours bucket
    raw = (rate / ref).fillna(1.0)
    # Shrink thin buckets: toward 1.0 up to 8 h, toward the previous bucket beyond that
    # (long gaps should never look better than the next-day evidence just because data is thin).
    k = 1000
    factor = []
    for i, (ni, ri) in enumerate(zip(n, raw)):
        prior = 1.0 if GAP_BINS[i] < 8 else factor[-1]
        factor.append((ni * ri + k * prior) / (ni + k))
    factor = pd.Series(factor)
    curve = {"edges": GAP_BINS, "factor": [round(float(x), 3) for x in factor],
             "raw_factor": [round(float(x), 3) for x in raw], "n": n.tolist()}
    json.dump(curve, open(MODEL_DIR / "gap_curve.json", "w"), indent=2)
    print("gap curve", curve)
    return curve


class TimingModel:
    """Loaded models + helper to score a feature frame."""

    def __init__(self):
        self.levels = json.load(open(MODEL_DIR / "category_levels.json"))
        self.m = {k: Ensemble([cls().load(MODEL_DIR / f"{k}_{cls.name}.{cls.ext}", self.levels)
                               for cls in ENSEMBLE_MEMBERS]) for k in TARGETS}
        self.gap = json.load(open(MODEL_DIR / "gap_curve.json"))

    def predict(self, X):
        return pd.DataFrame({f"p_{k}": m.predict(X) for k, m in self.m.items()}, index=X.index)

    def predict_slot(self, X):
        """Time-of-day score: same as predict() but with lead delay / retry gap pinned to reference
        values, so only the slot (hour, day, band history) moves the score."""
        X = X.copy()
        first = X.call_attempt_count == 1
        X["trigger_delay_min"] = np.where(first, REF_DELAY_MIN, np.nan)
        X["hrs_since_prev"] = np.where(first & X.hrs_since_prev.isna(), np.nan, REF_GAP_HRS)
        return self.predict(X)

    def gap_factor(self, hrs):
        e, f = self.gap["edges"], self.gap["factor"]
        idx = np.clip(np.searchsorted(e, np.asarray(hrs, dtype=float), side="left") - 1, 0, len(f) - 1)
        return np.asarray(f)[idx]


if __name__ == "__main__":
    train()
