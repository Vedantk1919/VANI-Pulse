"""Sarvam-native live call in the browser: the Agents SDK runtime behind a local bridge.

Browser mic --(our WebSocket, 16 kHz PCM)--> this bridge --(Sarvam Agents SDK)--> VANI runtime agent
Browser speaker <-------- agent voice + transcripts + interrupt events --------------------

Sarvam's own runtime does speech recognition, turn-taking, barge-in and the voice, exactly like
"Test agent" on the platform. The seller's runtime prompt goes in as agent_variables of the ONE
runtime agent, so nothing is pre-built per seller. The key stays on this machine (never sent to the
browser), as Sarvam's docs require.

Needs an Agents/platform API key from indus.sarvam.ai in SARVAM_AGENT_API_KEY (the sk_ developer
key is refused by the agents runtime). Org/workspace IDs come from the environment or
data/sarvam_ids.env (git-ignored, not secret).
"""
import asyncio
import json
import os
import struct
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sarvam_conv_ai_sdk import AsyncAudioInterface

from . import voice_server as vs
from .live_runtime import LIVE_AGENT_ID

PORT = 8603
ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "templates" / "sdk_call.html"


def _ids():
    ids = {}
    f = ROOT / "data" / "sarvam_ids.env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                ids[k.strip()] = v.strip().strip('"')
    ids.update({k: os.environ[k] for k in ("SARVAM_ORG_ID", "SARVAM_WORKSPACE_ID") if os.environ.get(k)})
    return ids


def key():
    return os.environ.get("SARVAM_AGENT_API_KEY", "")


def available():
    ids = _ids()
    return bool(key() and ids.get("SARVAM_ORG_ID") and ids.get("SARVAM_WORKSPACE_ID"))


def config(s, app_id=LIVE_AGENT_ID):
    """InteractionConfig for one seller session (from voice_server.SESSIONS)."""
    from sarvam_conv_ai_sdk import InteractionConfig, InteractionType
    from sarvam_conv_ai_sdk.messages.types import UserIdentifierType
    ids, sess = _ids(), s["sess"]
    return InteractionConfig(
        user_identifier_type=UserIdentifierType.CUSTOM, user_identifier=f"btc-live-{s['glid']}",
        org_id=ids["SARVAM_ORG_ID"], workspace_id=ids["SARVAM_WORKSPACE_ID"], app_id=app_id,
        interaction_type=InteractionType.CALL, sample_rate=16000,
        agent_variables={**sess["variables"], "company_name": s["company"], "call_summary": "", "user_name": ""},
        initial_bot_message=sess["greeting"], initial_language_name=sess["language"])


class BrowserAudio(AsyncAudioInterface):
    """AsyncAudioInterface that relays PCM between the SDK and one browser WebSocket."""

    def __init__(self, ws):
        self.ws, self.input_callback = ws, None

    async def start(self, input_callback):
        self.input_callback = input_callback

    async def stop(self):
        self.input_callback = None

    async def output(self, audio, sample_rate=None):
        # 4-byte little-endian sample rate, then 16-bit PCM mono
        await self.ws.send(struct.pack("<I", int(sample_rate or 16000)) + audio)

    def interrupt(self):
        asyncio.get_running_loop().create_task(self.ws.send(json.dumps({"type": "interrupt"})))


async def _handle(ws):
    from pydantic import SecretStr
    from sarvam_conv_ai_sdk import AsyncSamvaadAgent
    s = vs.SESSIONS.get(parse_qs(urlparse(ws.request.path).query).get("t", [""])[0])
    if not s:
        await ws.send(json.dumps({"type": "error", "text": "Session expired. Generate the GLID again."}))
        return
    if not available():
        await ws.send(json.dumps({"type": "error", "text": "SARVAM_AGENT_API_KEY is not set on the server."}))
        return
    audio = BrowserAudio(ws)

    async def on_transcript(m):
        await ws.send(json.dumps({"type": "transcript", "role": str(getattr(m.role, "value", m.role)), "text": m.content}))

    async def on_event(e):
        await ws.send(json.dumps({"type": "event", "name": type(e).__name__}))

    agent = AsyncSamvaadAgent(api_key=SecretStr(key()), config=config(s), audio_interface=audio,
                              transcript_callback=on_transcript, event_callback=on_event)
    try:
        await agent.start()
        if not await agent.wait_for_connect(timeout=15):
            raise RuntimeError("Sarvam runtime did not connect within 15 s")
        await ws.send(json.dumps({"type": "connected", "glid": s["glid"], "company": s["company"],
                                  "interaction_id": agent.get_interaction_id()}))
        ended = asyncio.create_task(agent.wait_for_disconnect())
        async for msg in ws:
            if ended.done():
                break
            if isinstance(msg, bytes):
                if audio.input_callback:
                    await audio.input_callback(msg, len(msg) // 2)
            elif json.loads(msg).get("type") == "stop":
                break
        await ws.send(json.dumps({"type": "ended"}))
    except Exception as e:
        detail = str(e)
        if "401" in detail:
            detail = "Sarvam refused the key (401). Use an Agents API key from indus.sarvam.ai, not the sk_ developer key."
        try:
            await ws.send(json.dumps({"type": "error", "text": f"{type(e).__name__}: {detail}"}))
        except Exception:
            pass
    finally:
        await agent.stop()


_started = False


def start(port=PORT, host="0.0.0.0"):
    """Run the bridge in a background thread with its own event loop; True if serving."""
    global _started
    if _started:
        return True
    import websockets
    ready, ok = threading.Event(), []

    def run():
        async def main():
            try:
                server = await websockets.serve(_handle, host, port, max_size=2 ** 20)
            except OSError:
                ready.set()
                return
            ok.append(True)
            ready.set()
            await server.serve_forever()
        asyncio.run(main())

    threading.Thread(target=run, daemon=True).start()
    ready.wait(5)
    _started = bool(ok)
    return _started


def embed_html(token, ws_url):
    boot = f"<script>window.VANI_TOKEN={json.dumps(token)};window.VANI_WS={json.dumps(ws_url)};</script>"
    return PAGE.read_text().replace("<script>", boot + "<script>", 1)


if __name__ == "__main__":
    import time
    print("bridge", start(), f"ws://localhost:{PORT}/?t=<token>")
    while True:
        time.sleep(3600)
