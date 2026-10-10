# Demo video script: Best Time to Call (Problem 3)

**Length:** about 6 min 45 s (the rules ask for 5 to 7 minutes).
**Speakers:** three. Put your names in for these roles:

| Role | Who | Speaks in |
|---|---|---|
| **A: Screen driver** | the person at the laptop (tech) | Scenes 3, 4, 5, 6, and plays the seller in the live call |
| **B: Business voice** | the non-tech member | Scenes 0, 1, 8 |
| **C: Model voice** | second tech member | Scenes 2, 7 |

The judges score five things. Each scene is tagged with the one it serves, so nothing is left out:
**Business Impact 25%** · **Solution Completeness 20%** · **Technical Robustness 20%** · **Voice Experience 20%** · **Demo & skills.md 15%**.

---

## Before you press record (15 minutes)

1. **Network:** use a network that reaches Sarvam. Check by opening https://api.sarvam.ai in the browser; a page or error page should appear quickly. The Airtel Wi-Fi blocked it earlier today.
2. **Start the dashboard** in a terminal:
   ```
   cd vani_best_time
   ./start_dashboard.sh
   ```
   Paste the `sk_…` key, then the `sk_samvaad_…` key, when it asks.
3. Open **http://localhost:8601** in Chrome. It has to be *localhost*, or the microphone is blocked.
4. **Warm up:** click through pages 1 to 8 once, and open demo sellers 1, 5, 7 and 9 on page 5. The first load of each takes up to 20 s; you don't want that wait on camera.
5. **Pick the live-call seller now:** on page 4, under **Suggestions**, choose a GLID from *"Has seller memory (Global Context)"*. Its opening line will have real enquiry counts. Write the number on a sticky note; don't put it in any file.
6. On page 5 → seller 1 → **Prompt & memory**, press **Clear demo write-backs**.
7. **Sidebar:** switch on **🎬 Recording mode**. It hides real company names, products, buyer cities and GLIDs.
8. **Do one full test call** in Scene 5 below, so you know the voice works on this network.
9. **Screen:** Chrome full screen (F11), zoom 90%, notifications off, other tabs closed.
10. **Audio:** person A wears **headphones with a mic**, so VANI's voice doesn't feed back into the mic. Use the screen recorder at 1080p and record system audio too, so VANI's voice is in the video.

**Recording tip:** record each scene as a separate clip and join them afterwards. A mistake then costs one scene, not the whole video. Speak a little slower than normal.

---

## Scene 0: Opening (0:00–0:20) · B speaks · *Demo*

**Screen:** page **1 · Overview**, scrolled to the top.

**B says:**
> "Hi, we are team ______. We picked Problem 3, Best Time to Call, for VANI, IndiaMART's voice bot that calls sellers to fix meetings. In the next six minutes we'll show what is wrong with the current calling schedule, what our model found in the data, and VANI calling a seller live on Sarvam with a plan built for that one seller."

---

## Scene 1: The problem (0:20–0:55) · B speaks · *Business Impact*

**Screen:** stay on **Overview**. **A** moves the mouse slowly over the KPI row as B talks about each number.

**B says:**
> "Today VANI calls every seller on a fixed schedule. If the seller doesn't pick up, it redials after exactly 15 minutes, again and again. That costs about **17 calls for every meeting fixed**, and sellers get irritated by back-to-back calls.
> Nobody knew whether the 15-minute rule was right. And optimising for pickups is not enough: a pickup that doesn't lead to a meeting is a wasted call. So we optimised for **meetings fixed**, not connect rate."

**A points at:** the *calls per meeting* KPI, then the **CHANGE** verdict.

**B says:**
> "Our answer on the 15-minute rule is: **change it**. Here's why."

---

## Scene 2: What the data says (0:55–1:40) · C speaks · *Technical Robustness*

**Screen:** page **2 · What the data says**. **A** scrolls one chart at a time, pausing on each while C speaks.

