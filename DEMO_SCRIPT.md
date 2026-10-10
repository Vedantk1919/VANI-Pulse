# Demo video script (6–7 minutes)

Start the dashboard with `.venv/bin/streamlit run app.py` (with the `SARVAM_*` variables set for the live chat). Turn on **🎬 Recording mode** in the sidebar before you hit record: it hides company names, products, buyer cities and GLIDs on screen.

Direct links (`?p=<page>&s=<demo seller>`) jump straight to a page with a seller already picked, e.g. `http://localhost:8501/?p=3&s=1`.

| Time | Page | Click | Say |
|---|---|---|---|
| 0:00–0:40 | **1 · Overview** | – | "VANI redials unanswered sellers after a fixed 15 minutes. It takes ~17 dials per meeting and sellers get irritated. We optimise **meetings fixed**, not pickups." Point at the KPI row and the verdict **CHANGE**. |
| 0:40–1:40 | **2 · What the data says** | scroll | Chart 1: evening converts best. Chart 2: 68% of meetings on the first call. Chart 3: redials under 30 min are the worst. Chart 4: frustration triples with repeated dials. Finish on the "nahi is not a refusal" row. |
| 1:40–2:40 | **3 · Demo sellers** → seller 1 | History tab | "A Delhi wholesaler who missed 6 calls. Here's every dial, plus what they did on other channels." Open **Plan & windows** and point at the grey blocked slots ("guardrails") and the weekly windows. |
| 2:40–3:10 | same | **Before vs after** tab | "The current system redialled within minutes; our plan waits for the 8 PM slot." |
| 3:10–3:50 | same | **Prompt & memory** tab | Show seller.md → "VANI already knows 3 enquiries came in, 1 unread". Use **Write back** "Call Later at 17:00" and show the plan jumping to 16:55. |
| 3:50–4:10 | sidebar → sellers 5 and 9 | – | Executive spoke today → skip today. Already 3 dials today → tomorrow. (One sentence each.) |
| 4:10–5:30 | **4 · Talk to VANI** → seller 1 | **▶ Start conversation** (the greeting plays), then **speak into the 🎙 box** or use the quick buttons | Say "haan ji boliye" → real-number opening. "abhi busy hoon" → VANI offers *this seller's* best windows. Say "yeah tell me" → VANI switches to English (and back to Hindi when you do). "char se paanch baje" → read back as a range. Point at "detected: English/Hindi" under each turn. |
| 5:30–6:30 | **5 · Results & validation** | tabs | Backtest: −17.5% dials, calls per meeting 16.9 → 13.75, +6.6% at equal dials. "Is it real?" chart and the off-policy +17.9% (CI 3.4–35.9). 15-minute verdict tab: short redials lose in every segment. |
| 6:30–7:00 | back to **Overview** | – | Limits: estimates come from old-schedule data, so next is a 5% A/B test. Thank you. |

**Before recording:** run `./run_all.sh` once. Open each demo seller once so the caches are warm (the first load takes ~20 s). Then clear write-backs (Prompt & memory tab → "Clear demo write-backs").
