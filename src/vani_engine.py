"""VANI conversation engine on Sarvam's developer APIs (works with an `sk_` API key).

The Sarvam agents runtime needs a different kind of key, so for local testing and the demo
dashboard VANI is assembled from the same Sarvam building blocks:

    seller turn (voice) --Saaras STT (saaras:v4, language auto-detect)--> text + language
    text --Sarvam LLM (sarvam-105b-conversations) + VANI prompt (base + seller block)--> reply
    reply --Bulbul TTS (bulbul:v3, this seller's pace)--> audio

Language switching mirrors the agent platform's per-turn language identification: every seller
turn is classified as English or Hindi/Hinglish, and that turn's LLM call carries an explicit
"reply in <language>" instruction.

Run:  python -m src.vani_engine <glid> [--at 2026-09-18T19:38] [--company "Name"]   (type as the seller)
"""
import argparse
import os
import re
import time
from datetime import datetime

import requests

from .config import ROOT
from . import sarvam

CHAT_URL = "https://api.sarvam.ai/v1/chat/completions"
STT_URL = "https://api.sarvam.ai/speech-to-text"
LLM_MODEL = os.environ.get("SARVAM_LLM_MODEL", "sarvam-105b-conversations")
STT_MODEL = os.environ.get("SARVAM_STT_MODEL", "saaras:v4")

HINGLISH = set("""hai hain hoon hun ho tha thi the nahi nahin nai kya kyun kaun kab kahan kaise kal aaj abhi baad baje
bajke theek thik haan han ji aap aapka aapke main mein mujhe mera meri hum humko ka ki ke ko se par bhi toh to bolo
boliye bataiye batao karo kariye kijiye karun chala chal raha rahi rahe gaadi dukaan samjha samajh matlab baar wala
wali chahiye zaroorat interest pareshan maaf shukriya dhanyavaad accha acha thoda zyada sirf bas ek do teen char
paanch chhe saat aath sham shaam subah dopahar raat""".split())


def _key():
    k = os.environ.get("SARVAM_API_KEY")
    if not k:
        raise RuntimeError("SARVAM_API_KEY is not set")
    return k


def detect_language(text, stt_language=None):
    """'English' or 'Hindi' for one seller turn (Hinglish counts as Hindi)."""
    if stt_language:
        if stt_language.startswith("en"):
            return "English"
        if stt_language.startswith("hi"):
            return "Hindi"
    if re.search(r"[ऀ-ॿ]", text or ""):
        return "Hindi"
    words = re.findall(r"[a-zA-Z']+", (text or "").lower())
    if not words:
        return None
    return "Hindi" if sum(w in HINGLISH for w in words) >= max(1, len(words) // 4) else "English"


def _hindi_words(text):
    """How many Hinglish marker words (or any Devanagari) a reply contains."""
    if re.search(r"[\u0900-\u097F]", text or ""):
        return 99
    return sum(w in HINGLISH for w in re.findall(r"[a-zA-Z']+", (text or "").lower()))


def build_system_prompt(seller_block, company):
    base = (ROOT / "outputs" / "vani_agent_prompt_template.md").read_text().split("---", 1)[1].strip()
    return base.replace("{{company_name}}", company).replace("{{seller_block}}", seller_block)


class VaniConversation:
    """One VANI call with one seller, kept in memory across turns."""

    def __init__(self, sess, company=None):
        """sess: output of sarvam_live.build_session (seller block, greeting, pace, language)."""
        self.sess = sess
        self.company = company or sess["variables"]["company_name"]
        self.system = build_system_prompt(sess["variables"]["seller_block"], self.company)
        self.language = sess["language"]                 # current conversation language
        self.messages = [("VANI", sess["greeting"], self.language)]
        self._history = [{"role": "system", "content": self.system},
                         {"role": "assistant", "content": sess["greeting"]}]
        self.latency = []
        self.tags = set()
        self.rewrites = 0

    def send(self, text, stt_language=None):
        """Seller says `text`; returns VANI's reply (and records both)."""
        lang = detect_language(text, stt_language) or self.language
        self.language = lang
        self.messages.append(("SELLER", text, lang))
        steer = (f"[The seller's last turn is in {lang}. Reply only in "
                 f"{'English' if lang == 'English' else 'natural Hinglish (Hindi in Latin script, English business words allowed)'}, "
                 f"at most 2 short sentences, following the instructions above.]")
        body = {"model": LLM_MODEL, "temperature": 0.3, "max_tokens": 250, "reasoning_effort": None,
                "messages": self._history + [{"role": "user", "content": text},
                                             {"role": "system", "content": steer}]}
        k = _key()
        t0 = time.time()
        reply = self._complete(body, k)
        if lang == "English" and _hindi_words(reply) >= 3:
            # the model copied a Hinglish example line: ask once for a clean English rewrite
            fix = {**body, "messages": body["messages"] + [
                {"role": "assistant", "content": reply},
                {"role": "system", "content": "That reply mixed in Hindi. Rewrite the same reply entirely in English, "
                                              "at most 2 short sentences. Output only the rewritten reply."}]}
            reply = self._complete(fix, k)
            self.rewrites += 1
        tags = re.findall(r"`?\b(do_not_call|callback|meeting_fixed)\b`?", reply)
        if tags:                                         # outcome tags are recorded, never spoken
            self.tags.update(tags)
            reply = re.sub(r"\s*`?\b(do_not_call|callback|meeting_fixed)\b`?\s*", " ", reply).strip()
        self.latency.append(time.time() - t0)
        self._history += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        self.messages.append(("VANI", reply, lang))
        return reply

    @staticmethod
    def _complete(body, k):
        r = requests.post(CHAT_URL, json=body, timeout=60,
                          headers={"api-subscription-key": k, "Authorization": f"Bearer {k}"})
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip()

    def speak(self, text, language=None):
        """WAV bytes of `text` in VANI's voice at this seller's pace."""
        lang = language or self.language
        return sarvam.tts(text, "en-IN" if lang == "English" else "hi-IN", self.sess["pace"])

    @staticmethod
    def transcribe(audio_bytes, filename="seller.wav"):
        """(transcript, language_code) for a recorded seller turn."""
        r = requests.post(STT_URL, headers={"api-subscription-key": _key()},
                          files={"file": (filename, audio_bytes, "audio/wav")},
                          data={"model": STT_MODEL, "language_code": "unknown"}, timeout=60)
        r.raise_for_status()
        j = r.json()
        return j.get("transcript", ""), j.get("language_code")

    def transcript(self):
        return "\n".join(f"{w}: {t}" for w, t, _ in self.messages)


def main():
    from . import sarvam_live as sl
    ap = argparse.ArgumentParser()
    ap.add_argument("glid", type=int)
    ap.add_argument("--at", default="2026-09-15T11:00")
    ap.add_argument("--company")
    ap.add_argument("--script", action="store_true", help="run the 11 standard test lines instead of typing")
    a = ap.parse_args()
    sess = sl.build_session(a.glid, datetime.fromisoformat(a.at), a.company)
    conv = VaniConversation(sess)
    print(f"VANI: {sess['greeting']}")
    lines = [line for _, line in sl.TEST_LINES] if a.script else None
    while True:
        said = lines.pop(0) if lines else (None if a.script else input("SELLER: ").strip())
        if not said:
            break
        if a.script:
            print(f"SELLER: {said}")
        print(f"VANI: {conv.send(said)}")
    print(f"\nmedian LLM latency {sorted(conv.latency)[len(conv.latency) // 2]:.2f}s")


if __name__ == "__main__":
    main()