**C says:**
> "We used all 530,000 call attempts from April to September, for about 149,000 sellers. Four things stood out.
> **One:** evenings convert best. Calls after 5 PM fix more meetings, and 9 AM is the weakest slot.
> **Two:** most meetings come from the *first* call. Retries matter, but each one is worth less.
> **Three:** redials within 30 minutes perform worst of all, in every segment we checked. That is exactly what the 15-minute rule does.
> **Four:** the more often a seller is dialled, the more frustrated the transcripts get.
> And one learning for the voice side: a seller saying 'nahi' is often not a refusal, so VANI must not hang up on the first 'nahi'."

---

## Scene 3: Best time to call and the new retry rule (1:40–2:40) · A speaks · *Business Impact*

**Screen:** page **3 · Best time to call & 15-min rule**.

**A does and says:**

1. *(Heatmap at the top)*
   > "This is when sellers actually agree to meetings: day of week against hour. Evening is best on every day. One exception: limited companies answer better in the late morning, 10 to 12, so the plan differs by seller type."
2. *(Scroll to the red vs green bars)*
   > "Here is the 15-minute rule in red against our retry gaps in green. Retrying after 1 to 2 hours, or 4 to 8 hours, in the seller's own best slot, fixes clearly more meetings than redialling at 15 minutes."
3. *(Scroll to the September table)*
   > "We trained on April to August and tested on **September**, which the model never saw. Against the current schedule, our plan uses **17.5% fewer dials**, calls per meeting drop from **16.9 to 13.75**, and estimated meetings go **up 1.3%**. At the same number of dials, re-timing alone gives **6.6% more meetings**."
4. *(Point at the new rule text)*
   > "So the new rule is: never redial within 30 minutes. Retry the same day after 1 to 2 hours or 4 to 8 hours, at most 3 dials in 24 hours and 5 per lead, and stop when the chance of a meeting drops below 1%. If the seller asks to be called later, call at that time."

---

## Scene 4: Any seller, generated live (2:40–3:30) · A speaks · *Solution Completeness*

**Screen:** page **8 · 🧪 Live GLID test (runtime)**.

**A does:**
1. Type the GLID from your sticky note into **Seller GLID**.
2. Keep **Now (live clock)**.
3. In **Company name**, type a made-up name such as **"Gupta Traders"**, so VANI says a natural name on the call.
4. Press **⚡ Generate everything now**.

**A says while it loads:**
> "This is the runtime system. I give it only a seller ID. Everything you'll see is computed right now from that seller's history. Nothing is prepared in advance."

**A points at, on the ⏰ Best time to call tab:**
> "The next action and exact slot, the chance this seller answers and agrees to a meeting, and the reason in plain words. The heatmap shows this seller's own best weekly windows, with the top three outlined. This table is the retry plan if they don't pick up: no 15-minute redials."

**A clicks 🧠 Memory & prompt:**
> "On the left is the seller's memory file. It joins their calls with what they did on IndiaMART's other channels: enquiries received, unread messages, recent activity. This is Problem 2, Global Context, plugged into our Problem 3. On the right is the part of VANI's prompt written for this seller: how to open, which hook to use, the tone, the two callback times to offer if they're busy, and rules like 'nahi alone never ends the call'."

---

## Scene 5: VANI calls the seller, live on Sarvam (3:30–4:55) · A plays the seller · *Voice Experience*

**Screen:** click **🎙 Talk to VANI**. The mode is already **🟢 Sarvam live runtime (Agents SDK)**.

**A says first:**
> "Now VANI calls this seller on Sarvam's own voice runtime, with the prompt we just generated passed in at call time. One Sarvam agent serves every seller. I'll play the seller."

**A presses ▶ Start call and has this conversation.** Wait for VANI to finish each time, except where noted.

| You say (as the seller) | What VANI should do | Why it matters |
|---|---|---|
| *(VANI greets you)* **"Haan ji, boliye."** | Introduces herself as Payal from IndiaMART, then the hook with **this seller's** enquiry numbers | Personal opening from the memory file |
| **"Abhi thoda busy hoon."** | Stops pitching and offers the **two callback times** from the seller block | Busy → callback; not counted as a meeting |
| **"Actually, tell me in English, what is this about?"** | Switches to **English** straight away | Multilingual switch mid-call |
| *Interrupt her mid-sentence:* **"Okay okay, how long is the meeting?"** | Stops talking, answers "15 to 20 minutes" | Natural turn-taking and barge-in |
| **"Theek hai, kal chaar se paanch baje ke beech rakh lo."** | Back in **Hinglish**, reads the time back **as a range** and asks you to confirm | Read-back of a range; switches back to Hindi |
| **"Haan, sahi hai."** | Confirms the meeting, then asks **once** if you need help with anything else | Ask-once closing question |
| **"Nahi, bas itna hi. Thank you."** | Thanks you and ends the call | Clean ending |

