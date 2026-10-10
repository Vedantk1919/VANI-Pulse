# Demo video script: VANI Pulse (Problem 3, Best Time to Call)

**Length:** about 6 min 45 s (the rules ask for 5 to 7 minutes).
**Presenters:** Vedant and Meet.

| Presenter | Role | Speaks in |
|---|---|---|
| **Vedant** | At the laptop: drives the screen and plays the seller in the live call | Scenes 3, 4, 5, 6 |
| **Meet** | Narrates the problem, the data, the validation and the close | Scenes 0, 1, 2, 7, 8 |

During Meet's scenes, Vedant still drives the screen and follows Meet's cues.

The judges score five things. Each scene is tagged with the one it serves, so nothing is left out:
**Business Impact 25%** · **Solution Completeness 20%** · **Technical Robustness 20%** · **Voice Experience 20%** · **Demo & skills.md 15%**.

---

## The two sellers for the live part

We scored 260 sellers that have cross-channel memory, each at a real moment in September just before VANI retried them. These two show the most at once: memory, tone, opening and timing. Their GLIDs are in **`data/live_demo_glids.md`** (local only, never pushed).

| | Date / time to enter | What it shows |
|---|---|---|
| **Live seller 1 (callback)**: limited company | **30 Sep 2026, 13:18** | Seller asked for a callback at 1:23 PM; plan calls at 1:18 (5 min early). VANI opens "Aapne 1:23 PM call karne ko kaha tha…". **Formal** tone, fast pace. Memory: **23 unread enquiries** with products and buyer cities. Retry ladder for the next day. |
| **Live seller 2 (dropped call)**: sole proprietor | **16 Sep 2026, 17:08** | The last call dropped at 17:00. The old system redialled within minutes; **our plan waits for 7 PM**. VANI opens "Pichhli baar baat poori nahi ho payi thi…". **Warm** tone. 12 enquiries. |

**Why a past moment and not "Now"?** Our data ends on 30 September, so "now" sees every seller as stale. Replaying a September moment runs the same engine, live, on what we knew at that minute.

---

## Before you press record (15 minutes)

1. **Network:** use a network that reaches Sarvam. Open https://api.sarvam.ai in the browser; a page or error page should appear quickly. The Airtel Wi-Fi blocked it earlier today.
2. **Start the dashboard** in a terminal:
   ```
   cd vani_best_time
   ./start_dashboard.sh
   ```
   Paste the `sk_…` key, then the `sk_samvaad_…` key, when it asks.
3. Open **http://localhost:8601** in Chrome. It has to be *localhost*, or the microphone is blocked.
4. **Warm up:** click through pages 1 to 8 once. Open demo sellers 1, 5 and 9 on page 5. On page 8, generate both live sellers once. The first load of each takes up to 20 s; you don't want that wait on camera.
5. On page 5 → seller 1 → **Prompt & memory**, press **Clear demo write-backs**.
6. **Sidebar:** switch on **🎬 Recording mode**. It hides real company names, buyer cities and GLIDs on screen. VANI's *voice* still says the product and city names; the video goes to the internal jury, so that is fine.
7. **Do one full test call** with Live seller 1 (Scene 5), so you know the voice works on this network.
8. **Screen:** Chrome full screen (F11), zoom 90%, notifications off, other tabs closed.
9. **Audio:** Vedant wears **headphones with a mic**, so VANI's voice doesn't feed back into the mic. Record at 1080p *with system audio*, so VANI's voice is in the video.

**Recording tip:** record each scene as a separate clip and join them afterwards. A mistake then costs one scene, not the whole video. Speak a little slower than normal.

---

## Scene 0: Opening (0:00–0:20) · Meet · *Demo*

**Screen:** page **1 · Overview**, top of the page.

**Meet:**
> "Hi, I'm Meet, and this is Vedant. This is **VANI Pulse**, our answer to Problem 3, Best Time to Call, for VANI, IndiaMART's voice bot that calls sellers to fix meetings. In six minutes we'll show what's wrong with today's calling schedule, what our model found in the data, and VANI calling a seller live on Sarvam with a plan built for that one seller."

---

## Scene 1: The problem (0:20–0:55) · Meet · *Business Impact*

**Screen:** stay on **Overview**. **Vedant** moves the mouse slowly over the KPI row while Meet talks about each number.

**Meet:**
> "Today VANI calls every seller on a fixed schedule. If the seller doesn't pick up, it redials after exactly 15 minutes, again and again. That costs about **17 calls for every meeting fixed**, and sellers get irritated by back-to-back calls.
> Nobody knew whether the 15-minute rule was right. And optimising for pickups is not enough: a pickup that doesn't end in a meeting is a wasted call. So we optimised for **meetings fixed**."

