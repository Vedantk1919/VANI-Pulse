"""Live runtime test: GLID in -> plan, best time, seller.md, prompt and a VANI conversation, all
computed on the spot (no pre-built per-seller agents).

The Sarvam platform side uses ONE agent ("VANI - Live runtime test (any GLID)") whose variables
`seller_block` and `company_name` take the prompt generated here.

Run:  python -m src.live_runtime <glid> [--at ...] [--company ...]   (prints what would be pushed)
"""
import argparse
import time
from datetime import datetime

from . import predict as pr
from . import sarvam_live as sl
from . import seller_md as sm
from .vani_engine import build_system_prompt

LIVE_AGENT_ID = "VANI---Live-fd3e7f49-d516"
LIVE_AGENT_NAME = "VANI - Live runtime test (any GLID)"


def default_company(glid):
    """Seller's company from the Global Context profile if we have it, else a neutral placeholder."""
    if sm.has_context(glid):
        name = sm._profile().loc[int(glid)].get("company_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "aapki company"


def run(glid, at=None, company=None):
    """Everything for one seller, computed now. Returns a dict with timings (ms)."""
    glid = int(glid)
    at = at or datetime.now().replace(second=0, microsecond=0)
    company = company or default_company(glid)
    t0 = time.perf_counter()
    p = pr.predict(glid, at)
    t1 = time.perf_counter()
    sess = sl.build_session(glid, at, company)
    full_prompt = build_system_prompt(sess["variables"]["seller_block"], company)
    t2 = time.perf_counter()
    return {"glid": glid, "at": at, "company": company, "predict": p, "sess": sess, "full_prompt": full_prompt,
            "seller_md": p["out"].get("seller_md"),
            "timing": {"plan_and_windows_ms": round((t1 - t0) * 1000), "prompt_ms": round((t2 - t1) * 1000),
                       "total_ms": round((t2 - t0) * 1000)}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glid", type=int)
    ap.add_argument("--at", default=None)
    ap.add_argument("--company", default=None)
    a = ap.parse_args()
    r = run(a.glid, datetime.fromisoformat(a.at) if a.at else None, a.company)
    w = r["predict"]["out"]["when"]
    print(f"GLID {r['glid']} as of {r['at']:%d %b %Y %H:%M} | company {r['company']} | {r['timing']}")
    print(f"NEXT: {w['action'].upper()} {w['slot'] or ''} | {w['reason']}")
    print(f"Top windows: {', '.join(r['predict']['grid'].head(3).window)}")
    print(f"\n--- push to Sarvam agent {LIVE_AGENT_ID}: company_name = {r['company']!r}; seller_block =\n")
    print(r["sess"]["variables"]["seller_block"])


if __name__ == "__main__":
    main()
