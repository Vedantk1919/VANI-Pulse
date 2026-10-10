# VANI: Best Time to Call

IndiaMART Voice AI Hackathon 2.0, **Problem 3: Best Time to Call**.

For every seller, the agent decides:

- **When** to dial: the best hour slot, how to retry when the seller doesn't pick up, and when to stop.
- **How** VANI should run the call: opening hook, tone, pace, language, and how to handle "busy", price questions and time capture.
- **Live adaptation** during the call: if the seller sounds irritated, rushed or confused, or switches language, VANI changes style straight away (apologise and offer a callback / ask for the time directly / simplify / continue in the seller's language).

Each decision comes with the evidence behind it. The output is a seller-specific prompt block for the VANI agent on Sarvam, plus a call plan for the dialer.

## Results on held-out September 2026 (trained on Apr–Aug)

| | Current schedule | Our policy |
|---|---|---|
| Dials | 124,779 | **102,898 (−17.5%)** |
| Meetings fixed | 7,383 | **~7,482 (+1.3%, estimated)** |
| Calls per meeting | 16.9 | **13.8 (−19%)** |
| Dials to a seller already called 3+ times in 24h | 60,585 | **0** |
| Connect rate | 55.7% | 56.0% |

**How these numbers are built:**

1. **Stop and anti-irritation rules.** These are replayed on the actual September call sequences, with no model assumptions. A dial the policy skips loses whatever it produced. Result: 17.5% fewer dials and 96.2% of meetings kept.
2. **Re-timing retries.** Each remaining retry moves to its best same-day slot, and hourly dialer capacity is capped at 1.15× today's volume. This adds +6.8% expected meetings, a model estimate.
3. **The freed dials** (~21.9k a month) can go to fresh leads, where first attempts fix ~10%. We don't count that gain in the table.

**Is the time-of-day model real? We checked it on actual outcomes.** Each September call is scored by how good its actual hour was compared with the same call's average over all hours, so seller effects cancel out. The observed meeting rate rises with that score:

| | Best vs worst slot-quality quintile | 95% bootstrap CI |
|---|---|---|
| First attempts | **+21.9%** meeting rate | +12.8% to +32.3% |
| Retries | **+93%** meeting rate | +70% to +120% |

**Model quality** (September, out of time). Production model = mean of LightGBM, XGBoost and CatBoost:

| Model | AUC | Top decile | Bottom decile |
|---|---|---|---|
| P(meeting) | 0.754 | 18.4% | 0.7% |
| P(answer) | 0.708 | 80% | 20% |

**Model bake-off.** Five candidates were trained on the same features with the same split (`python -m src.compare_models`, results in `outputs/model_comparison.csv`):

| Model | Meeting AUC | Meeting log-loss | Answer AUC |
|---|---|---|---|
| Logistic regression | 0.746 | 0.2032 | 0.699 |
| LightGBM | 0.7525 | 0.2016 | 0.708 |
| XGBoost | 0.7517 | 0.2017 | 0.707 |
| CatBoost | 0.7513 | 0.2019 | 0.708 |
| **Ensemble (production)** | **0.754** | **0.2013** | **0.7085** |

The ensemble is best on every accuracy metric, by a small margin. The three boosted models are statistically tied on slot ranking. Logistic regression is clearly weaker at ranking retry slots.

## Problem 3 brief: how each requirement is met

| Brief requirement | Where |
|---|---|
| 3.1 Ranked call windows per seller (hour × day of week, with scores) | `python -m src.windows <GLID>` and the dashboard; `src/windows.py::weekly_windows` |
| 3.1 Little or no history | Segment features (state, category, turnover, business type, GST year) carry new sellers. Model AUC by past dials: 0 (new): 0.6231, 1-2: 0.6963, 3-5: 0.7108, 6+: 0.7434; calibrated in every group. A seller's top-3 windows overlap ~66% between half and full history, so windows are stable even for new sellers |
| 3.2 Retry delay per attempt, and when to stop | `retry_ladder()`: the full plan if calls keep going unanswered, with gap curve, guardrails and stop rule |
| 3.3 Evidence and verdict on the 15-minute rule | **[RECOMMENDATION.md](RECOMMENDATION.md)**: **CHANGE** |
| 3.4 Optimise for meetings fixed; handle imbalance | The target is `meeting_fixed` (5.9% of dials). We predict calibrated probabilities with log-loss (no resampling, which would distort the probabilities the stop rule relies on) and judge on AUC, PR-AUC, top-decile lift, calibration and per-tier meeting rates. `meeting_done` isn't in the data; quality is checked with the `incorrect_mf` evaluator |
| 3.5 Time-based split, bias from the old schedule, lift on held-out data | Train Apr–Aug, test September; slot-quality check on real outcomes; off-policy IPS: +17.9% (CI 3.4 to 35.9) |
| FAQ Q2 time zone | All sellers assumed to be on IST; state and city are features |
| One-slide presentation | `presentation/best_time_to_call_one_slide.pptx` (rebuild: `python presentation/make_slide.py`) |

## Global Context: memory across channels (Problem 2, integrated)

Before each call, VANI loads a short **`seller.md`** for the seller (about 260 tokens). It's built from a single event timeline that combines enquiries, enquiry replies, buyer calls, buyleads, WhatsApp messages and chatbot chats, past VANI calls and executive calls. The data is the Global Context sample: 5,000 sellers, Apr–Oct 2026. Raw message text and phone numbers are never copied; only counts, products, cities, intents and scrubbed call outcomes.

**`seller.md` sections:**
- **Who:** location, business type, turnover, what they sell and buy.
- **Open threads:** promised callbacks, meetings already fixed, executive contact, unread enquiries, missed buyer calls.
- **Business activity:** enquiries, buyer calls, WhatsApp.
- **Last 3 conversations** on any channel.
- **Best time to call:** from the timing model.
- **Signals:** flags such as frustration or do-not-call.

**How the two problems feed each other:**

| Direction | What happens |
|---|---|
| Memory → prompt | The opening uses real numbers ("Pichhle 30 din mein Steel Racks ke liye 12 enquiry, zyada tar Pune se, 4 abhi tak padhi nahi gayi"), plus a "What you already know" section and a "don't re-ask" rule |
| Memory → timing | **Warm moment:** if the seller was active on another channel in the last 3h, slots in that window get ×1.08. **Executive spoke today:** VANI skips the day. **Callback from the last call:** the planner dials at that time |
| Timing → memory | The "Best time to call" section of `seller.md`, reusable by executives and the WhatsApp bot |
| Call → memory | VANI writes the outcome, summary and callback back to the timeline, and `seller.md` updates at once |

**Which context signals change *when* to call?** Tested on 18,600 VANI dials to these sellers (`src/gc_validation.py`):

| Signal | Result | Used? |
|---|---|---|
| Active on another channel ≤3h before the call | **+4.4 points pickup within the same seller** (95% CI +1.1 to +8.1, 639 sellers) | Yes, ×1.08 boost |
| Active ≤60 min before | +1.1 points (CI −3.4 to +4.9): not significant | No |
| WhatsApp pushes in the previous 24h | No drop in pickup, fewer "Not Interested" | Not counted as irritation |
| Executive call in the previous 24h | Only 4 cases: can't be tested | Cautious rule: skip that day |
| Seller's usual activity hour | Flat pickup | No |

**Quality of `seller.md`** (all 5,000 sellers, as of 30 Sep; `src/gc_eval.py`):

| Measure | Result |
|---|---|
| Size | median ~260 tokens (p95 ~350) |
| Build time | ~23 ms |
| Freshness | ~37 ms from write-back to an updated file |
| Openings with real numbers | 16% of sellers (the rest fall back to the lead-type opening) |
| Files with open threads | 23% |

**Lookback is 90 days, with a 7-day "new" view.** At 90 days, 78% of sellers have their own activity and 64% of all events are covered. 30 days covers only 57% of sellers; 180 days doubles the file content for little extra coverage.

**Limits:**
- The personalised opening has no measured lift on meetings yet, because no past calls used it. The evidence is indirect: specific numbers fixed 26.3% vs 23.0% in transcripts. It needs an A/B test.
- Coverage is the 5,000 sample sellers; everyone else gets the standard prompt.

## Scheduler spec alignment (allocator, tiers, production prompt)

**Same dials, better slots.** With exactly the dials actually made in each hour of September, re-timing retries gives **+6.6% meetings** (model estimate). This is the spec's "Δ meetings at equal dials" metric.

**Lead tiers.** Each lead gets a tier from its predicted P(meeting) per dial. Cut points are learned on Apr–Aug: A is the top 10%, B the next 20%, C the next 30%, D the rest. On September:

| Tier | Share of dials | Share of meetings | Meeting rate |
|---|---|---|---|
| A | 9.7% | 30.4% | 18.6% |
| B | 16.2% | 29.9% | 10.9% |
| C | 27.1% | 24.9% | 5.4% |
| D | 47.1% | 14.8% | 1.9% |

**Batch allocator** (`src/allocator.py`). It scores a whole queue of leads × 48h of slots in one batch, applies the guardrails and Global Context signals, then fills hourly dialer capacity greedily. On 300 real leads it takes **13.6 ms per lead** (target: under 50 ms). One seller scored on its own takes ~74 ms, so production should plan in batches.

**Meeting label checked.** The `incorrect_mf` evaluator re-read 18,457 "meeting fixed" calls. **2.4% were not real meetings**, and the rate is flat by hour (2.0–2.7%) and attempt number (2.2–3.0%). With the corrected label, September AUC stays 0.7539 and the hour ranking is unchanged (correlation 1.0), so the timing advice holds.

**Production prompt.** `templates/vani_scheduler_blocks.j2` plugs into the existing Jinja2 VANI prompt. The planner outputs the variables: `attempt_no`, `prior_disposition`, `hours_since_last`, `past_objection_top`, `seller_frustrated`, `already_with_exec`, `dnc_requested`, `tier`, `callback_time`, `callback_offer`, `opening_hook`, `what_you_know`, and others. The template adds:

- **An opening based on the last call's outcome.** Meeting rate per answered call: fresh lead 18.6%, after Not Answered 10.8%, after Call Later 8.0%, after a talk with no result 3.6%, attempt 4+ 4.3%.
  - Callback → reference it and skip the introduction.
  - Dropped or unfinished talk → don't re-pitch.
  - Attempt 4+ → acknowledge the repeat calls and offer an opt-out.
- **A Hinglish "nahi" guard.** "nahi" appears in 54% of calls that fixed a meeting (0.94× lift), so it never ends a call by itself. The real negatives are "interest/zaroorat nahi" (0.31×), deferral (0.48×) and "call mat karo" (0.37×).

**Where we differ from the spec:**
- **Do-not-call stays a hard stop.** The spec suggests up to 3 more calls after a seller asks not to be called. That conflicts with the seller's explicit request and with do-not-disturb rules, and it would add about 14 meetings over six months.
- **No blanket "shorter opening at midday".** 73% of answered calls at midday are retries, against 41% at other hours. On first calls there's no midday dip (16.6% vs 16.2%); only late retries do badly at midday, and the planner already handles that.

## Recommendation on the 15-minute rule

Today an unanswered call is redialled after a fixed 15 minutes. The data shows these redials do little, and repeated dials irritate sellers. **Replace the rule with:**

1. **No redial within 30 minutes.** Answered redials under 30 minutes fix meetings 2.5–3.2% of the time, against 11.5% when the gap is 1–2 hours.
2. **Retry on the same day, 1–2 hours or 4–8 hours later, in the seller's best-scoring slot.** A next-day retry is worth about half: the meeting factor is 0.5 for 8–24 hours and 0.37 for 24–48 hours.
3. **At most 3 dials per seller in any 24 hours.** The meeting rate per answered call drops from 18.6% with no prior dial to 7.4% after 3. Frustration in transcripts rises from 1.8% to 5.5%.
4. **At most 5 attempts per lead, and stop early when P(meeting) < 1%.** Attempts 6 and later produce 1.2% of all meetings.
5. **When a seller says "Call Later", call at the time they asked for**, 5 minutes early. When a seller says they're busy, VANI offers two concrete times taken from that seller's best windows.

The evidence tables are in the dashboard ("15-minute rule" tab) and in `outputs/backtest_report.json`.

## Key findings (Apr–Sep 2026: 530k attempts, 149k sellers)

- **Most meetings come early.** 68% of meetings are fixed on attempt 1 and 93% by attempt 3. It takes about 17 dials to get one meeting.
- **Evening is the best time; 9 AM is the worst.** On first attempts, 6–9 PM fixes 11.8–12.8% against 8.4% at 9–10 AM. The raw data shows a dip at 11 AM (3.1%), but that comes from retries piling up at that hour, not from the hour itself.
- **Speed to lead matters.** Calls placed within 30 seconds of the trigger: 65.7% answered, 11.0% meetings. Calls 15–60 minutes late: 58.7% and 8.8%.
- **Segments change how many sellers convert more than when they convert:**
  - New businesses (GST 2023+) fix 12.7%, against about 8% for older ones.
  - Meeting rate falls as turnover rises.
  - Limited companies pick up only 46% at 9 AM.
  - UP, MP and Rajasthan convert best; Delhi lowest.
- **A seller's own history predicts pickup** (23% → 75%), **but not meetings.** History is thin (median 2 dials per seller), so the model blends segment-level and seller-level signals.
- **Conversation** (12.8k transcripts):
  - **Match the opening hook to the lead type.** PIM leads given a "paid services" opening fixed 26.9%; given a buyleads opening, 7.9%.
  - **Use the real enquiry count.** A specific number beats a vague "kuch zyada".
  - **"Busy" halves the meeting rate.**
  - **A price question is a buying signal:** 37% of those calls fix a meeting, against 22%.

**Tested and not supported:** moving the overnight 9 AM backlog of fresh leads to later hours. Overnight leads called at 10 AM or later did no better, so the policy still calls fresh leads immediately. This is a candidate for an A/B test.

## How it works

```
attempts + seller profile ──► features.py   leakage-free history features (only past calls)
                              model.py      ensemble (LightGBM+XGBoost+CatBoost) P(answer), P(meeting) + retry-gap curve
                              compare_models.py  5-model bake-off on the same split
                              policy.py     candidate slots (48 h) → guardrails → best slot / stop
                              prompt_gen.py hook, tone, pace, language, objections → VANI prompt block
                              backtest.py   September replay + empirical validation
                              timeline.py   Global Context: one event timeline per GLID across channels
                              seller_md.py  seller.md (memory) + timing signals + write-back
                              gc_validation.py / gc_eval.py   context-signal tests, seller.md quality
                              allocator.py  batch allocator: lead queue x slots under hourly capacity, tiers A-D
                              label_check.py meeting-label robustness (incorrect_mf evaluator)
                              templates/vani_scheduler_blocks.j2  Jinja2 blocks for the production VANI prompt
                              app.py        dashboard (plan + seller.md · backtest · 15-min rule · global context · model)
                              sarvam.py     speaks the opening via Sarvam Bulbul at the persona's pace
```

**Design choice.** The model ranks **time of day** only. Lead delay and retry gap are pinned to reference values while scoring, because those two features reflect how the current scheduler behaves and don't extrapolate safely. Speed-to-lead and the retry gap are explicit, data-derived rules instead.

**Data that stays out of the model.** The seller-file engagement fields (`eng_*`, past objections) are snapshots taken at the end of September. They are used only for conversation design, never in the timing model, to avoid leakage.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run_all.sh                          # features → model → backtest → sample plans  (~7 min)
.venv/bin/python -m src.prompt_gen <GLID>         # plan for one seller → outputs/plans/<GLID>.md
SARVAM_API_KEY=... .venv/bin/streamlit run app.py # dashboard (audio needs the key)
```

**Data locations:**

- The `BesTime to Call` CSVs are read from `../Aids to solve Problems/BesTime to Call/`. Override with `BTC_RAW_DIR`.
- The persona files are read from `data/persona/`. Override with `BTC_PERSONA_DIR`.
- The Global Context seller files are read from `data/gc/`. Override with `BTC_GC_DIR`.
- Seller data is internal to IndiaMART: don't copy `data/` or `outputs/plans/` off premises.

## Demo dashboard

```bash
.venv/bin/streamlit run app.py
```

The pages follow the demo story:

1. **Overview:** the problem, what we built, headline KPIs and an architecture diagram.
2. **What the data says:** six charts from 530k dials and a table of transcript findings.
3. **Demo sellers:** 10 curated real sellers, one per scenario. Each has a profile, every dial and other-channel activity, the plan with blocked slots, weekly windows, the retry ladder, *before vs after* (what the current system did next vs our plan), `seller.md`, the VANI prompt with the reason for each instruction, and a write-back demo.
4. **Talk to VANI:** a live Sarvam chat seeded with the selected seller's prompt, one-click test lines with the behaviour to expect, a transcript download, and "Speak opening" (Bulbul TTS).
5. **Results & validation:** backtest, 15-minute verdict, model comparison and checks, Global Context tests.

**🎬 Recording mode** (sidebar) hides company, product and buyer-city names and GLIDs on screen. Direct links: `?p=3&s=1` opens page 3 with demo seller 1. See **[DEMO_SCRIPT.md](DEMO_SCRIPT.md)** for a minute-by-minute video script.

## Test the VANI agent on Sarvam with any GLID (no hosting)

`src/sarvam_live.py` builds the chosen seller's plan and prompt block locally. It then starts a Sarvam session with the block passed in as agent variables, using Sarvam's conversation SDK.

1. **Create the agent on Sarvam.** On indus.sarvam.ai, create an agent and use `outputs/sarvam_test/agent_base_prompt.md` as its prompt. On the Variables tab, add `seller_block` and `company_name`, then commit a version.
2. **Set the credentials:**
   ```bash
   export SARVAM_API_KEY=... SARVAM_ORG_ID=... SARVAM_WORKSPACE_ID=... SARVAM_APP_ID=...
   ```
3. **Run it:**
   ```bash
   .venv/bin/python -m src.sarvam_live <GLID> --at 2026-09-18T19:38            # dry run: shows the plan and variables
   .venv/bin/python -m src.sarvam_live <GLID> --at ... --mode chat             # type as the seller
   .venv/bin/python -m src.sarvam_live <GLID> --at ... --mode script           # 11-line test conversation, saves transcript
   .venv/bin/python -m src.sarvam_live <GLID> --at ... --mode call             # voice via laptop mic (needs PyAudio/PortAudio)
   ```
   Use `--company "Made-up Name"` when recording a demo.

**Hosting is only needed for production.** Sarvam's on-start hook would fetch the seller block at call time, so the planner would run as an internal IndiaMART service; seller data must not go to a public host.

## Outputs

| Path | What it holds |
|---|---|
| `outputs/plans/*.md`, `*.json` | Sample per-seller call plans and VANI prompt blocks (see `INDEX.md`) |
| `outputs/vani_agent_prompt_template.md` | Base VANI agent prompt with the `{{seller_block}}` slot |
| `outputs/backtest_report.json` | Backtest results, empirical validation and 15-minute-rule evidence |
| `outputs/retry_policy_grid.csv` | Trade-off grid for the stop rules |
| `outputs/model_report.json` | AUC, calibration and feature importance |
| `outputs/model_comparison.csv` | Model bake-off results |
| `outputs/seller_md/*.md` | Sample seller.md files |
| `outputs/gc_validation.json`, `outputs/gc_eval.json` | Context-signal tests and seller.md quality |