**Vedant points at:** the *calls per meeting* KPI, then the **CHANGE** verdict.

**Meet:**
> "Our answer on the 15-minute rule: **change it**. Here's why."

---

## Scene 2: What the data says (0:55–1:40) · Meet · *Technical Robustness*

**Screen:** page **2 · What the data says**. **Vedant** scrolls one chart at a time and pauses on each.

**Meet:**
> "We used all 530,000 call attempts from April to September, for about 149,000 sellers. Four things stood out.
> **One:** evenings convert best. Calls after 5 PM fix more meetings; 9 AM is the weakest slot.
> **Two:** most meetings come from the *first* call. Retries matter, but each one is worth less.
> **Three:** redials within 30 minutes perform worst, in every segment we checked. That's exactly what the 15-minute rule does.
> **Four:** the more often a seller is dialled, the more frustrated the call transcripts get.
> And one learning for the voice side: a seller saying 'nahi' is often not a refusal, so VANI must not hang up on the first 'nahi'."

---

## Scene 3: Best time to call and the new retry rule (1:40–2:35) · Vedant · *Business Impact*

**Screen:** page **3 · Best time to call & 15-min rule**.

1. *(Heatmap at the top)*
   > "This is when sellers actually agree to meetings: day of week against hour. Evening is best on every day. One exception: limited companies answer better in the late morning, so the plan differs by seller type."
2. *(Scroll to the red vs green bars)*
   > "The 15-minute rule is in red; our retry gaps are in green. Retrying after 1 to 2 hours, or 4 to 8 hours, in the seller's own best slot fixes clearly more meetings."
3. *(Scroll to the September table)*
   > "We trained on April to August and tested on **September**, which the model never saw. Against the current schedule, our plan uses **17.5% fewer dials**, calls per meeting drop from **16.9 to 13.75**, and estimated meetings go **up 1.3%**. At the same number of dials, re-timing alone gives **6.6% more meetings**."
4. *(Point at the new rule)*
   > "So the new rule: never redial within 30 minutes. Retry the same day after 1 to 2 or 4 to 8 hours, at most 3 dials a day and 5 per lead, and stop when the chance of a meeting falls below 1%. If the seller asks to be called later, call at that time."

---

## Scene 4: Any seller, generated live (2:35–3:25) · Vedant · *Solution Completeness*

**Screen:** page **8 · 🧪 Live GLID test (runtime)**.

**Vedant does:**
1. In **Seller GLID**, type the GLID of **Live seller 1** (from `data/live_demo_glids.md`).
2. Choose **A past moment**. Date **2026/09/30**, time **13:18**.
3. In **Company name**, type **Gupta Traders**.
4. Press **⚡ Generate everything now**.

**Vedant (while it loads):**
> "This is the runtime system. I give it only a seller ID and a moment; here, 30 September at 1:18 PM. Everything is computed now from what we knew at that minute. Nothing is prepared in advance."

**Vedant, on the ⏰ Best time to call tab** (point at each):
> "The plan says: call now. The reason: an hour ago this seller said 'call me at 1:23', so we dial five minutes early. That's a callback honoured, not a blind redial. Here are this seller's best weekly windows, and the retry plan if they don't pick up: tomorrow, not in 15 minutes."

**Vedant clicks 🧠 Memory & prompt:**
> "On the left is the seller's memory file: the callback VANI promised, **23 enquiries in the last 30 days that are still unread**, which products and which cities they came from, and what happened on the last call. That's Problem 2, Global Context, feeding our Problem 3.
> On the right is the part of VANI's prompt written for this seller. Because it's a **limited company**, the tone is **formal and crisp**, with business value and no small talk. The opening skips the introduction and refers to the callback. And the rules: 'nahi' alone never ends the call; a busy seller gets a callback, not a pitch."

---

## Scene 5: VANI calls the seller, live on Sarvam (3:25–4:50) · Vedant plays the seller · *Voice Experience*

**Screen:** click **🎙 Talk to VANI**. The mode is already **🟢 Sarvam live runtime (Agents SDK)**.

**Vedant:**
> "Now VANI calls this seller on Sarvam's own voice runtime, with the prompt we just generated passed in at call time. One Sarvam agent serves every seller. I'll play the seller."

**Vedant presses ▶ Start call and has this conversation.** Wait for VANI to finish each time, except where marked.

