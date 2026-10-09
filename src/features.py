"""Build the attempt-level feature table.

Every history feature is computed only from attempts strictly *before* the current one,
so the table can be split by time without leakage.

Run:  python -m src.features
"""
import numpy as np
import pandas as pd

from .config import ATTEMPTS_CSV, SELLERS_CSV, WORK_DIR, BANDS, TURNOVER_ORDER

PROFILE_CATS = ["seller_state", "business_type", "nature_of_business", "top_category_group"]
CAT_FEATURES = ["redis_bucket", "lead_bot_version", "prev_disp", "band"] + PROFILE_CATS
NUM_FEATURES = [
    "hour", "dow", "is_weekend", "call_attempt_count", "trigger_delay_min",
    "hrs_since_prev", "dials_24h", "dials_today",
    "hist_n", "hist_ans_rate", "hist_mf", "hist_ni", "hist_callback", "hist_episodes",
    "hist_prev_episode_mf", "band_n", "band_ans_rate", "band_ans_lift",
    "turnover_ord", "gst_registration_year", "num_categories",
]
FEATURES = NUM_FEATURES + CAT_FEATURES


def load_sellers():
    s = pd.read_csv(SELLERS_CSV, usecols=[
        "fk_glusr_usr_id", "seller_city", "seller_state", "business_type", "annual_turnover",
        "nature_of_business", "gst_registration_year", "top_category_1", "top_category_group",
        "num_categories"])
    s["turnover_ord"] = s.annual_turnover.map(TURNOVER_ORDER)
    return s.drop_duplicates("fk_glusr_usr_id")


def hour_band(h):
    out = np.full(len(h), BANDS[-1][2], dtype=object)
    for lo, hi, name in BANDS:
        out[(h >= lo) & (h < hi)] = name
    return out


def build():
    a = pd.read_csv(ATTEMPTS_CSV, parse_dates=["lead_sent_time", "call_start_time", "lead_tbro_time"])
    a = a.dropna(subset=["call_start_time"]).copy()
    a["call_attempt_count"] = a.call_attempt_count.fillna(1)
    a["lead_bot_version"] = a.lead_bot_version.fillna("unknown")
    a = a.sort_values(["fk_glusr_usr_id", "call_start_time"]).reset_index(drop=True)

    a["ans"] = (a.lead_call_status == "Answered").astype(np.int8)
    a["mf"] = a.meeting_fixed.astype(np.int8)
    a["ni"] = (a.disposition_label == "Not Interested").astype(np.int8)
    a["cb"] = (a.disposition_label == "Call Later / Busy").astype(np.int8)
    t = a.call_start_time
    a["hour"] = t.dt.hour
    a["dow"] = t.dt.dayofweek
    a["is_weekend"] = (a.dow >= 5).astype(np.int8)
    a["band"] = hour_band(a.hour.values)
    a["date"] = t.dt.normalize()
    a["trigger_delay_min"] = np.where(
        a.call_attempt_count == 1,
        ((t - a.lead_sent_time).dt.total_seconds() / 60).clip(0, 24 * 60), np.nan)

    g = a.groupby("fk_glusr_usr_id", sort=False)
    a["prev_disp"] = g.disposition_label.shift().fillna("none")
    a["hrs_since_prev"] = ((t - g.call_start_time.shift()).dt.total_seconds() / 3600).clip(upper=24 * 60)

    # dials to this seller in the previous 24h (rows are sorted by seller, time)
    secs = (t.astype("int64") // 10**9).to_numpy()
    key = a.fk_glusr_usr_id.to_numpy().astype(np.int64) * 10**10 + secs
    a["dials_24h"] = np.arange(len(a)) - np.searchsorted(key, key - 86400)
    a["dials_today"] = a.groupby(["fk_glusr_usr_id", "date"]).cumcount()

    # cumulative history (exclusive of current row)
    a["hist_n"] = g.cumcount()
    for col, src in [("hist_ans", "ans"), ("hist_mf", "mf"), ("hist_ni", "ni"), ("hist_callback", "cb")]:
        a[col] = g[src].cumsum() - a[src]
    a["hist_ans_rate"] = np.where(a.hist_n > 0, a.hist_ans / a.hist_n.clip(lower=1), np.nan)
    a["new_ep"] = (a.call_attempt_count == 1).astype(np.int8)
    a["hist_episodes"] = g.new_ep.cumsum() - a.new_ep
    # did any earlier episode end in a meeting?
    a["hist_prev_episode_mf"] = (a.hist_mf > 0).astype(np.int8)

    # same-band history: how this seller has answered in this hour band before
    gb = a.groupby(["fk_glusr_usr_id", "band"], sort=False)
    a["band_n"] = gb.cumcount()
    band_ans = gb.ans.cumsum() - a.ans
    a["band_ans_rate"] = np.where(a.band_n > 0, band_ans / a.band_n.clip(lower=1), np.nan)
    a["band_ans_lift"] = a.band_ans_rate - a.hist_ans_rate

    s = load_sellers()
    a = a.merge(s, on="fk_glusr_usr_id", how="left")
    for c in CAT_FEATURES:
        a[c] = a[c].fillna("NA").astype(str)

    keep = ["data_hotlead_disposition_dtlid", "fk_glusr_usr_id", "call_start_time", "lead_sent_time",
            "lead_tbro_time", "disposition_label", "lead_call_duration", "ans", "mf", "ni", "cb",
            "date", "annual_turnover", "seller_city", "top_category_1"] + FEATURES
    a = a[list(dict.fromkeys(keep))]
    a.to_parquet(WORK_DIR / "attempts_features.parquet", index=False)
    print("features:", a.shape, "->", WORK_DIR / "attempts_features.parquet")
    return a


if __name__ == "__main__":
    build()
