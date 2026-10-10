"""Hands-free voice conversation with VANI in the browser (no phone call, no record button).

The page listens all the time, detects when the seller starts and stops speaking, sends that turn,
and plays VANI's reply; speaking over VANI interrupts her. Each turn on the server:
Saaras speech-to-text -> VaniConversation (Sarvam LLM on this seller's runtime prompt) -> Bulbul voice.
Only the `sk_` developer key is needed.

The dashboard starts this server in its own process (so the model caches stay warm) and registers a
session per generated GLID. It also runs alone:  python -m src.voice_server   then open
http://localhost:8602/?glid=<GLID>
"""
import base64
import json
import re
import secrets
import threading
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .vani_engine import VaniConversation

PORT = 8602
PAGE = Path(__file__).resolve().parent.parent / "templates" / "voice_call.html"
SESSIONS = {}            # token -> {"sess", "company", "glid", "conv", "lock"}
_LOCK = threading.Lock()


def register(sess, company, glid):
    """Make a conversation slot for a session built elsewhere (the dashboard); returns its token."""
    t = secrets.token_urlsafe(9)
    with _LOCK:
        SESSIONS[t] = {"sess": sess, "company": company, "glid": int(glid), "conv": None, "lock": threading.Lock()}
    return t


def _new_from_glid(glid, company=None):
    from . import live_runtime as lr
    from . import prompt_gen as pg
    if int(glid) not in pg._attempts_by_seller():
        raise ValueError(f"GLID {glid} is not in our data.")
    r = lr.run(int(glid), datetime.now().replace(second=0, microsecond=0), company)
    return register(r["sess"], r["company"], r["glid"])


def phrases(text, first=60, rest=140):
    """Split a reply into short speakable pieces: the first is kept short so VANI starts talking fast,
    the others are voiced while she is already speaking."""
    out = []
    for sent in re.split(r"(?<=[.?!।])\s+", text.strip()):
        limit = first if not out else rest
        while len(sent) > limit:
            cut = max(sent.rfind(sep, 0, limit) for sep in (", ", " - ", " — ", "; "))
            if cut < 15:
                cut = sent.rfind(" ", 0, limit)
            if cut < 15:
                break
            out.append(sent[:cut + 1].strip())
            sent, limit = sent[cut + 1:].strip(), rest
        if sent:
            out.append(sent)
    return out or [text]


def _voice(conv, text):
    """Audio for the first phrase now; the rest are fetched by the page through /api/say."""
    parts = phrases(text)
    return {"audio": _b64(conv.speak(parts[0])), "rest": parts[1:]}


def _b64(wav):
    return base64.b64encode(wav).decode() if wav else None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        if u.path == "/health":
            return self._send(200, {"ok": True, "sessions": len(SESSIONS)})
        if u.path == "/api/transcript":
            s = SESSIONS.get(parse_qs(u.query).get("t", [""])[0])
            if not s:
                return self._send(404, {"error": "unknown session"})
            c = s["conv"]
            return self._send(200, {"messages": c.messages if c else [], "tags": sorted(c.tags) if c else []})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            if u.path == "/api/new":                       # standalone use: any GLID, plan as of now
                j = json.loads(body or b"{}")
                return self._send(200, {"token": _new_from_glid(j["glid"], j.get("company") or None)})
            s = SESSIONS.get(q.get("t", [""])[0])
            if not s:
                return self._send(404, {"error": "Session expired. Generate the GLID again."})
            if u.path == "/api/say":                       # one later phrase of VANI's current reply
                c = s["conv"]
                return self._send(200, {"audio": _b64(c.speak(json.loads(body)["text"])) if c else None})
            with s["lock"]:
                if u.path == "/api/start":                 # (re)start: VANI opens the call
                    c = s["conv"] = VaniConversation(s["sess"], s["company"])
                    greet = s["sess"]["greeting"]
                    return self._send(200, {"glid": s["glid"], "company": s["company"], "reply": greet,
                                            "lang": c.language, **_voice(c, greet)})
                if u.path == "/api/turn":                  # body = WAV of one seller turn
                    c = s["conv"]
                    if c is None:
                        return self._send(400, {"error": "Press Start first."})
                    t0 = time.time()
                    text, code = VaniConversation.transcribe(body)
                    t1 = time.time()
                    if not text.strip():
                        return self._send(200, {"heard": "", "reply": None})
                    reply = c.send(text, code)
                    t2 = time.time()
                    voice = _voice(c, reply)
                    t3 = time.time()
                    return self._send(200, {"heard": text, "lang": c.messages[-2][2], "reply": reply, **voice,
                                            "tags": sorted(c.tags),
                                            "ms": {"stt": round((t1 - t0) * 1000), "llm": round((t2 - t1) * 1000),
                                                   "tts": round((t3 - t2) * 1000)}})
            self._send(404, {"error": "not found"})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})


def embed_html(token, api):
    """The call page with its session and API address baked in (for st.components.v1.html)."""
    boot = f"<script>window.VANI_TOKEN={json.dumps(token)};window.VANI_API={json.dumps(api)};</script>"
    return PAGE.read_text().replace("<script>", boot + "<script>", 1)


_server = None


def start(port=PORT, host="0.0.0.0"):
    """Start once in a background thread; returns True if this process serves the port."""
    global _server
    if _server is None:
        try:
            _server = ThreadingHTTPServer((host, port), Handler)
        except OSError:
            return False
        threading.Thread(target=_server.serve_forever, daemon=True).start()
    return True


if __name__ == "__main__":
    print(f"VANI voice: http://localhost:{PORT}/?glid=<GLID>")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
