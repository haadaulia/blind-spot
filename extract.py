"""
extract.py — LLM-based structured risk extraction (replaces regex splitting).

This is the current research-standard approach (Dolphin et al., 2026):
feed the clean Item 1A text to an LLM and get back individual risk
factors as structured JSON, each with a verbatim supporting quote.
The quote is both a hallucination guard (it must exist in the source)
and the "show receipts" evidence layer for the demo.

No heading heuristics, no length thresholds, no category regex. The LLM
handles bulleted summaries (GS), sentence-headings (MS), uncategorized
lists (Apple) and many-category lists (T-Mobile) natively.

Determinism + cost: temperature=0 and results cached to
data/risks/<accession>.json, so each company is extracted once, ever.
Re-runs and the live demo read the cache — zero network.
"""
import os
import re
import json
import time
import html
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.1-8b-instant"   # high free-tier throughput; extraction is mechanical

CHUNK_CHARS = 12000              # bigger chunks = more context for heading-vs-elaboration judgement
REQUEST_PAUSE = 1.5

CACHE_DIR = Path(__file__).parent / "data" / "risks"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = (
    "You extract the TOP-LEVEL named risk factors from a company's 10-K "
    "Item 1A text. A risk factor is a major, distinct risk that would appear "
    "as its own bold heading — e.g. 'Significant changes to interest rates "
    "could adversely affect our results of operations.' A large 10-K "
    "typically has 25–50 of these. If you extract more than ~50 from one "
    "filing, you are being far too granular.\n\n"
    "Return ONLY a JSON array, no prose or markdown fences. Each element: "
    '{"category": "<the section heading it sits under, or empty string>", '
    '"title": "<the risk as one concise sentence>", '
    '"quote": "<a short phrase copied verbatim from the text>"}.\n\n'
    "CRITICAL granularity rules:\n"
    "1. DO NOT split an enumerated list into separate risks. "
    "'Downturns can be caused by: pandemics; illiquid markets; political "
    "instability; high inflation' is ONE risk about adverse economic "
    "conditions — not four.\n"
    "2. DO NOT create a risk from a sentence that merely elaborates, gives "
    "an example of, or explains a risk you have already captured. Fold all "
    "supporting detail into the parent risk.\n"
    "3. DO NOT extract definitions of risk types (e.g. 'Market risk refers "
    "to the risk that...'), introductory sentences, page headers, or table "
    "markers.\n"
    "4. The quote MUST be copied verbatim from the provided text. Never "
    "invent a risk that is not stated.\n"
    "If a chunk contains no top-level risk factors, return []."
)

# Summary-slicing trades completeness for speed: it gives a clean but COARSE
# list (GS summary = 24 headings) that can't be fairly compared against peers'
# full-text lists. For honest gap detection every company must be extracted at
# the same source/granularity, so this is OFF by default — all use full text,
# and consolidate.py brings them to comparable granularity.
PREFER_SUMMARY = False

# GS-style filings repeat their risks: a clean bulleted summary, then a long
# prose elaboration introduced by this divider.
_SUMMARY_DIVIDER = re.compile(
    r"following are (?:the )?detailed descriptions of (?:our|the) risk factors",
    re.IGNORECASE,
)


def _prefer_summary(text: str) -> str:
    """If enabled and the section has a summary+detail split, keep the summary."""
    if not PREFER_SUMMARY:
        return text
    m = _SUMMARY_DIVIDER.search(text)
    if m and m.start() > 1500:   # ensure there's a real summary before the divider
        return text[:m.start()]
    return text


def _clean(text: str) -> str:
    """Decode HTML entities and drop page-break table markers + their content."""
    text = re.sub(r"##TABLE_START.*?##TABLE_END", " ", text, flags=re.DOTALL)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ")
    return text


