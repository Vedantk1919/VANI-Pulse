"""Per-seller VANI call plan + prompt block.

For one seller GLID this produces:
  1. WHEN  - next dial slot, top windows, retry/stop plan (from policy.plan_next_call)
  2. HOW   - opening hook, tone, pace, language, busy/objection handling, each with the reason
  3. A ready-to-paste prompt block for VANI (Sarvam agent) and a markdown plan file

Run:  python -m src.prompt_gen <glid> [<glid> ...]      (writes outputs/plans/<glid>.md/.json)
"""
import json
import sys
from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from .config import WORK_DIR, PERSONA_DIR, OUT_DIR, TEST_START
from .model import TimingModel
from . import policy

PLAN_DIR = OUT_DIR / "plans"
PLAN_DIR.mkdir(exist_ok=True, parents=True)

PROFILE_COLS = ["seller_state", "business_type", "nature_of_business", "top_category_group",
                "turnover_ord", "gst_registration_year", "num_categories"]

# Evidence used in the reasons (all from the Apr-Sep 2026 data; see README "Findings").
EVIDENCE = {
    "hook_paid": "PIM/PAM leads: 'paid services' opening fixed 26.9% of transcribed calls vs 7.9% with a buyleads opening",
    "hook_buylead": "PUA leads: buyleads opening fixed 28.0% vs 8.7% with a catalog opening",
    "hook_enquiry": "UA leads: a specific number ('80 se zyada buyer inquiry') fixed 26.3% vs 23.0% for a vague 'kuch zyada'",
    "busy": "When the seller says they are busy, meetings halve (13% vs 24%) and 56% end as Call Later",
    "price": "A price question is a buying signal: 37% of those calls fixed a meeting vs 22%",
    "exec": "Sellers already in touch with an executive fix 16% vs 23%",
    "who": "Calls where the seller first asks 'kaun bol raha hai?' fix 16.6% vs 25.1% after a clear confirmation",
    "repeat": "Frustration in transcripts rises from 1.8% (no dial in 24h) to 5.5% (5+ dials); 2.0% on attempt 1 vs 8.9% on attempt 6",
    "time_bug": "Seen in transcripts: 'char se paanch' (4 to 5) was booked as 4:05",
}

EPISODE_RESET_HRS = 72

SOUTH = {"Tamil Nadu", "Karnataka", "Kerala", "Andhra Pradesh", "Telangana", "Puducherry"}
GREETING = {"Gujarat": "Namaste / Kem cho", "Maharashtra": "Namaskar", "Punjab": "Sat Sri Akal ji",
            "West Bengal": "Namaskar", "Tamil Nadu": "Vanakkam", "Karnataka": "Namaskara",
            "Kerala": "Namaskaram", "Telangana": "Namaskaram", "Andhra Pradesh": "Namaskaram"}


@lru_cache(maxsize=1)
def _attempts():
    return pd.read_parquet(WORK_DIR / "attempts_features.parquet")


@lru_cache(maxsize=1)
def _persona():
    cols = ["fk_glusr_usr_id", "seller_city", "annual_turnover", "top_category_1", "eng_pickup_ratio_90d",
            "eng_meetings_1yr", "eng_enq_received_90d", "eng_cqs", "avg_answered_call_sec", "past_objections",
            "past_questions_asked", "asked_if_talking_to_bot", "showed_frustration",
            "already_in_touch_with_executive", "do_not_call_requested", "past_dispositions_detailed"]
    s = pd.concat([pd.read_csv(PERSONA_DIR / f"ps07_seller_files_part{i}.csv", usecols=cols, low_memory=False)
                   for i in (1, 2)])
    return s.drop_duplicates("fk_glusr_usr_id").set_index("fk_glusr_usr_id")


@lru_cache(maxsize=1)
def _model():
    return TimingModel()


def seller_context(glid, now):
    a = _attempts()
    hist = a[(a.fk_glusr_usr_id == glid) & (a.call_start_time < now)].sort_values("call_start_time")
    prof_row = a[a.fk_glusr_usr_id == glid].iloc[-1] if (a.fk_glusr_usr_id == glid).any() else None
    profile = {c: (prof_row[c] if prof_row is not None else np.nan) for c in PROFILE_COLS}
    for c in ("seller_state", "business_type", "nature_of_business", "top_category_group"):
        profile[c] = str(profile[c]) if pd.notna(profile[c]) else "NA"
    p = _persona()
    persona = p.loc[glid].to_dict() if glid in p.index else {}
    return hist, profile, persona


