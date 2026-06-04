"""
sec.py — clean Item 1A (Risk Factors) extraction.

Architecture (the industry-standard split):

  • edgartools  → DISCOVERY ONLY. Resolve ticker → latest 10-K →
    the filing's primary-document URL + fiscal period. This is the
    thing edgartools is reliable at, and it's free.

  • SEC-API.io Extractor → EXTRACTION. Hand it the filing URL and
    item code "1A" and it returns clean, standardized Risk Factors
    text: no page-header noise, no Part II bleed, no XBRL, no encoding
    problems. This replaces the old legacy-fallback parsing entirely.

Caching: every fetched section is written to data/sections/<accession>_1A.txt.
If the cache file exists we never hit the API again. So each company
costs exactly ONE SEC-API call, ever — re-runs are free. The free tier
is 100 calls/month; a four-company run uses four.

Env (.env):
  SEC_API_KEY    — from https://sec-api.io/signup/free
  SEC_IDENTITY   — "Your Name your@email" (SEC requires this for edgar)
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from edgar import Company, set_identity
from sec_api import ExtractorApi

load_dotenv()

set_identity(os.getenv("SEC_IDENTITY", "Haad Aulia haad.aulia@hotmail.com"))

_SEC_API_KEY = os.getenv("SEC_API_KEY")
_extractor = ExtractorApi(_SEC_API_KEY) if _SEC_API_KEY else None

CACHE_DIR = Path(__file__).parent / "data" / "sections"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _primary_doc_url(filing) -> str:
    """Build the SEC Archives URL for the filing's primary .htm document.

    Constructed from CIK + accession + primary document filename, which is
    stable across edgartools versions. Falls back to filing.url if needed.
    """
    try:
        cik = int(filing.cik)
        acc_nodash = filing.accession_no.replace("-", "")
        doc = filing.primary_document
        if doc:
            return f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"
    except Exception:
        pass
    url = getattr(filing, "url", None)
    if url:
        return str(url)
    raise ValueError("Could not determine primary document URL for filing")


def _pick_filing(filings, period: str | None):
    """Pick the 10-K matching `period` (exact, then by year), else most recent.

    `filings` is a list sorted newest-first.
    """
    if period:
        for f in filings:
            if str(getattr(f, "period_of_report", "")) == period:
                return f
        year = period[:4]
        for f in filings:
            if str(getattr(f, "period_of_report", ""))[:4] == year:
                return f
    return filings[0]  # newest (list is sorted reverse by filing_date)


def get_risk_factors(ticker: str, period: str | None = None) -> dict:
    """Return clean Item 1A text for `ticker`, period-pinned if given.

    Returns: {ticker, name, filing_date, period, accession, url, risk_text}
    """
    company = Company(ticker)
    if company is None:
        raise ValueError(f"Ticker {ticker!r} not resolved")

    filings = company.get_filings(form="10-K")
    if filings is None or len(filings) == 0:
        raise ValueError(f"No 10-K filings for {ticker}")

    # Exclude amendments (10-K/A) — they patch specific items and usually
    # contain no Item 1A, which is what broke TSLA (it grabbed a 10-K/A).
    exact = [f for f in filings if str(getattr(f, "form", "")).upper() == "10-K"]
    if not exact:
        raise ValueError(f"No non-amended 10-K for {ticker}")
    exact.sort(key=lambda f: str(getattr(f, "filing_date", "")), reverse=True)

    filing = _pick_filing(exact, period)
    accession = filing.accession_no
    url = _primary_doc_url(filing)

    # ── Cache check: skip the API entirely if we've fetched this before ──
    cache_file = CACHE_DIR / f"{accession}_1A.txt"
    if cache_file.exists():
        risk_text = cache_file.read_text(encoding="utf-8")
        source = "cache"
    else:
        if _extractor is None:
            raise RuntimeError(
                "SEC_API_KEY not set. Add it to .env "
                "(free key: https://sec-api.io/signup/free)"
            )
        risk_text = _extractor.get_section(url, "1A", "text")
        if not risk_text or len(risk_text.strip()) < 500:
            raise ValueError(
                f"Extractor returned little/no Item 1A for {ticker} "
                f"({len(risk_text or '')} chars). URL: {url}"
            )
        cache_file.write_text(risk_text, encoding="utf-8")
        source = "api"

    return {
        "ticker": ticker,
        "name": getattr(company, "name", ticker),
        "filing_date": str(filing.filing_date),
        "period": str(getattr(filing, "period_of_report", "")),
        "accession": accession,
        "url": url,
        "risk_text": risk_text,
        "source": source,
    }


if __name__ == "__main__":
    for t in ["GS", "MS", "JPM", "BAC"]:
        try:
            d = get_risk_factors(t)
            print(f"{t:5s}  {d['period']}  {len(d['risk_text']):>7,} chars  "
                  f"[{d['source']:5s}]  {d['name'][:38]}")
        except Exception as e:
            print(f"{t:5s}  ERROR {type(e).__name__}: {e}")