| Vedant says (as the seller) | What VANI should do | What it proves |
|---|---|---|
| *(VANI: "Namaste! Kya meri baat Gupta Traders se ho rahi hai?")* **"Haan ji, boliye."** | Refers to the callback ("aapne 1:23 baje call karne ko kaha tha…") and, formally, the **23 unread enquiries** | Memory and callback in the opening; formal tone |
| **"Abhi bhi thoda busy hoon."** | Stops pitching and offers **two concrete callback times** | Busy → callback, counted as a callback, not a meeting |
| **"Actually, tell me in English. What are these enquiries?"** | Switches to **English**, explains the enquiries in one or two lines | Language switch mid-call |
| *Interrupt her mid-sentence:* **"Okay okay, how long is the meeting?"** | Stops talking, answers "15 to 20 minutes" | Natural turn-taking and barge-in |
| **"Theek hai, kal chaar se paanch baje ke beech rakh lo."** | Back in **Hinglish**; reads the time back **as a range** and asks you to confirm | Range read-back; switches back to Hindi |
| **"Haan, sahi hai."** | Confirms the meeting, then asks **once** if you need help with anything else | Ask-once closing question |
| **"Nahi, bas itna hi. Thank you."** | Thanks you and ends the call | Clean ending |

**Vedant afterwards (10 s):**
> "That was fully spontaneous: no buttons between turns. Sarvam handled the listening, interruptions and voice; our system decided *what* VANI says and *when* she calls."

**If something goes off-script:** don't restart. Answer VANI naturally, as a real seller would. If Sarvam doesn't connect at all, switch the mode to **🎧 Hands-free voice call**; it works the same way on the other key.

---

## Scene 6: A different seller gets a different plan (4:50–5:35) · Vedant · *Solution Completeness*

1. **Still on page 8:** enter **Live seller 2**, choose **A past moment**, **2026/09/16**, **17:08**, and press **⚡ Generate everything now**.
   > "A different seller: a small proprietor whose last call dropped eight minutes ago. The old system redialled within minutes. Our plan says **wait until 7 PM**, their best slot today. On **🧠 Memory & prompt** the tone is now **warm and simple**, and VANI opens with 'pichhli baar baat poori nahi ho payi thi', picking up the dropped call instead of pitching again."
2. **Page 5 · Demo sellers → seller 1 → Prompt & memory tab.** In **Write back**, record *Call Later* at **17:00** and submit.
   > "And when a call ends, the result is written back to memory. The seller asked for 5 PM, so the next plan moves to just before 5."
3. **Seller 5 → Plan & windows**, then **seller 9 → Plan & windows**, one line each:
   > "An IndiaMART executive already spoke to this seller today, so VANI skips today."
   > "This one was dialled three times today already, so the next call moves to tomorrow."

---

## Scene 7: Why you can trust the numbers (5:35–6:20) · Meet · *Technical Robustness*

**Screen:** page **7 · Results & validation**. **Vedant** clicks each tab when Meet starts that point.

1. **Backtest (Sept)** tab. **Meet:**
   > "Everything is tested on September, a month the model never trained on. Every feature uses only calls *before* the moment we predict, so nothing leaks from the future."
2. Same tab, the "Is it real?" chart. **Meet:**
   > "We also checked against what actually happened. Calls the model rated best fixed **22% more meetings** on first calls and **93% more** on retries than the ones it rated worst. An off-policy estimate puts the gain on retries at **+17.9%**, with a 95% confidence interval of 3.4 to 35.9."
3. **Model & checks** tab. **Meet:**
   > "We compared five models. An ensemble of LightGBM, XGBoost and CatBoost won, with an AUC of 0.754 for meetings. We checked the meeting labels against call transcripts: only 2.4% were wrong."
4. **15-minute verdict** tab. **Meet:**
   > "Short redials lose in every segment, so the verdict is CHANGE. Edge cases are covered too: brand-new sellers fall back to their segment's pattern, unknown IDs get a clear error, and a do-not-call request stops all calls."

---

## Scene 8: Close (6:20–6:45) · Meet · *Business Impact + Demo*

**Screen:** back to **1 · Overview**, or the one-slide summary (`presentation/best_time_to_call_one_slide.pptx`).

**Meet:**
> "To sum up, VANI Pulse saves about one call in six, the same meetings or more, and sellers no longer redialled every 15 minutes. That's fewer irritated sellers and more meetings for IndiaMART.
> One honest limit: the gains are estimated from data logged under the old schedule, so the next step is a 5% live A/B test before rolling out to everyone.
> Code, README, skills.md and our Sarvam agent ID are in the submission. Thank you."

---

## After recording

- **Check:** VANI's voice is audible, and no real company names or GLIDs are visible on screen (Recording mode on).
- **Length:** trim pauses to land between 6:00 and 7:00.
- **Cutting time:** if you're over 7 minutes, cut steps 2–3 of Scene 6 and keep only Live seller 2.
- **Submission form:** the live agent ID is `VANI---Live-fd3e7f49-d516`.
