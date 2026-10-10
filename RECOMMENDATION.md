# Recommendation: the 15-minute rule

## Verdict: CHANGE

Replace the fixed 15-minute redial with four rules:

1. **No redial within 30 minutes.** Redials under 30 minutes after a no-answer fix meetings 0–3% of the time, against 3–5% at 30 minutes to 2 hours. This holds in **every** segment we checked: business type, turnover and lead type. There's no segment where a short redial works, so we recommend **change**, not "supplement".
2. **Retry on the same day, 1–2 hours or 4–8 hours later, in the seller's best-scored slot.** A next-day retry is worth about half (factor 0.37–0.5).
3. **At most 3 dials per seller in any 24 hours and 5 attempts per lead; stop early when P(meeting) < 1%.**
4. **"Call Later" means call at the time the seller asked for.** When a seller is busy, VANI offers that seller's two best predicted windows.

## Evidence (held-out September 2026, 124,779 dials)

| | Current schedule | Model schedule |
|---|---|---|
| Dials | 124,779 | 102,898 (-17.5%) |
| Meetings fixed | 7,383 | ~7,482 (+1.3%) |
| Calls per meeting | 16.9 | **13.75** |
| Connect rate | 55.7% | 56.0% |
| Meetings at equal dials per hour | — | **+6.6%** (model estimate) |

**The trade-off:** tighter stop rules save more dials but lose more meetings. A 4-attempt cap with a 1.5% threshold saves 34% of dials and keeps 88% of meetings. Our default saves 17.5% and keeps 96.2%. The full grid is in `outputs/retry_policy_grid.csv`.

## Why we trust it

The data was logged under the old schedule, so we checked the results three separate ways:

- **Time split.** We trained on Apr–Aug and tested on September, with no shuffling. Volume grew ~6.6× and conversion fell, so a random split would leak.
- **Calls that happened at different times.** We scored each September call by how good its actual hour was compared with the same call's other hours. Calls in the best fifth beat the worst fifth by **+21.9%** (first calls; 95% CI 12.8 to 32.3) and **+93.2%** (retries; CI 69.9 to 120.3).
- **Off-policy check (inverse-propensity weighting).** We modelled how likely each hour was under the old schedule and reweighted. Moving retries to their best hour gives **+17.9%** meetings (95% CI 3.4 to 35.9; effective sample size 5,122).

## Limits
- **The re-timing lift is estimated, not randomised.** Untried options can't be priced: there are only 330 retries under 15 minutes, and holding calls to the evening was rare. Next step: a 5% A/B test.
- **Freed dials only help if there are leads to use them.** We don't credit that capacity in the meeting numbers.
- **Assumptions:** one time zone (IST) for all sellers, with state and city used as features. `meeting_done` wasn't in the data, so meeting quality was checked with the `incorrect_mf` evaluator instead: 2.4% false meetings, flat by hour, with AUC and hour ranking unchanged.
- **We assume the 15-minute rule is the vendor's redial *inside* one logged attempt** (dial-to-report times peak at about 7 and 22 minutes), because logged retries are 45+ minutes apart. To be confirmed by the organisers.
