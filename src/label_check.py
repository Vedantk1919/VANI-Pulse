"""Robustness of the meeting label: re-score September with the incorrect_mf evaluator's corrections.

The evaluator re-read 19,617 calls; 'meeting fixed' calls where the seller actually rejected the
meeting are set to 0. If the false-meeting rate does not depend on hour or attempt number, the
timing recommendations are unaffected.

Run:  python -m src.label_check      (writes outputs/label_check.json)
"""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .config import OUT_DIR, PERSONA_DIR, TEST_START
from .model import load, TimingModel


def load_flags():
    """incorrect_mf flags, extracted once from the persona evaluator outputs."""
    path = PERSONA_DIR / "incorrect_mf.parquet"
    if not path.exists():
        import glob
        x = pd.concat(pd.read_csv(f) for f in sorted(glob.glob(str(PERSONA_DIR / "ps07_evaluator_outputs_*.csv"))))
        x = x[x.eval_agent == "incorrect_mf"]
        j = x.agent_output.map(json.loads)
        pd.DataFrame({"attempt_id": x.attempt_id, "incorrect_mf": j.map(lambda d: d.get("incorrect_mf")),
                      "stance": j.map(lambda d: d.get("seller_final_stance"))}).to_parquet(path, index=False)
    return pd.read_parquet(path)


def main():
    flags = load_flags()
    df = load()
    df = df.merge(flags, left_on="data_hotlead_disposition_dtlid", right_on="attempt_id", how="left")
    df["mf_clean"] = np.where(df.incorrect_mf == True, 0, df.mf)
    mf = df[(df.mf == 1) & df.incorrect_mf.notna()]
    rep = {"meetings": int(df.mf.sum()), "meetings_evaluated": int(len(mf)),
           "false_meeting_rate": round(float(mf.incorrect_mf.mean()), 4),
           "false_rate_by_hour_band": mf.groupby(pd.cut(mf.hour, [8, 10, 12, 14, 16, 18, 21])).incorrect_mf.mean().round(4)
               .rename(index=str).to_dict(),
           "false_rate_by_attempt": mf.groupby(mf.call_attempt_count.clip(upper=4)).incorrect_mf.mean().round(4)
               .rename(index=lambda x: str(int(x))).to_dict()}
    te = df[df.call_start_time >= TEST_START]
    p = TimingModel().predict(te).p_meeting.to_numpy()
    rep["test_auc_original_label"] = round(roc_auc_score(te.mf, p), 4)
    rep["test_auc_clean_label"] = round(roc_auc_score(te.mf_clean, p), 4)
    hour = te.groupby("hour").agg(original=("mf", "mean"), clean=("mf_clean", "mean"))
    rep["hour_ranking_correlation"] = round(float(hour.original.rank().corr(hour.clean.rank())), 4)
    json.dump(rep, open(OUT_DIR / "label_check.json", "w"), indent=2, default=float)
    print(json.dumps(rep, indent=2, default=float))


if __name__ == "__main__":
    main()
