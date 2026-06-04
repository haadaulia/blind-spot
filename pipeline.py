"""
pipeline.py — the BlindSpot analysis as one reusable function.

run_analysis(target, peers) → results dict (also cached to data/runs/<key>.json
and mirrored to data/last_run.json). Used by both smoke_test.py (CLI) and
app.py (FastAPI). The embedding model is loaded once and reused.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering

from sec import get_risk_factors
from extract import extract_risks
from consolidate import consolidate_company
from label import label_theme
from verify import verify_absent

CONSOLIDATE_THRESHOLD = 0.45
DISTANCE_THRESHOLD = 0.40
MIN_PEER_AGREEMENT = 2
ABSENT_BELOW = 0.50
REWORDED_ABOVE = 0.65

DATA = Path(__file__).parent / "data"
RUNS = DATA / "runs"
RUNS.mkdir(parents=True, exist_ok=True)

_MODEL = None
def _model():
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def _key(target, peers):
    return re.sub(r"[^A-Za-z0-9]", "", target + "_" + "_".join(peers))


def _classify(sim):
    if sim < ABSENT_BELOW:
        return "ABSENT", "No semantically close coverage in the target — likely genuine gap"
    if sim < REWORDED_ABOVE:
        return "PARTIAL", "Target touches adjacent topics but doesn't match closely"
    return "REWORDED", "Target appears to cover this in different language"


def _process(ticker, period=None, log=print):
    try:
        d = get_risk_factors(ticker, period=period)
        risks = extract_risks(d["risk_text"], accession=d["accession"], ticker=ticker)
        log(f"  [{ticker}] {len(risks)} risks")
        return {**d, "risks": risks}
    except Exception as e:
        log(f"  [{ticker}] FAILED: {type(e).__name__}: {e}")
        return {"ticker": ticker, "name": ticker, "period": "", "filing_date": "",
                "accession": "", "risks": []}


def run_analysis(target, peers, use_cache=True, label=True, log=print):
    target = target.upper().strip()
    peers = [p.upper().strip() for p in peers if p.strip()]
    cache_file = RUNS / f"{_key(target, peers)}.json"
    if use_cache and cache_file.exists():
        out = json.loads(cache_file.read_text(encoding="utf-8"))
        (DATA / "last_run.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
        return out

    log(f"Target {target} vs {', '.join(peers)}")
    tgt = _process(target, log=log)
    if not tgt["risks"]:
        raise RuntimeError(f"Couldn't process target {target} (no Item 1A risks extracted)")
    period = tgt["period"]
    companies = [tgt] + [_process(p, period=period, log=log) for p in peers]

    model = _model()
    for c in companies:
        if len(c["risks"]) > 2:
            emb = model.encode([r["title"] for r in c["risks"]],
                               convert_to_numpy=True, normalize_embeddings=True)
            c["risks"] = consolidate_company(c["risks"], emb, CONSOLIDATE_THRESHOLD)
    sizes = {c["ticker"]: len(c["risks"]) for c in companies}
    log(f"consolidated sizes: {sizes}")

    corpus = [{"ticker": c["ticker"], "category": r.get("category", ""),
               "title": r["title"], "quote": r.get("quote", "")}
              for c in companies for r in c["risks"]]

    embeddings = model.encode([f"{x['title']} {(x['quote'] or '')[:300]}".strip() for x in corpus],
                              convert_to_numpy=True, normalize_embeddings=True)
    labels = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average",
                                     distance_threshold=DISTANCE_THRESHOLD).fit_predict(embeddings)

    theme_t, theme_ex, theme_i = defaultdict(set), defaultdict(list), defaultdict(list)
    for idx, (item, tid) in enumerate(zip(corpus, labels)):
        theme_t[tid].add(item["ticker"]); theme_ex[tid].append(item); theme_i[tid].append(idx)

    tgt_idx = [i for i, x in enumerate(corpus) if x["ticker"] == target]
    tgt_emb = embeddings[tgt_idx]
    tgt_local = [corpus[i] for i in tgt_idx]
    valid_peers = {c["ticker"] for c in companies if c["risks"]} - {target}

    cands = []
    for tid, ticks in theme_t.items():
        if target in ticks or len(ticks & valid_peers) < MIN_PEER_AGREEMENT:
            continue
        pidx = [theme_i[tid][k] for k, e in enumerate(theme_ex[tid]) if e["ticker"] in valid_peers]
        centroid = embeddings[pidx].mean(axis=0); centroid /= (np.linalg.norm(centroid) + 1e-12)
        sims = tgt_emb @ centroid
        best = int(sims.argmax()); best_sim = float(sims[best])
        cls, expl = _classify(best_sim)
        cands.append({"peers": sorted({e["ticker"] for e in theme_ex[tid]} & valid_peers),
                      "peer_count": len(ticks & valid_peers), "examples": theme_ex[tid],
                      "closest": tgt_local[best], "similarity": best_sim,
                      "classification": cls, "explanation": expl})

    order = {"ABSENT": 0, "PARTIAL": 1, "REWORDED": 2}
    cands.sort(key=lambda c: (order[c["classification"]], c["similarity"]))

    def theme_label(c):
        if not label:
            return ""
        try:
            return label_theme([f"{e['title']} {e['quote']}" for e in c["examples"]])
        except Exception:
            return ""

    out = {"target": target, "peers": sorted(valid_peers), "period": period,
           "sizes": sizes,
           "results": [{
               "rank": i + 1, "theme": theme_label(c) if c["classification"] == "ABSENT" else "",
               "classification": c["classification"], "similarity": round(c["similarity"], 3),
               "peers": c["peers"],
               "peer_examples": [{"ticker": e["ticker"], "title": e["title"], "quote": e["quote"]}
                                 for e in c["examples"] if e["ticker"] in c["peers"]][:3],
               "closest_in_target": {"title": c["closest"]["title"], "quote": c["closest"]["quote"]},
           } for i, c in enumerate(cands)]}

    # Auto-verification: re-check each ABSENT gap against the target's FULL
    # Item 1A text to catch risks disclosed in different framing (kills the
    # interest-rate / climate style false positives).
    try:
        confirmed, downgraded = verify_absent(out["results"], tgt.get("risk_text", ""))
        out["verification"] = {"confirmed": confirmed, "downgraded": downgraded}
        vorder = {"ABSENT": 0, "COVERED_DIFFERENT_FRAMING": 1, "UNVERIFIED": 2, "PARTIAL": 3, "REWORDED": 4}
        out["results"].sort(key=lambda r: (vorder.get(r["classification"], 9), r["similarity"]))
        for i, r in enumerate(out["results"]):
            r["rank"] = i + 1
        log(f"verification: {confirmed} confirmed absent, {downgraded} downgraded to covered")
    except Exception as e:
        log(f"verification skipped: {e}")

    cache_file.write_text(json.dumps(out, indent=2), encoding="utf-8")
    (DATA / "last_run.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
