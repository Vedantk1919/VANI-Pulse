"""Minimal Sarvam AI client: speak the seller-specific opening with the persona's pace.

Set SARVAM_API_KEY (team key from dashboard.sarvam.ai). Docs: docs.sarvam.ai
"""
import base64
import os
import re

import requests

TTS_URL = "https://api.sarvam.ai/text-to-speech"
MODEL = os.environ.get("SARVAM_TTS_MODEL", "bulbul:v3")
SPEAKER = os.environ.get("SARVAM_SPEAKER", "priya")      # VANI speaks as a female agent ("Payal")


def available():
    return bool(os.environ.get("SARVAM_API_KEY"))


def pace_from_design(design):
    m = re.search(r"TTS pace ([0-9]+(?:\.[0-9]+)?)", design.get("pace", {}).get("instruction", ""))
    return float(m.group(1)) if m else 1.0


def language_from_design(design):
    return "en-IN" if "Start in simple English" in design.get("language", {}).get("instruction", "") else "hi-IN"


def tts(text, language_code="hi-IN", pace=1.0, speaker=SPEAKER, model=MODEL, timeout=30):
    """Return WAV bytes for `text`."""
    key = os.environ.get("SARVAM_API_KEY")
    if not key:
        raise RuntimeError("SARVAM_API_KEY is not set")
    r = requests.post(TTS_URL, headers={"api-subscription-key": key, "Content-Type": "application/json"},
                      json={"text": text[:2400], "language_code": language_code, "model": model,
                            "speaker": speaker, "pace": pace}, timeout=timeout)
    r.raise_for_status()
    return base64.b64decode(r.json()["audios"][0])


def opening_script(plan_json, company="aapki company"):
    """The first two bot turns VANI would speak for this seller."""
    from .sarvam_live import fill_unknown_counts
    hook = fill_unknown_counts(plan_json["how"]["opening_hook"]["instruction"])
    greet = plan_json["how"]["language"]["instruction"]
    g = re.search(r"greeting '([^']+)'|with '([^']+)'", greet)
    hello = (g.group(1) or g.group(2)).split(" / ")[0] if g else "Namaste"
    if language_from_design(plan_json["how"]) == "en-IN":
        return f"{hello}! Am I speaking with {company}? This is Payal from IndiaMART. {hook}"
    return f"{hello}! Kya meri baat {company} se ho rahi hai? Main IndiaMART se Payal bol rahi hoon. {hook}"
