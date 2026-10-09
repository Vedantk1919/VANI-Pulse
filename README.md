# VANI: Best Time to Call

IndiaMART Voice AI Hackathon 2.0, **Problem 3: Best Time to Call**.

For every seller, the agent decides:

- **When** to dial: the best hour slot, how to retry when the seller doesn't pick up, and when to stop.
- **How** VANI should run the call: opening hook, tone, pace, language, and how to handle "busy", price questions and time capture.

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
                              app.py        dashboard (plan · backtest · 15-min rule · model)
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
- Seller data is internal to IndiaMART: don't copy `data/` or `outputs/plans/` off premises.

## Outputs

| Path | What it holds |
|---|---|
| `outputs/plans/*.md`, `*.json` | Sample per-seller call plans and VANI prompt blocks (see `INDEX.md`) |
| `outputs/vani_agent_prompt_template.md` | Base VANI agent prompt with the `{{seller_block}}` slot |
| `outputs/backtest_report.json` | Backtest results, empirical validation and 15-minute-rule evidence |
| `outputs/retry_policy_grid.csv` | Trade-off grid for the stop rules |
| `outputs/model_report.json` | AUC, calibration and feature importance |
| `outputs/model_comparison.csv` | Model bake-off results |
