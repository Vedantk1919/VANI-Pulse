"""Aggregates behind the dashboard's "What the data says" page (no seller-level data).

Run:  python -m src.analysis       (writes outputs/analysis.json)
"""
import json

import numpy as np
import pandas as pd

from .config import OUT_DIR, PERSONA_DIR, WORK_DIR


def rates(g):
    an = g[g.ans == 1]
    return pd.Series({"dials": len(g), "answer_rate": g.ans.mean(), "meeting_rate": g.mf.mean(),
                      "meeting_per_answered": an.mf.mean() if len(an) else np.nan})


def main():
    a = pd.read_parquet(WORK_DIR / "attempts_features.parquet")
    rep = {"totals": {"dials": int(len(a)), "sellers": int(a.fk_glusr_usr_id.nunique()), "meetings": int(a.mf.sum()),
                      "answer_rate": round(a.ans.mean(), 4), "meeting_rate": round(a.mf.mean(), 4),
                      "dials_per_meeting": round(len(a) / a.mf.sum(), 1)}}
    first = a[a.call_attempt_count == 1]
    h = first[first.hour.between(9, 20)].groupby("hour").apply(rates, include_groups=False).reset_index()
    rep["hour_first_attempt"] = h.round(4).to_dict("records")
    att = a.groupby(a.call_attempt_count.clip(upper=8).astype(int)).apply(rates, include_groups=False)
    att["share_of_all_meetings"] = a.groupby(a.call_attempt_count.clip(upper=8).astype(int)).mf.sum() / a.mf.sum()
    rep["by_attempt"] = att.reset_index().round(4).to_dict("records")

    r = a[(a.call_attempt_count > 1) & (a.prev_disp == "Not Answered")]
    bins = [0, 0.5, 1, 2, 4, 8, 24, 48, 1e5]
    labels = ["<30m", "30-60m", "1-2h", "2-4h", "4-8h", "8-24h", "1-2d", "2d+"]
    r = r.assign(gap=pd.cut(r.hrs_since_prev, bins, labels=labels))
    rep["retry_gap"] = r.groupby("gap", observed=True).apply(rates, include_groups=False).reset_index().astype({"gap": str}).round(4).to_dict("records")

    f = first.assign(delay=pd.cut(first.trigger_delay_min, [-1, 0.5, 2, 5, 15, 60, 1e9],
                                  labels=["<30s", "30s-2m", "2-5m", "5-15m", "15-60m", "60m+"]))
    f = f[f.hour >= 10]
    rep["speed_to_lead"] = f.groupby("delay", observed=True).apply(rates, include_groups=False).reset_index().astype({"delay": str}).round(4).to_dict("records")

    an = a[a.ans == 1]
    d24 = an.groupby(an.dials_24h.clip(upper=5)).agg(meeting_per_answered=("mf", "mean"), not_interested=("ni", "mean"),
                                                     answered=("mf", "size")).reset_index()
    rep["dials_24h"] = d24.round(4).to_dict("records")

    # frustration in transcripts vs dials in the previous 24 h
    t = pd.read_csv(PERSONA_DIR / "ps07_call_turns.csv")
    pat = r"baar baar|bar bar|kitni baar|roz roz|call mat|mat karo|mat kijiye|disturb|pareshan|band karo|bola na|bataya na"
    fr = set(t[(t.speaker == "seller") & t.text.str.lower().str.contains(pat, na=False)].attempt_id)
    x = a[a.data_hotlead_disposition_dtlid.isin(set(t.attempt_id))]
    x = x.assign(frus=x.data_hotlead_disposition_dtlid.isin(fr))
    rep["frustration_by_dials_24h"] = x.groupby(x.dials_24h.clip(upper=5)).frus.agg(["size", "mean"]).reset_index() \
        .rename(columns={"size": "calls", "mean": "frustration_rate"}).round(4).to_dict("records")

    seg = []
    for col in ("annual_turnover", "business_type", "seller_state"):
        g = first.groupby(col).apply(rates, include_groups=False)
        g = g[g.dials >= 2000].sort_values("meeting_rate", ascending=False).head(8).reset_index().rename(columns={col: "value"})
        g.insert(0, "segment", col)
        seg += g.round(4).to_dict("records")
    rep["segments_first_attempt"] = seg
    # best time to call: hour x day-of-week heatmap (first attempts) and best band per segment
    f9 = first[first.hour.between(9, 20)]
    hd = f9.groupby([f9.call_start_time.dt.dayofweek.rename("dow"), "hour"]).agg(
        dials=("mf", "size"), meeting_rate=("mf", "mean"), answer_rate=("ans", "mean")).reset_index()
    rep["hour_dow_first_attempt"] = hd.round(4).to_dict("records")
    bands = {9: "09-10", 10: "10-12", 11: "10-12", 12: "12-14", 13: "12-14", 14: "14-16", 15: "14-16",
             16: "16-18", 17: "16-18", 18: "18-21", 19: "18-21", 20: "18-21"}
    f9 = f9.assign(band=f9.hour.map(bands))
    best = []
    for col, label in (("business_type", "Business type"), ("annual_turnover", "Turnover"),
                       ("seller_state", "State"), ("top_category_group", "Category group")):
        g = f9.groupby([col, "band"]).agg(n=("mf", "size"), meeting_rate=("mf", "mean")).reset_index()
        g = g[g.n >= 300]
        tot = f9.groupby(col).size()
        for v, gg in g.groupby(col):
            if tot.get(v, 0) < 3000 or len(gg) < 4:
                continue
            gg = gg.sort_values("meeting_rate", ascending=False)
            worst = gg.iloc[-1]
            best.append({"segment": label, "value": v, "first_calls": int(tot[v]),
                         "best_window": gg.iloc[0].band, "best_meeting_rate": round(float(gg.iloc[0].meeting_rate), 4),
                         "second_best": gg.iloc[1].band, "worst_window": worst.band,
                         "worst_meeting_rate": round(float(worst.meeting_rate), 4)})
    rep["best_window_by_segment"] = best
    json.dump(rep, open(OUT_DIR / "analysis.json", "w"), indent=2, default=float)
    print({k: (v if k == "totals" else len(v)) for k, v in rep.items()})


if __name__ == "__main__":
    main()