def _chunk(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Accumulate paragraphs into ~`size`-char chunks on paragraph boundaries."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) > size:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def _parse_json_array(content: str) -> list[dict]:
    """Strip any fences and parse a JSON array; tolerate minor model noise."""
    s = content.strip()
    s = re.sub(r"^```(?:json)?|```$", "", s.strip(), flags=re.MULTILINE).strip()
    start, end = s.find("["), s.rfind("]")
    if start != -1 and end != -1:
        s = s[start:end + 1]
    try:
        data = json.loads(s)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _extract_chunk(chunk: str) -> list[dict]:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Item 1A text chunk:\n\n{chunk}\n\nJSON array:"},
        ],
        "temperature": 0,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }

    # Free-tier rate limits (esp. tokens-per-minute) throw 429. Back off and
    # retry, honouring Groq's Retry-After hint when present.
    for attempt in range(6):
        r = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        if r.status_code == 429:
            wait = float(r.headers.get("retry-after", 0)) or (8 * (attempt + 1))
            try:
                msg = r.json().get("error", {}).get("message", "")[:120]
            except Exception:
                msg = ""
            print(f"    rate-limited; waiting {wait:.0f}s (attempt {attempt + 1}/6) {msg}", flush=True)
            time.sleep(wait + 1)
            continue
        r.raise_for_status()
        break
    else:
        raise RuntimeError("Groq kept rate-limiting after 6 retries — wait a minute and rerun (progress is cached)")

    content = r.json()["choices"][0]["message"]["content"]
    # response_format json_object can wrap the array in a key; handle both
    parsed = _parse_json_array(content)
    if parsed:
        return parsed
    try:
        obj = json.loads(content)
        for v in obj.values():
            if isinstance(v, list):
                return v
    except Exception:
        pass
    return []


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())[:80]


def extract_risks(text: str, accession: str | None = None, ticker: str | None = None,
                  use_cache: bool = True) -> list[dict]:
    """Extract risks from Item 1A text. Cached by accession when provided.

    Resumable: progress is saved after every chunk to <accession>.progress.json,
    so a crash or hard rate-limit loses nothing — just rerun and it continues.
    """
    cache_file = CACHE_DIR / f"{accession}.json" if accession else None
    if use_cache and cache_file and cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    if not GROQ_KEY:
        raise RuntimeError("GROQ_API_KEY not set in .env")

    chunks = _chunk(_prefer_summary(_clean(text)))

    # Resume from saved progress if a previous run was interrupted
    progress_file = CACHE_DIR / f"{accession}.progress.json" if accession else None
    risks, seen, start = [], set(), 0
    if progress_file and progress_file.exists():
        prog = json.loads(progress_file.read_text(encoding="utf-8"))
        risks = prog["risks"]
        seen = {_norm(r["title"]) for r in risks}
        start = prog["next_chunk"]
        print(f"    resuming from chunk {start + 1}/{len(chunks)} ({len(risks)} risks so far)")

    for idx in range(start, len(chunks)):
        for item in _extract_chunk(chunks[idx]):
            title = (item.get("title") or "").strip()
            if not title:
                continue
            key = _norm(title)
            if not key or key in seen:
                continue
            seen.add(key)
            risks.append({
                "ticker": ticker or "",
                "category": (item.get("category") or "").strip(),
                "title": title,
                "quote": (item.get("quote") or "").strip(),
            })
        if progress_file:
            progress_file.write_text(
                json.dumps({"next_chunk": idx + 1, "risks": risks}), encoding="utf-8")
        if idx < len(chunks) - 1:
            time.sleep(REQUEST_PAUSE)

    if cache_file:
        cache_file.write_text(json.dumps(risks, indent=2), encoding="utf-8")
    if progress_file and progress_file.exists():
        progress_file.unlink()  # clean up; final cache is authoritative
    if len(risks) > 70:
        print(f"    WARNING: {len(risks)} risks is high (expected ~25-50). "
              f"Extraction may be over-firing on this filing.")
    return risks


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    from sec import get_risk_factors

    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "GS"
    d = get_risk_factors(ticker)
    print(f"{ticker}: {len(d['risk_text']):,} chars  ->  extracting...\n")
    risks = extract_risks(d["risk_text"], accession=d["accession"], ticker=ticker)
    print(f"Extracted {len(risks)} risks:\n")
    for i, r in enumerate(risks, 1):
        print(f"[{i:>2}] ({r['category'] or '—'}) {r['title']}")
        print(f"     quote: \"{r['quote'][:100]}\"")
