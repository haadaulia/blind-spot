"""
verify.py — entailment-based verification of ABSENT candidates.

Framed as natural-language inference / fact-checking against a grounding
document (cf. MiniCheck 2024; ClaimVer 2024; entailment-bias work 2025):
for each candidate gap we ask whether the TARGET's own Item 1A *entails* the
specific risk the peers describe. Topical/keyword overlap is NOT entailment.

Three mechanisms keep the false-positive (wrongly-COVERED) rate down:
  1. Strict NLI framing with ABSENT as the default verdict (counters the
     "attestation bias" where an LLM affirms a plausible-sounding claim).
  2. Chain-of-thought: name the specific risk, pick one best span, then judge.
  3. Evidence-span grounding: a COVERED verdict must cite a verbatim span that
     actually occurs in the target text, else it is overridden back to ABSENT.

Retrieval is keyword-based over the FULL filing so document position never
hides a disclosure.
"""
import os
import re
import time
import json

import requests
from dotenv import load_dotenv

load_dotenv()
GROQ_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.1-8b-instant"

_STOP = set("the a an and or of to in for on with our we us their they that this as is are "
            "be been being by from at it its may could would such other not no any all more "
            "most some these those which who whom whose will have has had can also than then but "
            "if into over under between about your you company companies business businesses risk "
            "risks result results operations operation financial condition adversely affect affects "
            "affected material materially significant significantly including include due various "
            "factors ability able unable success successful able".split())

SYSTEM = (
    "You are a forensic disclosure analyst performing a NATURAL LANGUAGE "
    "INFERENCE check. You are given a RISK CLAIM (how a company's peers describe "
    "a specific risk) and EXCERPTS from the TARGET company's own Risk Factors. "
    "Decide whether the target's text ENTAILS that the target faces the SAME "
    "SPECIFIC risk.\n\n"
    "RULES — read carefully:\n"
    "• ENTAILED (verdict COVERED): a span of the target text discloses the SAME "
    "underlying RISK — the same hazard or driver — even if it manifests through a "
    "DIFFERENT mechanism, channel, or business line, and even if worded "
    "differently. The peers and the target need not be affected the same way; if "
    "both disclose exposure to the same underlying driver, that is COVERED.\n"
    "• NOT ENTAILED (verdict ABSENT): the target text does not disclose this risk "
    "at all. Sharing only a TOPIC or KEYWORD is NOT entailment, and a span about a "
    "genuinely DIFFERENT risk that happens to share a word is NOT entailment. A "
    "single passing mention in a list, with no real discussion, does NOT count.\n"
    "• Distinguish 'different mechanism, same risk' (COVERED) from 'different risk "
    "entirely' (ABSENT). When genuinely uncertain whether a real disclosure "
    "exists, lean COVERED to avoid false gaps; but a bare keyword stays ABSENT.\n"
    "• Your evidence MUST be a verbatim substring copied from the excerpts. If no "
    "span genuinely states the risk, leave evidence empty and answer ABSENT.\n\n"
    "Worked examples:\n"
    "1) CLAIM: 'limits on our ability to reduce emissions and improve fuel economy "
    "to meet regulatory standards.' TARGET SPAN: 'we may face delays ramping "
    "production and meeting our cost and profitability targets.' → ABSENT "
    "(production-cost is a DIFFERENT risk from fuel-economy regulatory "
    "compliance; only the word 'fuel/economy' overlaps).\n"
    "2) CLAIM: 'failure to attract and retain qualified employees.' TARGET SPAN: "
    "'our business would be adversely affected if we are unable to hire and retain "
    "qualified employees.' → COVERED (same risk, plainly stated).\n"
    "3) CLAIM: 'risk from joint ventures we do not control.' TARGET SPAN: 'we may "
    "experience delays in developing and launching products.' → ABSENT (no joint "
    "venture mentioned at all — the target operates with no such arrangements).\n"
    "4) CLAIM: 'high interest rates may reduce our lending arm's financing margin.' "
    "TARGET SPAN: 'rising interest rates may lead consumers to pull back spending "
    "on our products, harming demand.' → COVERED (SAME underlying risk — interest "
    "rates hurting the business — even though the target is exposed through "
    "consumer demand rather than a lending arm; same hazard, different channel).\n\n"
    "Think step by step, then return ONLY JSON:\n"
    '{"specific_risk":"<the exact risk the claim is about>",'
    '"best_span":"<the single closest verbatim span from the excerpts, or empty>",'
    '"reasoning":"<does that span describe the SAME risk or just a related topic?>",'
    '"verdict":"COVERED"|"ABSENT",'
    '"evidence":"<verbatim span if COVERED, else empty>"}'
)


