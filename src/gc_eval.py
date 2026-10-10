"""Quality of the seller.md layer across all 5,000 Global Context sellers.

  * lookback choice  - how much of each seller's activity each window captures
  * compactness      - characters / approx tokens per file
  * coverage         - share of files with a real-number opening, open threads, fresh activity
  * freshness        - time from a new (write-back) event to an updated seller.md

Run:  python -m src.gc_eval        (writes outputs/gc_eval.json)
"""
import json
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .config import OUT_DIR
from .timeline import TIMELINE, WRITEBACK
from . import seller_md as sm

AS_OF = datetime(2026, 9, 30, 10, 0)


def main():
    t = pd.read_parquet(TIMELINE)
    t = t[t.ts <= AS_OF]
    rep = {"as_of": AS_OF.isoformat(), "sellers": int(t.glid.nunique())}

    # lookback: share of sellers with any seller-initiated activity, and share of all events covered
    act = t[t.by_seller == 1]
    total = t.groupby("glid").size()
    rows = []
    for d in (7, 30, 60, 90, 120, 180):
        w = t[t.ts > AS_OF - timedelta(days=d)]
        rows.append({"days": d, "sellers_with_activity": round(act[act.ts > AS_OF - timedelta(days=d)].glid.nunique() / rep["sellers"], 3),
                     "median_events_per_seller": int(w.groupby("glid").size().reindex(total.index, fill_value=0).median()),
                     "share_of_all_events": round(len(w) / len(t), 3)})
    rep["lookback"] = rows

    # build every file
    sizes, hooks, threads, warm, secs = [], 0, 0, 0, []
    for g in sorted(t.glid.unique()):
        t0 = time.perf_counter()
        md, f = sm.build(g, AS_OF)
        secs.append(time.perf_counter() - t0)
        sizes.append(len(md))
        hooks += sm.personal_hook(f) is not None
        threads += bool(f["open_threads"])
        warm += bool(f["timing_signals"].get("warm"))
    n = len(sizes)
    rep["compactness"] = {"chars_median": int(np.median(sizes)), "chars_p95": int(np.percentile(sizes, 95)),
                          "approx_tokens_median": int(np.median(sizes) / 4), "approx_tokens_p95": int(np.percentile(sizes, 95) / 4)}
    rep["coverage"] = {"real_number_opening": round(hooks / n, 3), "has_open_threads": round(threads / n, 3),
                       "warm_at_as_of": round(warm / n, 3)}
    rep["build_ms_median"] = round(1000 * float(np.median(secs)), 1)

    # freshness: write back a call result, rebuild, check it is visible
    g = int(t.glid.iloc[0])
    backup = WRITEBACK.read_text() if WRITEBACK.exists() else None
    t0 = time.perf_counter()
    sm.writeback(g, AS_OF, "Call Later / Busy", "Seller was driving, asked to call at 5 PM", AS_OF.replace(hour=17))
    md, _ = sm.build(g, AS_OF + timedelta(seconds=1))
    rep["freshness_ms_writeback_to_updated_file"] = round(1000 * (time.perf_counter() - t0), 1)
    rep["freshness_check_passed"] = "05:00 PM" in md
    if backup is None:
        WRITEBACK.unlink()
    else:
        WRITEBACK.write_text(backup)

    json.dump(rep, open(OUT_DIR / "gc_eval.json", "w"), indent=2, default=float)
    print(json.dumps(rep, indent=2, default=float))


if __name__ == "__main__":
    main()