def _episode_state(hist, now):
    """Attempt number of the next dial and last outcome in the current episode."""
    if hist.empty:
        return 1, None, None, None
    last = hist.iloc[-1]
    if (now - last.call_start_time) > pd.Timedelta(hours=EPISODE_RESET_HRS):
        return 1, None, None, last.get("redis_bucket", "PUA")      # old episode is over: treat as a fresh lead
    ep_start = hist[hist.call_attempt_count == 1].call_start_time.max()
    in_ep = hist[hist.call_start_time >= ep_start] if pd.notna(ep_start) else hist
    nxt = int(in_ep.call_attempt_count.max()) + 1
    callback = None
    if last.disposition_label == "Call Later / Busy" and pd.notna(last.lead_tbro_time) and last.lead_tbro_time > now:
        callback = last.lead_tbro_time.to_pydatetime()
    return nxt, last.disposition_label, callback, last.get("redis_bucket", "PUA")


def top_windows(ranked, n=6):
    """Top distinct hour windows from the ranked candidate slots (allowed only)."""
    r = ranked[ranked.allowed].sort_values("score", ascending=False)
    out, seen = [], set()
    for _, x in r.iterrows():
        key = (x.slot.date(), x.slot.hour)
        if key in seen:
            continue
        seen.add(key)
        out.append({"slot": x.slot.strftime("%a %d %b, %I:%M %p"), "hour": int(x.slot.hour),
                    "slot_iso": x.slot.strftime("%Y-%m-%dT%H:%M:%S"),
                    "p_meeting": round(float(x.p_meeting), 4), "p_answer": round(float(x.p_answer), 3)})
        if len(out) == n:
            break
    return out


HINDI_DAYS = ["Somvaar", "Mangalvaar", "Budhvaar", "Guruvaar", "Shukravaar", "Shanivaar", "Ravivaar"]


def hinglish_time(slot, now):
    """'aaj shaam 7 baje' / 'kal dopahar 3 baje' / 'Guruvaar subah 11 baje'."""
    days = (slot.date() - now.date()).days
    day = "aaj" if days == 0 else "kal" if days == 1 else HINDI_DAYS[slot.weekday()]
    h = slot.hour
    part = "subah" if h < 12 else "dopahar" if h < 16 else "shaam" if h < 20 else "raat"
    return f"{day} {part} {h % 12 or 12} baje"


def pick_alternatives(windows, now, n=2):
    """Two offered callback times, at least 2 hours apart, best first."""
    out = []
    for w in windows:
        t = datetime.strptime(w["slot_iso"], "%Y-%m-%dT%H:%M:%S")
        if all(abs((t - o).total_seconds()) >= 7200 for o in out):
            out.append(t)
        if len(out) == n:
            break
    return [hinglish_time(t, now) for t in out]


