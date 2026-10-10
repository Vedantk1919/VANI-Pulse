"""A Sarvam conversation that lives across Streamlit reruns.

The SDK is async and keeps a WebSocket open, while Streamlit re-runs the script on every
click. So the session runs on its own event loop in a background thread; the page sends text
into it and reads the transcript back.
"""
import asyncio
import os
import threading
import time

REQUIRED = ["SARVAM_API_KEY", "SARVAM_ORG_ID", "SARVAM_WORKSPACE_ID", "SARVAM_APP_ID"]


def missing_env():
    return [k for k in REQUIRED if not os.environ.get(k)]


class ChatSession:
    def __init__(self, sess):
        """sess: output of sarvam_live.build_session (variables, greeting, pace, language)."""
        self.sess = sess
        self.messages = [("VANI", sess["greeting"])]
        self.error = None
        self.connected = False
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._agent = None

    def _run(self, coro, timeout=20):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def start(self):
        from pydantic import SecretStr
        from sarvam_conv_ai_sdk import AsyncSamvaadAgent
        from .sarvam_live import _config

        async def on_text(msg):
            text = getattr(msg, "text", "")
            if text:
                self.messages.append(("VANI", text))

        async def go():
            self._agent = AsyncSamvaadAgent(api_key=SecretStr(os.environ["SARVAM_API_KEY"]),
                                            config=_config(self.sess, "chat"), text_callback=on_text)
            await self._agent.start()
            await self._agent.wait_for_connect(timeout=10.0)
        try:
            self._run(go())
            self.connected = True
        except Exception as e:                      # surfaced in the UI
            self.error = f"{type(e).__name__}: {e}"
        return self.connected

    def send(self, text, wait=6.0):
        """Send a seller line and wait briefly for VANI's reply."""
        if not self.connected:
            return
        n = len(self.messages)
        self.messages.append(("SELLER", text))
        try:
            self._run(self._agent.send_text(text))
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            return
        end = time.time() + wait
        while time.time() < end and len(self.messages) <= n + 1:
            time.sleep(0.2)
        time.sleep(0.8)                              # let streamed chunks land

    def stop(self):
        if self._agent is not None:
            try:
                self._run(self._agent.stop(), timeout=10)
            except Exception:
                pass
        self.connected = False
        self._loop.call_soon_threadsafe(self._loop.stop)