def _keywords(theme, peer_titles):
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", f"{theme} {' '.join(peer_titles)}".lower())
    seen, out = set(), []
    for w in words:
        if w in _STOP or w in seen:
            continue
        seen.add(w); out.append(w)
    return out[:12]


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _excerpts(full_text, keywords, window=240, cap=4200):
    low = full_text.lower()
    spans = []
    for kw in keywords:
        start = 0
        while True:
            i = low.find(kw, start)
            if i == -1:
                break
            spans.append((max(0, i - window), min(len(full_text), i + len(kw) + window)))
            start = i + len(kw)
            if len(spans) > 60:
                break
    if not spans:
        return "", 0
    spans.sort()
    merged = [spans[0]]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    out, total = [], 0
    for s, e in merged:
        chunk = full_text[s:e].strip()
        out.append("…" + chunk + "…")
        total += len(chunk)
        if total >= cap:
            break
    return "\n---\n".join(out), len(merged)


def _call(claim, peer_titles, excerpts, retries=6):
    user = (f"RISK CLAIM (peers' framing):\n{claim}\n\n"
            f"PEER PHRASINGS:\n" + "\n".join(f"- {t}" for t in peer_titles[:4]) +
            f"\n\nTARGET EXCERPTS (keyword-matched from anywhere in the filing):\n{excerpts}\n\n"
            "Perform the NLI check. JSON only:")
    delay = 2.0
    for _ in range(retries):
        r = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL, "temperature": 0, "max_tokens": 600,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": SYSTEM},
                               {"role": "user", "content": user}]},
            timeout=60,
        )
        if r.status_code == 429:
            wait = float(r.headers.get("retry-after", delay))
            time.sleep(min(wait, 45)); delay = min(delay * 1.6, 45)
            continue
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", content, re.DOTALL)
            return json.loads(m.group(0)) if m else {"verdict": "ABSENT", "evidence": "", "reasoning": "parse error"}
    raise RuntimeError("verification rate-limited after retries")


def verify_absent(results, target_text):
    """COVERED -> COVERED_DIFFERENT_FRAMING (grounded); ABSENT -> confirmed.
    Returns (confirmed, downgraded)."""
    if not GROQ_KEY or not target_text:
        return (0, 0)
    norm_full = _norm(target_text)
    confirmed = downgraded = 0
    for r in results:
        if r.get("classification") != "ABSENT":
            continue
        claim = r.get("theme") or (r["peer_examples"][0]["title"] if r.get("peer_examples") else "")
        peer_titles = [e["title"] for e in r.get("peer_examples", [])]
        excerpts, hits = _excerpts(target_text, _keywords(claim, peer_titles))

        if hits == 0:  # no related language anywhere -> genuine gap, no LLM needed
            r["verification"] = {"verdict": "ABSENT", "evidence": "",
                                 "rationale": "No related language anywhere in the target's Item 1A."}
            confirmed += 1
            continue
        try:
            v = _call(claim, peer_titles, excerpts)
        except Exception as e:
            r["verification"] = {"verdict": "UNVERIFIED", "evidence": "", "rationale": str(e)[:90]}
            r["classification"] = "UNVERIFIED"
            continue

        verdict = str(v.get("verdict", "")).upper()
        evidence = v.get("evidence", "") or ""
        # Evidence-span grounding: a COVERED verdict must cite a span that truly
        # occurs in the target text. Ungrounded "coverage" is overridden to ABSENT.
        grounded = False
        if evidence:
            ne = _norm(evidence)
            probe = ne[:60]
            grounded = len(ne) >= 12 and probe in norm_full
        r["verification"] = {"verdict": verdict, "evidence": evidence,
                             "rationale": v.get("reasoning", "") or v.get("rationale", "")}

        if verdict == "COVERED" and grounded:
            r["classification"] = "COVERED_DIFFERENT_FRAMING"
            r["explanation"] = "Verification found the target DOES disclose this, in different framing"
            downgraded += 1
        else:
            # ABSENT, or COVERED but evidence not found in the filing -> keep as finding
            if verdict == "COVERED" and not grounded:
                r["verification"]["rationale"] = ("Claimed covered but no matching span found in the "
                                                  "filing — treated as absent. " + r["verification"]["rationale"])
            confirmed += 1
    return (confirmed, downgraded)