def conversation_design(profile, persona, hist, bucket, attempt_no, windows, now):
    """Rules -> opening hook, tone, pace, language, handling. Each item carries its reason."""
    d = {}
    city = persona.get("seller_city") or "aapke shehar"
    cat = persona.get("top_category_1") or "aapki category"
    turnover = profile.get("turnover_ord")
    big = (pd.notna(turnover) and turnover >= 3) or profile["business_type"] == "Limited Company"
    new_biz = pd.notna(profile.get("gst_registration_year")) and profile["gst_registration_year"] >= 2023
    dials_24h = int((hist.call_start_time > pd.Timestamp(now) - pd.Timedelta(hours=24)).sum()) if len(hist) else 0
    short_calls = pd.notna(persona.get("avg_answered_call_sec")) and persona["avg_answered_call_sec"] < 20
    frustrated = bool(persona.get("showed_frustration") == 1) or dials_24h >= 2 or attempt_no >= 3

    # 1. Opening hook - matched to the lead trigger
    if bucket in ("PIM", "PAM", "PANF"):
        hook = (f"Main dekh rahi hoon ki aap IndiaMART ki paid services explore kar rahe the. Isi baare mein hamare "
                f"sales executive aapke saath 15-20 minute ki chhoti si meeting karna chahte hain.")
        d["opening_hook"] = (hook, EVIDENCE["hook_paid"])
    elif bucket in ("PUA", "PUT"):
        hook = (f"Aap IndiaMART par buyleads dekh rahe the - {cat} ke liye {city} mein naye buyers aa rahe hain. "
                f"Hamare sales executive aapko inhe convert karne ka tareeka 15-20 minute mein samjha denge.")
        d["opening_hook"] = (hook, EVIDENCE["hook_buylead"])
    else:
        hook = (f"{city} mein {cat} ki category mein {{enquiry_count}} se zyada buyer enquiry aayi hain. "
                f"Isliye hamare sales executive aapse 15-20 minute ki meeting karna chahenge.")
        d["opening_hook"] = (hook, EVIDENCE["hook_enquiry"] + ". Always speak the real number, never 'kuch zyada'.")

    # 2. Tone / formality
    if big:
        d["tone"] = ("Formal and crisp: 'aap', 'sir/madam', business-value framing (more qualified enquiries, ROI). "
                     "No small talk.", "Limited company / turnover >= 5 Cr: lower meeting rate (7.1% vs 9.9% for 0-40 L) and "
                     "lowest 9-10 AM pickup (46%) - respect their time.")
    elif new_biz:
        d["tone"] = ("Warm and encouraging, simple Hinglish, growth framing ('naye buyers tak pahunchne mein madad').",
                     "New businesses (GST 2023+) convert best: 12.7% vs ~8% for older sellers.")
    else:
        d["tone"] = ("Friendly, respectful Hinglish; one benefit, then the meeting ask.",
                     "Default for proprietorship / small traders (the majority of sellers).")
    if frustrated:
        d["tone"] = (d["tone"][0] + " Open by acknowledging earlier calls ('pehle bhi call kiya tha, bas 30 second "
                     "lungi') and get to the ask within 10 seconds.", d["tone"][1] + " | " + EVIDENCE["repeat"])

    # 3. Pace
    if short_calls or frustrated:
        d["pace"] = ("Fast and short: max 2 sentences per turn, ask for the meeting time in the 2nd bot turn. "
                     "TTS pace 1.1.", f"Average answered call {persona.get('avg_answered_call_sec', 'NA')} s / repeat dials.")
    else:
        d["pace"] = ("Normal pace (TTS 1.0), pause after the hook for a reaction.", "No sign of a rushed seller.")

    # 4. Language
    st = profile["seller_state"]
    if st in SOUTH:
        d["language"] = (f"Start in simple English with '{GREETING.get(st, 'Namaste')}'; switch to Hindi only if the seller does.",
                         f"Seller is in {st}.")
    else:
        g = GREETING.get(st, "Namaste")
        d["language"] = (f"Hinglish, greeting '{g}'. Mirror the seller: if they reply in English, continue in English.",
                         f"Seller is in {st}; 99.8% of transcribed seller speech is Roman Hinglish.")

    # 5. Identity line
    d["identity"] = ("If asked 'kaun bol raha hai?' or whether this is a bot: answer in one line - "
                     "'Main IndiaMART ki virtual assistant Payal hoon, aapke account ke liye call kiya hai' - then repeat the ask.",
                     EVIDENCE["who"] + ". Honest disclosure keeps trust.")

    # 6. Busy handling - ties the timing model into the conversation
    alt_txt = " ya ".join(pick_alternatives(windows, now)) or "aaj shaam 6 baje"
    d["busy_handling"] = (f"If the seller is busy/driving: stop the pitch at once and offer two concrete times from the "
                          f"call plan: 'Koi baat nahi - kya main {alt_txt} call karun?'. Save the time as callback.",
                          EVIDENCE["busy"] + ". The offered times are this seller's best predicted windows.")
    d["price_question"] = ("If the seller asks price: give the one-line answer you have, then 'baaki detail executive "
                           "meeting mein samjha denge - kal kis time 15 minute milenge?'", EVIDENCE["price"])
    if persona.get("already_in_touch_with_executive") == 1:
        d["existing_executive"] = ("Seller already talks to an IndiaMART executive: acknowledge it and offer to schedule "
                                   "with the same executive; do not push a new one.", EVIDENCE["exec"])
    d["time_capture"] = ("When the seller gives a range ('char se paanch'), read it back as a range "
                         "('chaar se paanch baje ke beech, theek hai?') before confirming.", EVIDENCE["time_bug"])
    if isinstance(persona.get("past_objections"), str):
        d["past_objections"] = (f"Expect: {persona['past_objections']}. Address the first one up front.",
                                "From this seller's past calls (objections evaluator).")
    return d


