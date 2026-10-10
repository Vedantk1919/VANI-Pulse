# Connecting VANI to the Sarvam platform (from zero)

There are two paths. Do **Path A first**: it needs nothing but the Sarvam website and gives you a working agent for the demo and the submission's "Agent ID / live link". **Path B** then connects that agent to our dashboard, so any GLID can be tested from the Talk to VANI page.

The files you paste are generated in `outputs/sarvam_test/` (run `./run_all.sh` or `python -m src.sarvam_live <GLID>` to refresh them):

| File | Used in |
|---|---|
| `PATH_A_1_seller_memory.md`, `PATH_A_2_limited_company.md`, `PATH_A_3_south_india_seller.md` | Path A: a complete prompt for one seller |
| `agent_base_prompt.md` | Path B: the agent prompt with the `@company_name` and `@seller_block` variables |
| `default_seller_block.txt` | Path B: the default value for `seller_block` |

---

## Step 0: Account and API key (5 min)

1. Open **https://dashboard.sarvam.ai** and log in with your team's hackathon account. Ask the organisers or the Sarvam team on the floor if you don't have one.
2. Find the **API keys** section and copy your key (it starts with `sk_`). You already have one, and it works for text-to-speech.
3. Keep the key out of chats and files. Set it only in your terminal:
   ```bash
   export SARVAM_API_KEY=sk_...
   ```

## Path A: a working VANI agent in the browser (15–20 min)

### A1. Create the agent
1. Open **https://indus.sarvam.ai** (the same login).
2. In the left menu, under **Build**, click **Agents**.
3. Click **Create from Scratch**. Skip the "What should your agent do?" box, because we already have the prompt.
4. You land on the **Canvas**, the agent builder.

### A2. Paste the prompt
1. Open `outputs/sarvam_test/PATH_A_1_seller_memory.md` in VS Code.
2. On the Canvas, open the **Instructions** tab.
3. **Agent name:** copy the `AGENT NAME:` line, e.g. *VANI - Seller memory: real-number opening*.
4. **Greeting:** copy the line under `GREETING:` (e.g. *Namaste! Kya meri baat Sharma Rubber Works se ho rahi hai?*).
5. **System prompt:** copy **everything** under `SYSTEM PROMPT (paste everything below):` and paste it in.
6. Save.

### A3. Language and voice
1. Open the agent's **Settings**.
2. Under **Language personalisation**:
   - **Starting language:** Hindi (English for `PATH_A_3_south_india_seller.md`)
   - Turn **Switch language during call** on
   - **Allowed languages:** Hindi and English
3. Under **Speakers & voice**:
   - pick a **female** voice, since VANI speaks as "Payal"
   - set the **pace** to the `VOICE PACE:` value in the file (1.1 or 1.0) if the option exists
4. Save.

### A4. Test in the browser
1. Click **Test agent** and allow microphone access.
2. Speak as the seller:

| You say | VANI should |
|---|---|
| "Haan ji, boliye" | Give the real-number hook ("…3 buyer enquiry aayi hain… 1 abhi tak padhi nahi gayi") and ask for a time |
| "Abhi busy hoon, gaadi chala raha hoon" | Stop pitching and offer two specific times ("aaj raat 8 baje ya kal shaam 5 baje") |
| "Nahi, abhi dukaan pe hoon… haan bataiye" | Carry on: "nahi" alone isn't a refusal |
| "Kitni baar call karoge aap log?" | Apologise once, keep it to one sentence, offer a callback |
| "Jaldi bolo, time nahi hai" | Ask for the time directly |
| "Matlab? Samjha nahi" | Repeat in simpler words |
| "Can you speak in English?" | Continue in English |
| "Char se paanch baje" | Read it back as "chaar se paanch baje ke beech" |
| "Kaun bol raha hai? Bot ho kya?" | Answer honestly in one line, then ask again |
| "Mujhe dobara call mat karna" | Apologise, confirm and end |

3. If a reply is off, edit only the matching line in the system prompt, save, and test again.

### A5. Save a version and note the link
1. **Commit / publish** a version of the agent. Sarvam runs committed versions; drafts are for editing.
2. Copy the agent's page URL and its **Agent ID**. That's the "Agent ID / live link on Sarvam platform" in the submission checklist.

### A6 (optional). One agent per demo seller
Repeat A1–A5 with `PATH_A_2_limited_company.md` (formal tone) and `PATH_A_3_south_india_seller.md` (English first) to show contrasting sellers in the video.

---

## Path B: connect the agent to our dashboard (any GLID) (20–30 min)

In Path B **one** agent serves every seller: the dashboard sends that seller's instructions into the agent as variables when the conversation starts.

### B1. Create the variable-based agent
1. On indus.sarvam.ai: **Build → Agents → Create from Scratch**. Name it **VANI – Best Time to Call (variables)**.
2. Open the **Variables** tab. Under **Input variables**, click **Add** twice:

