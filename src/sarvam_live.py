"""Test the VANI agent on Sarvam for ANY seller GLID - no hosting needed.

For the chosen GLID and moment, the planner builds the seller's call plan and prompt block
locally, then starts a Sarvam session with them passed as agent variables:

    seller_block   - this seller's instructions (timing, hook, tone, memory, live adaptation)
    company_name   - how VANI addresses the seller

Modes
    chat     you type as the seller in the terminal (no microphone needed)
    script   sends the standard 11-line test conversation and saves the transcript
    call     real voice through the laptop mic + speaker (needs PyAudio / PortAudio)
    dry-run  only prints what would be sent (no Sarvam account needed)

Setup (once): create the agent on Sarvam with outputs/sarvam_test/agent_base_prompt.md as its
prompt, add the variables `seller_block` and `company_name` on its Variables tab, commit a
version, then set:
    export SARVAM_API_KEY=...  SARVAM_ORG_ID=...  SARVAM_WORKSPACE_ID=...  SARVAM_APP_ID=...

Run:  python -m src.sarvam_live <glid> [--at 2026-09-18T19:38] [--mode chat|script|call|dry-run]
"""
import argparse
import asyncio
import os
import re
from datetime import datetime

from .config import OUT_DIR
from . import prompt_gen as pg
from . import seller_md as sm

TEST_LINES = [
    ("memory / hook", "Haan ji, boliye"),
    ("busy -> best times", "Abhi busy hoon, gaadi chala raha hoon"),
    ("'nahi' guard", "Nahi, abhi dukaan pe hoon... haan bataiye"),
    ("irritated", "Kitni baar call karoge aap log?"),
    ("rushed", "Jaldi bolo, time nahi hai"),
    ("confused", "Matlab? Samjha nahi"),
    ("language switch", "Can you speak in English?"),
    ("time capture", "Char se paanch baje"),
    ("identity", "Kaun bol raha hai? Bot ho kya?"),
    ("refusal", "Interest nahi hai"),
    ("do-not-call", "Mujhe dobara call mat karna"),
]
OUT = OUT_DIR / "sarvam_test"
OUT.mkdir(parents=True, exist_ok=True)


def build_session(glid, at, company=None):
    """Plan + variables for one seller at one moment."""
    out, _ = pg.generate(glid, at, write=False)
    if company is None and sm.has_context(glid):
        company = sm._profile().loc[glid].get("company_name")
    company = company if isinstance(company, str) else "aapki company"
    m = re.search(r"'([^']+)'", out["how"]["language"]["instruction"])
    hello = m.group(1).split(" / ")[0] if m else "Namaste"
    pace = float(re.search(r"TTS pace ([0-9]+(?:\.[0-9]+)?)", out["how"]["pace"]["instruction"]).group(1)) \
        if "TTS pace" in out["how"]["pace"]["instruction"] else 1.0
    english = "Start in simple English" in out["how"]["language"]["instruction"]
    return {
        "plan": out,
        "variables": {"seller_block": out["vani_prompt_block"], "company_name": company},
        "greeting": f"{hello}! Kya meri baat {company} se ho rahi hai?",
        "pace": pace,
        "language": "English" if english else "Hindi",
    }


def _config(sess, interaction):
    from pydantic import SecretStr  # noqa: F401  (imported for the caller)
    from sarvam_conv_ai_sdk import InteractionConfig, InteractionType, TextToSpeechConfig, SpeechSettings
    from sarvam_conv_ai_sdk.messages.types import UserIdentifierType
    need = ["SARVAM_ORG_ID", "SARVAM_WORKSPACE_ID", "SARVAM_APP_ID", "SARVAM_API_KEY"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Set {', '.join(missing)} first (see the module docstring).")
    return InteractionConfig(
        user_identifier_type=UserIdentifierType.CUSTOM,
        user_identifier=f"btc-test-{sess['plan']['glid']}",
        org_id=os.environ["SARVAM_ORG_ID"], workspace_id=os.environ["SARVAM_WORKSPACE_ID"],
        app_id=os.environ["SARVAM_APP_ID"],
        interaction_type=InteractionType.CALL if interaction == "call" else InteractionType.CHAT,
        agent_variables=sess["variables"],
        initial_bot_message=sess["greeting"],
        initial_language_name=sess["language"],
        text_to_speech_config=TextToSpeechConfig(speech_settings=SpeechSettings(pace=sess["pace"])),
        sample_rate=16000,
    )


async def run(sess, mode):
    from pydantic import SecretStr
    from sarvam_conv_ai_sdk import AsyncSamvaadAgent
    log = []

    async def on_text(msg):
        text = getattr(msg, "text", "")
        if text:
            print(f"VANI: {text}")
            log.append(("VANI", text))

    config = _config(sess, mode)                      # checks the Sarvam env vars first
    kwargs = {"api_key": SecretStr(os.environ["SARVAM_API_KEY"]), "config": config, "text_callback": on_text}
    if mode == "call":
        from sarvam_conv_ai_sdk import AsyncDefaultAudioInterface
        kwargs["audio_interface"] = AsyncDefaultAudioInterface(input_sample_rate=16000)
    agent = AsyncSamvaadAgent(**kwargs)
    try:
        await agent.start()
        await agent.wait_for_connect(timeout=10.0)
        if mode == "call":
            print("Connected - speak as the seller. Ctrl+C to end.")
            await agent.wait_for_disconnect()
        elif mode == "script":
            for label, line in TEST_LINES:
                await asyncio.sleep(4)
                print(f"\nSELLER [{label}]: {line}")
                log.append((f"SELLER [{label}]", line))
                await agent.send_text(line)
            await asyncio.sleep(6)
        else:
            print("Connected - type as the seller, empty line to end.")
            loop = asyncio.get_running_loop()
            while True:
                line = (await loop.run_in_executor(None, input, "SELLER: ")).strip()
                if not line:
                    break
                log.append(("SELLER", line))
                await agent.send_text(line)
                await asyncio.sleep(3)
    finally:
        await agent.stop()
    if log:
        path = OUT / f"transcript_{sess['plan']['glid']}_{mode}.md"
        path.write_text("\n".join(f"**{w}:** {t}" for w, t in log) + "\n")
        print(f"\nTranscript saved: {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("glid", type=int)
    ap.add_argument("--at", default="2026-09-15T11:00", help="plan as of this moment (data covers Apr-Sep 2026)")
    ap.add_argument("--mode", default="dry-run", choices=["dry-run", "chat", "script", "call"])
    ap.add_argument("--company", help="name VANI uses for the seller (use a made-up name when recording a demo)")
    a = ap.parse_args()
    sess = build_session(a.glid, datetime.fromisoformat(a.at), a.company)
    w = sess["plan"]["when"]
    print(f"GLID {a.glid} as of {a.at}: {w['action'].upper()} {w['slot'] or ''} | tier {sess['plan'].get('tier')} | "
          f"{w['reason']}")
    print(f"Greeting: {sess['greeting']} | language {sess['language']} | pace {sess['pace']}")
    if a.mode == "dry-run":
        print("\n--- agent variable: seller_block ---\n" + sess["variables"]["seller_block"])
        return
    asyncio.run(run(sess, a.mode))


if __name__ == "__main__":
    main()
