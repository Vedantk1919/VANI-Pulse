"""Call-plan policy: when to dial a seller next, and when to stop.

The model ranks every candidate slot (date x hour) by predicted P(meeting fixed).
Guardrails derived from the Apr-Sep data keep the plan from irritating sellers:

  * MIN_GAP_HRS     never redial sooner than 30 min (answered re-dials < 30 min fix meetings
                    2.5-3.2% vs 11.5% at 1-2 h; frustration rises with dial density).
                    This replaces the fixed 15-minute redial.
  * Gap curve       retries are scored x a data-derived factor for hours since the last dial
                    (1-2 h and 4-8 h same day best; next day ~0.4-0.5x)
  * Fresh leads     call immediately (speed-to-lead); leads that arrive outside 09:00-21:00 are
                    called when the window opens. (Moving the 9 AM backlog later was tested and
                    NOT supported by the data - left as an A/B hypothesis.)
  * MAX_DIALS_24H   at most 3 dials in any rolling 24 h (MF per answered call falls from
                    18.6% with 0 prior dials in 24 h to 7.4% with 3; frustration doubles)
  * MAX_ATTEMPTS    stop the episode after 5 attempts (attempts 6+ = 1.2% of all meetings)
  * STOP_P_MEETING  stop when even the best slot in the next 48 h is below this probability
  * Call Later      honour the time the seller asked for (dial 5 min early)
  * Not Interested / Meeting Fixed / do-not-call  -> stop the episode
Global Context signals (optional, from seller.md; tested in gc_validation.py):
  * Warm moment     seller active on another channel in the last 3 h -> slots inside that 3 h
                    window get x1.08 (within-seller test: +4.4 pp pickup, 95% CI +1.1 to +8.1)
  * Executive today an IndiaMART executive spoke to the seller in the last 24 h -> no VANI dial
                    today (policy choice; too few cases in the data to test)
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .config import CALL_HOURS, band_of

MIN_GAP_HRS = 0.5
MAX_DIALS_24H = 3
MAX_ATTEMPTS = 5
STOP_P_MEETING = 0.01
HORIZON_DAYS = 2


@dataclass
class Plan:
    action: str                     # "call" | "stop"
    reason: str
    slot: datetime | None = None
    p_meeting: float | None = None
    p_answer: float | None = None
    ranked: pd.DataFrame = field(default_factory=pd.DataFrame)


def _history_stats(hist, slot):
    """History features for a hypothetical dial at `slot` given past attempts `hist`."""
    h = hist[hist.call_start_time < slot]
    n = len(h)
    band = band_of(slot.hour)
    hb = h[h.band == band]
    ans_rate = h.ans.mean() if n else np.nan
    band_rate = hb.ans.mean() if len(hb) else np.nan
    last = h.iloc[-1] if n else None
    secs = (slot - h.call_start_time).dt.total_seconds() if n else pd.Series(dtype=float)
    return {
        "hist_n": n, "hist_ans_rate": ans_rate, "hist_mf": int(h.mf.sum()) if n else 0,
        "hist_ni": int(h.ni.sum()) if n else 0, "hist_callback": int(h.cb.sum()) if n else 0,
        "hist_episodes": int((h.call_attempt_count == 1).sum()) if n else 0,
        "hist_prev_episode_mf": int(h.mf.sum() > 0) if n else 0,
        "band_n": len(hb), "band_ans_rate": band_rate,
        "band_ans_lift": band_rate - ans_rate if len(hb) and n else np.nan,
        "prev_disp": last.disposition_label if n else "none",
        "hrs_since_prev": min(secs.iloc[-1] / 3600, 24 * 60) if n else np.nan,
        "dials_24h": int((secs < 86400).sum()) if n else 0,
        "dials_today": int((h.call_start_time.dt.normalize() == pd.Timestamp(slot).normalize()).sum()) if n else 0,
        "band": band,
    }


def candidate_slots(now, days=HORIZON_DAYS, not_before=None):
    """All dialable hour slots from `now` for `days` days (top of hour, or `now` itself)."""
    start = max(now, not_before) if not_before else now
    out = []
    for d in range(days + 1):
        day = (start + timedelta(days=d)).replace(hour=0, minute=0, second=0, microsecond=0)
        for hr in CALL_HOURS:
            s = day + timedelta(hours=hr)
            if s + timedelta(minutes=59) < start:
                continue
            out.append(max(s, start))
    return out


def build_candidates(hist, profile, now, attempt_no, lead_sent=None, bucket="PUA",
                     bot_version="main_vani", days=HORIZON_DAYS):
    """Feature rows for every candidate slot. History is summarised once (every slot is >= now,
    so the same past dials apply); only slot-dependent fields are computed per slot."""
    slots = candidate_slots(now, days)
    h = hist[hist.call_start_time < pd.Timestamp(now)]
    n = len(h)
    base = {
        "call_attempt_count": attempt_no, "redis_bucket": bucket, "lead_bot_version": bot_version,
        "hist_n": n, "hist_ans_rate": h.ans.mean() if n else np.nan,
        "hist_mf": int(h.mf.sum()) if n else 0, "hist_ni": int(h.ni.sum()) if n else 0,
        "hist_callback": int(h.cb.sum()) if n else 0,
        "hist_episodes": int((h.call_attempt_count == 1).sum()) if n else 0,
        "hist_prev_episode_mf": int(h.mf.sum() > 0) if n else 0,
        "prev_disp": h.disposition_label.iloc[-1] if n else "none", **profile}
    band_stats = h.groupby("band").ans.agg(["size", "mean"]) if n else pd.DataFrame(columns=["size", "mean"])
    t_hist = h.call_start_time.to_numpy() if n else np.array([], dtype="datetime64[ns]")
    rows = []
    for slot in slots:
        ts = np.datetime64(pd.Timestamp(slot))
        band = band_of(slot.hour)
        bn = int(band_stats.loc[band, "size"]) if band in band_stats.index else 0
        br = float(band_stats.loc[band, "mean"]) if bn else np.nan
        secs = (ts - t_hist) / np.timedelta64(1, "s") if n else np.array([])
        rows.append({
            "slot": slot, "hour": slot.hour, "dow": slot.weekday(), "is_weekend": int(slot.weekday() >= 5),
            "trigger_delay_min": (min(max((slot - lead_sent).total_seconds() / 60, 0), 1440)
                                  if attempt_no == 1 and lead_sent is not None else np.nan),
            "band": band, "band_n": bn, "band_ans_rate": br,
            "band_ans_lift": br - base["hist_ans_rate"] if bn and n else np.nan,
            "hrs_since_prev": min(secs[-1] / 3600, 24 * 60) if n else np.nan,
            "dials_24h": int((secs < 86400).sum()) if n else 0,
            "dials_today": int((t_hist.astype("datetime64[D]") == ts.astype("datetime64[D]")).sum()) if n else 0,
        })
    c = pd.DataFrame(rows)
    for k, v in base.items():
        c[k] = v
    return c


def apply_guardrails(c, hist, attempt_no):
    """Mark slots that break the anti-irritation rules."""
    c = c.copy()
    ok = np.ones(len(c), dtype=bool)
    why = np.full(len(c), "", dtype=object)
    gap = c.hrs_since_prev.fillna(1e9)
    m = gap < MIN_GAP_HRS; ok &= ~m; why[m] = "too soon after last dial"
    m = c.dials_24h >= MAX_DIALS_24H; ok &= ~m; why[m & (why == "")] = "3 dials already in 24h"
    c["allowed"], c["blocked_reason"] = ok, why
    return c


def plan_next_call(model, hist, profile, now, attempt_no, lead_sent=None, bucket="PUA",
                   callback_at=None, last_disposition=None, do_not_call=False, signals=None):
    """Return the next action for one seller."""
    if do_not_call:
        return Plan("stop", "Seller asked not to be called.")
    if last_disposition == "Meeting Fixed":
        return Plan("stop", "Meeting already fixed in this episode.")
    if last_disposition == "Not Interested":
        return Plan("stop", "Seller said not interested - wait for a new trigger (cool-off 7 days).")
    if attempt_no > MAX_ATTEMPTS:
        return Plan("stop", f"Episode reached {MAX_ATTEMPTS} attempts; later attempts give ~1% of meetings "
                            "and the highest frustration.")
    c = build_candidates(hist, profile, now, attempt_no, lead_sent, bucket)
    c = score_candidates(model, c)
    c = apply_guardrails(c, hist, attempt_no)
    c = apply_context(c, now, signals or {})
    if callback_at is not None:
        slot = max(callback_at - timedelta(minutes=5), now)
        near = c.iloc[[int((c.slot - slot).abs().argmin())]]
        return Plan("call", "Seller asked for a callback at this time - honour it (dial 5 min early).", slot,
                    float(near.p_meeting.iloc[0]), float(near.p_answer.iloc[0]), c)
    allowed = c[c.allowed]
    if allowed.empty:
        return Plan("stop", "No slot passes the anti-irritation guardrails in the next 48h.", ranked=c)
    if attempt_no == 1:
        best = allowed.iloc[0]
        if best.slot <= now + timedelta(minutes=5):
            reason = ("Fresh lead: call now. Calls placed within 30 s of the trigger answer 65.7% / fix 11.0% "
                      "vs 58.7% / 8.8% when delayed 15-60 min.")
        else:
            reason = "Lead arrived outside the dialing window: call as soon as the window opens (speed-to-lead)."
    else:
        best = allowed.sort_values("score", ascending=False).iloc[0]
        reason = (f"Best time-of-day score x retry-gap factor among allowed slots in the next {HORIZON_DAYS} days.")
        if best.get("warm", False):
            reason += " Seller was active on another channel in the last 3 h (warm moment, x1.08)."
        if (signals or {}).get("exec_answered_24h"):
            reason += " Skipped today: an IndiaMART executive already spoke to the seller."
        if best.p_meeting < STOP_P_MEETING:
            return Plan("stop", f"Best slot in 48h has P(meeting)={best.p_meeting:.1%} < {STOP_P_MEETING:.0%}; "
                                "stop to save dials and avoid irritation.", ranked=c)
    return Plan("call", reason, best.slot.to_pydatetime(), float(best.p_meeting), float(best.p_answer), c)


WARM_HOURS = 3
WARM_FACTOR = 1.08


def apply_context(c, now, signals):
    """Global Context adjustments: warm-moment boost and 'executive already spoke today' block."""
    c = c.copy()
    c["warm"] = False
    mins = signals.get("mins_since_activity")
    if signals.get("warm") and mins is not None:
        until = now + timedelta(minutes=WARM_HOURS * 60 - mins)
        c["warm"] = c.slot <= until
        c.loc[c.warm, "score"] *= WARM_FACTOR
    if signals.get("exec_answered_24h"):
        today = c.slot.dt.normalize() == pd.Timestamp(now).normalize()
        c.loc[today & c.allowed, "blocked_reason"] = "executive already spoke to the seller today"
        c.loc[today, "allowed"] = False
    return c


def score_candidates(model, c):
    """p_meeting/p_answer at each slot (time-of-day only) and the ranking score (x gap factor)."""
    c = c.copy()
    p = model.predict_slot(c)
    c["p_meeting"], c["p_answer"] = p.p_meeting.to_numpy(), p.p_answer.to_numpy()
    gf = np.where(c.hrs_since_prev.isna(), 1.0, model.gap_factor(c.hrs_since_prev.fillna(0)))
    c["gap_factor"] = gf
    c["score"] = c.p_meeting * gf
    return c
