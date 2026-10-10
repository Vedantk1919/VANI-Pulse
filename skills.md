# skills.md: VANI Pulse build journey

## Tools

- **Python 3.12:** pandas, NumPy, PyArrow
- **LightGBM, XGBoost, CatBoost:** ensemble for the two binary models, P(answer) and P(meeting); logistic regression as a baseline
- **scikit-learn:** AUC and log-loss
- **Streamlit + Altair:** dashboard
- **Sarvam AI:** Bulbul v3 text-to-speech speaks the seller-specific opening at the persona's pace; the VANI agent runs on the Sarvam Voice Agent platform using `outputs/vani_agent_prompt_template.md`
- **Claude Code (AI pair-programmer):** data exploration, code and documentation

## Journey

1. **Understand the problem.** Problem 3 is scored on lift in **meetings fixed** (not connect rate) on held-out data, plus connect rate, calls per meeting, validation soundness and a defensible verdict on the 15-minute rule. So we optimised P(meeting) per dial and used a strict time-based split: train on Apr–Aug, test on September.

2. **Explore the data** (530k attempts, 149k sellers, plus 12.8k transcripts from the persona dataset).
   - 68% of meetings come on attempt 1.
   - Evening is best; 9 AM is worst.
   - The 11 AM dip is a retry-mix artifact, not an hour effect.
   - Speed to lead matters.
   - Irritation is measurable: frustration phrases in transcripts rise with dials per 24h and with attempt number.

3. **Build features with no leakage.** All history features (pickup rate, pickup rate in the same hour band, dials in the last 24h, hours since the last dial, previous outcome) come from earlier calls only. The seller-file engagement fields are end-of-September snapshots, so we kept them out of the model.

4. **First backtest: a failure we caught.** The model-based re-timing looked like +6%. But an empirical check showed that calls which happened to land in the model's top hours did **worse** (−4%). The cause: when we shifted the hour, we also shifted "minutes since lead" and "hours since last dial". Those features reflect how the current scheduler behaves, so the model can't extrapolate them.

5. **Fix.**
   - The model now scores **time of day only**, with delay and gap pinned to reference values.
   - Retry spacing became an explicit, data-derived gap curve, with thin buckets shrunk toward their neighbours.
   - With that change, the empirical check turned clearly positive on real September outcomes. The best-scored slots convert +21.9% better on first attempts (95% CI +13% to +32%) and +93% better on retries (95% CI +70% to +120%).

6. **Model bake-off.** We compared logistic regression, LightGBM, XGBoost, CatBoost and an ensemble on the same split.
   - The ensemble won every accuracy metric (meeting AUC 0.754 vs 0.746–0.7525), but the margin over single boosted models is small: the data is the limit, not the algorithm.
   - We added bootstrap confidence intervals to the slot check after noticing it moved by about ±10 points between LightGBM reruns.
   - The ensemble went to production because it is the most accurate and the most stable.

7. **Test a hypothesis and drop it.** "Move the 9 AM overnight backlog to later hours" had no support in the data, so we left it out and listed it as an A/B candidate.

8. **Retry and stop policy.** We replayed the actual September sequences under a grid of rules (max attempts, P(meeting) stop threshold, stop after Not Interested, 30-minute minimum gap, 3 dials per 24h). Default chosen: 5 attempts and a 1% threshold, which cuts 17.5% of dials and keeps 96.2% of meetings. A 60-minute minimum gap was also tested: it cost 5% of meetings, because redials 30–60 minutes after a no-answer still convert at 4%. So the threshold stays at 30 minutes.

9. **Conversation design.** From transcripts we matched the opening hook to the lead type (PIM: "paid services" fixed 26.9% vs 7.9% with a buyleads opening), and measured the cost of "busy", the buying signal of a price question, and the effect of an unclear identity line. Each instruction in the generated prompt block carries its evidence. We also tied the timing model into the conversation: when a seller is busy, VANI offers that seller's two best predicted windows as callback times. Finally we added live-adaptation rules to the prompt: irritated → apologise once and offer a callback, rushed → ask for the time directly, language switch → follow the seller, confused → simplify. The voice (speaker, pace) is chosen per seller before the call; the style adapts turn by turn.

10. **Global Context (Problem 2) integrated.** We combined 11 source files into one event timeline per seller (400k events, 5,000 sellers), with no raw message text, because enquiry replies contain phone numbers. From it we build a ~260-token `seller.md`. Then we tested which context signals should change *when* VANI calls, using the same within-seller method as before:
   - Activity on another channel in the last 3h → +4.4 points pickup (95% CI +1.1 to +8.1). We use this as a small boost.
   - Within 60 minutes alone, the effect wasn't significant.
   - WhatsApp pushes don't irritate sellers.
   - The seller's usual activity hour doesn't matter.
   - Executive calls were too rare to test, so we kept a cautious "skip today" rule and labelled it as such.
   The prompt now opens with real numbers and never re-asks what's known. VANI writes each call result back, and `seller.md` updates in ~37 ms, so a callback promised on the call is honoured by the planner.

11. **Checked against the PM's scheduler spec.** We adopted:
    - the equal-dials metric (+6.6%)
    - lead tiers A–D (Tier D: 47% of dials, 15% of meetings)
    - a batch allocator (13.6 ms per lead)
    - variables for the production Jinja2 prompt
    - openings based on the last call's outcome
    - the Hinglish "nahi" guard, verified on our transcripts (0.94× lift)
    - the `incorrect_mf` label check (2.4% false meetings, flat across hours, so the AUC and the hour ranking are unchanged)

    We tested two of the spec's points and kept our own version:
    - Do-not-call stays a hard stop.
    - The "midday dip" turned out to be mostly a retry-mix effect: no dip on first calls.

12. **Sarvam integration under a constraint.** We connected Claude Code to Sarvam's MCP server and configured the agents from the editor:
    - language identification "always" with Hindi + English (the default "once" locked the language, so "yeah tell me" got Hindi)
    - an English-authored flow and a female bilingual voice
    - text-chat tests through the connector, then committed versions

    The only API key available was an `sk_` developer key, which the agents runtime rejects ("Invalid API key format"). So the dashboard runs VANI on Sarvam's developer APIs instead: Saaras STT → Sarvam LLM (`sarvam-105b-conversations`) with the same prompt → Bulbul TTS. It detects the language on every turn ourselves and rewrites any English reply that slips into Hindi. Median reply is about 0.4 s, and all 11 test behaviours pass.

13. **Package.** The deliverables are the dashboard, sample plans for 6 contrasting sellers, the backtest report, the 15-minute-rule recommendation and the Sarvam agent prompt template.

## Limits and next steps

- **The re-timing lift is a model estimate.** It is backed by the empirical quintile check, but it is not a randomised result. The next step is to A/B it with 10% of traffic (Problem 5's framework).
- **Seller-level history is thin** (median 2 dials per seller). Seller-specific windows will sharpen as more history arrives.
- **Freed dial capacity isn't credited** in the meeting numbers.
- **The personalised `seller.md` opening has no measured lift yet.** It needs an A/B test. Global Context covers the 5,000 sample sellers only.