**A says afterwards (10 s):**
> "That was fully spontaneous: no buttons between turns. Sarvam handled the listening, interruptions and voice; our system decided *what* VANI says and *when* she calls."

**If something goes wrong on camera:** don't restart. Answer VANI naturally, as a real seller would. If Sarvam doesn't connect at all, switch the mode to **🎧 Hands-free voice call**; it works the same way on the other key.

---

## Scene 6: Different sellers get different plans (4:55–5:35) · A speaks · *Solution Completeness*

**Screen:** page **5 · Demo sellers**. Pick the seller from the sidebar list.

1. **Seller 1** → **Before vs after** tab:
   > "Real example. The old system redialled this seller within minutes; our plan waits for their 8 PM slot."
2. Same seller → **Prompt & memory** tab → in **Write back**, record a *Call Later* for **17:00** → submit:
   > "When a call ends, the result is written back to the seller's memory. The seller asked to be called at 5, so the next plan moves to just before 5. The memory stays current after every call."
3. **Seller 5** → **Plan & windows**:
   > "An IndiaMART executive already spoke to this seller today, so VANI skips today."
4. **Seller 9** → **Plan & windows**:
   > "This one was already dialled three times today, so the next call moves to tomorrow."
5. **Seller 7** → **Prompt & memory** (just show the seller block):
   > "A limited company: formal tone and a late-morning slot."

---

## Scene 7: Why you can trust the numbers (5:35–6:20) · C speaks · *Technical Robustness*

**Screen:** page **7 · Results & validation**. **A** clicks the tabs as C talks.

1. **Backtest (Sept)** tab. **C:**
   > "Everything is tested on September, a month the model never trained on. Every feature uses only calls *before* the moment we predict, so there is no leakage."
2. Still on that tab, the "Is it real?" chart. **C:**
   > "We also checked against what actually happened. Calls the model rated best fixed **22% more meetings** on first calls and **93% more** on retries than the ones it rated worst. An off-policy estimate puts the gain for retries at **+17.9%**, with a 95% confidence interval of 3.4 to 35.9."
3. **Model & checks** tab. **C:**
   > "We compared five models; an ensemble of LightGBM, XGBoost and CatBoost won, with an AUC of 0.754 for meetings. We checked the meeting labels against call transcripts: only 2.4% were wrong."
4. **15-minute verdict** tab. **C:**
   > "And short redials lose in every segment, which is why the verdict is CHANGE.
   > Edge cases are handled too: brand-new sellers fall back to their segment's pattern, unknown IDs get a clear error, and a do-not-call request stops all calls."

---

## Scene 8: Close (6:20–6:45) · B speaks · *Business Impact + Demo*

**Screen:** back to **1 · Overview**, or the one-slide summary (`presentation/best_time_to_call_one_slide.pptx`).

**B says:**
> "To sum up: about one call in six saved, the same meetings or more, and sellers no longer get redialled every 15 minutes. That's fewer irritated sellers and more meetings for IndiaMART.
> One honest limit: the gains are estimated from data logged under the old schedule, so the next step is a 5% live A/B test before rolling out to all traffic.
> The code, README, skills.md and the Sarvam agent ID are in our submission. Thank you."

---

## After recording

- **Check:** VANI's voice is audible in the video, and no real company names or GLIDs are visible (Recording mode on).
- **Length:** trim pauses to land between 6:00 and 7:00.
- **Cutting time:** if you're over 7 minutes, shorten Scene 6 to seller 1 only.
- **Submission form:** include the live agent ID `VANI---Live-fd3e7f49-d516`, along with the README, skills.md and team details.