def build_prompt(glid, design, plan, windows, profile, persona):
    lines = [
        f"## Seller-specific instructions (GLID {glid})",
        f"- Seller: {persona.get('top_category_1', 'NA')} | {profile['nature_of_business']} | "
        f"{profile['business_type']} | {persona.get('annual_turnover', 'NA')} | {persona.get('seller_city', '')}, {profile['seller_state']}",
        f"- Opening (after confirming the company name): \"{design['opening_hook'][0]}\"",
        f"- Tone: {design['tone'][0]}",
        f"- Pace: {design['pace'][0]}",
        f"- Language: {design['language'][0]}",
        f"- Identity: {design['identity'][0]}",
        f"- If busy: {design['busy_handling'][0]}",
        f"- If price is asked: {design['price_question'][0]}",
        f"- Time capture: {design['time_capture'][0]}",
    ]
    for k in ("existing_executive", "past_objections"):
        if k in design:
            lines.append(f"- {k.replace('_', ' ').capitalize()}: {design[k][0]}")
    lines.append("- Goal: fix a 15-20 minute meeting with the sales executive. Keep the call under 90 seconds.")
    return "\n".join(lines)


def generate(glid, now=None, write=True):
    now = now or datetime.fromisoformat(TEST_START)
    hist, profile, persona = seller_context(glid, now)
    attempt_no, last_disp, callback, bucket = _episode_state(hist, now)
    lead_sent = now if attempt_no == 1 else None
    plan = policy.plan_next_call(_model(), hist, profile, now, attempt_no, lead_sent=lead_sent,
                                 bucket=str(bucket or "PUA"), callback_at=callback, last_disposition=last_disp,
                                 do_not_call=persona.get("do_not_call_requested") == 1)
    windows = top_windows(plan.ranked) if not plan.ranked.empty else []
    design = conversation_design(profile, persona, hist, str(bucket or "PUA"), attempt_no, windows, now)
    prompt = build_prompt(glid, design, plan, windows, profile, persona)
    out = {
        "glid": int(glid), "as_of": now.isoformat(), "attempt_no": attempt_no, "last_disposition": last_disp,
        "lead_type": bucket, "past_dials": int(len(hist)),
        "past_answer_rate": round(float(hist.ans.mean()), 3) if len(hist) else None,
        "when": {"action": plan.action, "reason": plan.reason,
                 "slot": plan.slot.strftime("%a %d %b %Y, %I:%M %p") if plan.slot else None,
                 "p_meeting": plan.p_meeting, "p_answer": plan.p_answer, "top_windows": windows,
                 "retry_rules": {"min_gap_min": int(policy.MIN_GAP_HRS * 60), "max_dials_24h": policy.MAX_DIALS_24H,
                                 "max_attempts": policy.MAX_ATTEMPTS, "stop_below_p_meeting": policy.STOP_P_MEETING}},
        "how": {k: {"instruction": v[0], "reason": v[1]} for k, v in design.items()},
        "vani_prompt_block": prompt,
    }
    if write:
        json.dump(out, open(PLAN_DIR / f"{glid}.json", "w"), indent=2, default=str)
        (PLAN_DIR / f"{glid}.md").write_text(to_markdown(out))
    return out, plan


def to_markdown(o):
    w = o["when"]
    md = [f"# Call plan - seller {o['glid']}", f"_As of {o['as_of']} | next attempt #{o['attempt_no']} | "
          f"lead type {o['lead_type']} | past dials {o['past_dials']} | past answer rate {o['past_answer_rate']}_", "",
          "## When", f"**{w['action'].upper()}** {('at ' + w['slot']) if w['slot'] else ''}", f"- Why: {w['reason']}"]
    if w["p_meeting"] is not None:
        md.append(f"- Predicted: P(answer) {w['p_answer']:.0%}, P(meeting) {w['p_meeting']:.1%}")
    if w["top_windows"]:
        md.append("- Best windows: " + "; ".join(f"{x['slot']} ({x['p_meeting']:.1%})" for x in w["top_windows"][:3]))
    r = w["retry_rules"]
    md += [f"- If not answered: retry by the plan (>= {r['min_gap_min']} min later, max {r['max_dials_24h']} dials/24h, "
           f"stop after {r['max_attempts']} attempts or when P(meeting) < {r['stop_below_p_meeting']:.0%})", "",
           "## How (with reasons)"]
    for k, v in o["how"].items():
        md.append(f"- **{k.replace('_', ' ')}**: {v['instruction']}  \n  _why: {v['reason']}_")
    md += ["", "## VANI prompt block", "```", o["vani_prompt_block"], "```"]
    return "\n".join(md)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python -m src.prompt_gen <glid> [<glid> ...]")
    ids = [int(x) for x in sys.argv[1:]]
    for g in ids:
        o, _ = generate(g)
        print(to_markdown(o), "\n")
