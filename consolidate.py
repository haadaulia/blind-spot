"""
consolidate.py — collapse each company's raw risks to a comparable
granularity, deterministically, with NO LLM calls.

The problem this solves: GS extracted at heading level (~24), peers at
sub-clause level (88-179). You cannot compare a coarse list to fine
lists — everything looks like a gap. Fix: cluster each company's risks
semantically and keep one representative per cluster, so every company
lands at the same ~heading granularity.

Uses the SAME MiniLM embeddings as the cross-company step (already a
dependency). Deterministic -> reproducible demo, no Groq, no rate limit.
"""
from collections import defaultdict

import numpy as np
from sklearn.cluster import AgglomerativeClustering


def consolidate_company(risks: list[dict], embeddings: np.ndarray,
                        distance_threshold: float = 0.45) -> list[dict]:
    """Collapse near-equivalent risks for ONE company to representatives.

    risks: that company's raw risks (same order as embeddings)
    embeddings: normalized MiniLM vectors for each risk's title
    Returns the representative risk per cluster (the fullest-stated one).
    """
    n = len(risks)
    if n <= 2:
        return risks

    labels = AgglomerativeClustering(
        n_clusters=None, metric="cosine", linkage="average",
        distance_threshold=distance_threshold,
    ).fit_predict(embeddings)

    groups = defaultdict(list)
    for idx, lab in enumerate(labels):
        groups[lab].append(idx)

    canonical = []
    for idxs in groups.values():
        # representative = member closest to the cluster centroid (most
        # central meaning), tie-broken toward the fuller statement
        centroid = embeddings[idxs].mean(axis=0)
        centroid /= (np.linalg.norm(centroid) + 1e-12)
        sims = embeddings[idxs] @ centroid
        best = idxs[int(np.argmax(sims))]
        canonical.append(risks[best])
    return canonical