| Name | Default value |
|---|---|
| `company_name` | `aapki company` |
| `seller_block` | the whole contents of `outputs/sarvam_test/default_seller_block.txt` |

### B2. Paste the base prompt and insert the variables
1. **Instructions tab → System prompt:** paste `outputs/sarvam_test/agent_base_prompt.md`.
2. The pasted text contains `@company_name` and `@seller_block` as **plain text**, so you have to turn them into variable chips:
   - delete the text `@company_name`, type `@`, and pick **company_name** from the list that pops up. It becomes a coloured chip.
   - do the same for `@seller_block` at the end of the prompt.
3. **Greeting:** type `Namaste! Kya meri baat `, insert the `@company_name` chip, then type ` se ho rahi hai?`
4. Set the same **Settings** as in A3, then save.
5. Use **Test agent** once. VANI should use the default seller block from step B1.
6. **Commit / publish** a version. The SDK uses the latest committed version.

### B3. Find the three IDs
The SDK needs to know **which** agent to talk to, so beyond the API key it needs:

| Variable | What it is |
|---|---|
| `SARVAM_ORG_ID` | your organisation |
| `SARVAM_WORKSPACE_ID` | the workspace the agent is in |
| `SARVAM_APP_ID` | the agent itself |

Where to look (Sarvam's docs don't spell this out):
1. Open the agent and look for **Deploy → Deploy with Code** (also at `https://indus.sarvam.ai/samvaad/deploy/with-code`). The **Embed** / code snippet shown there normally contains the org, workspace and app IDs.
2. If not, check the **browser address bar** while the agent is open; the IDs are often part of the URL.
3. If you still can't find them, ask the Sarvam team on the floor: *"For the conversation SDK I need org_id, workspace_id and app_id for my agent."*

These are identifiers, not secrets. Only the API key is secret.

### B4. Test from the terminal first
```bash
cd "/home/imart/Downloads/Aids to solve Problems-20261009T105420Z-1-001/vani_best_time"
export SARVAM_API_KEY=sk_...  SARVAM_ORG_ID=...  SARVAM_WORKSPACE_ID=...  SARVAM_APP_ID=...

# 1. What will be sent (no Sarvam call)
.venv/bin/python -m src.sarvam_live <GLID> --at 2026-09-18T19:38 --company "Sharma Rubber Works"

# 2. Type as the seller (empty line ends the chat)
.venv/bin/python -m src.sarvam_live <GLID> --at 2026-09-18T19:38 --company "Sharma Rubber Works" --mode chat

# 3. Run the 11 test lines automatically; the transcript is saved in outputs/sarvam_test/
.venv/bin/python -m src.sarvam_live <GLID> --at 2026-09-18T19:38 --company "Sharma Rubber Works" --mode script
```
VANI's first real reply should mention **this seller's** details (3 enquiries, 1 unread…). If it only uses the generic default text, the variables aren't being picked up (see Troubleshooting).

### B5. Use it from the dashboard
```bash
# same terminal, with the four variables still set
.venv/bin/streamlit run app.py
```
1. Pick a demo seller in the sidebar.
2. Go to **4 · Talk to VANI (Sarvam)**, click **▶ Start conversation**, then use the quick buttons or type as the seller.
3. **🔊 Speak opening** plays the opening in VANI's voice; it needs only the API key.

---

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| "Set SARVAM_ORG_ID, …" message | The variables weren't exported in the terminal that started the script or dashboard. Export them, then restart |
| 401 / 403 error | Wrong or expired API key, or the key belongs to a different organisation than the agent |
| Agent not found / 404 | Wrong `SARVAM_APP_ID`, or no committed version yet (step B2.6) |
| VANI ignores the seller details | `@seller_block` was pasted as plain text instead of a variable chip (B2.2), or the variable name doesn't match exactly (`seller_block`, `company_name`) |
| Long prompt rejected or cut | The seller block is 2,000–4,000 characters. Ask the Sarvam team about variable size limits, or fall back to Path A (full prompt per seller) |
| `--mode chat` connects but VANI never replies to typed text | This voice agent may not accept typed input. Use `--mode call` (laptop mic; first `sudo apt install portaudio19-dev` and `.venv/bin/pip install pyaudio`) or the console's **Test agent** button |
| `bulbul:v2` deprecated error | Our code uses `bulbul:v3`; only custom settings would hit this |

## For the submission
- **Agent ID / live link:** from step A5 (or B2).
- **Demo video:** record the dashboard plus a test conversation (DEMO_SCRIPT.md). Turn on **🎬 Recording mode** in the dashboard and use made-up company names.
- **Afterwards:** regenerate the API key on dashboard.sarvam.ai, since it has been shared in chat.
