# BlindSpot — finding the risks a company *doesn't* disclose

**Move 37 · London Tech Week 2026 · Build track**

## The one idea

Every risk-factor analysis tool ever built reads a filing and tells you what's *in* it. BlindSpot does the opposite: it tells you what's **missing** — the risks a company's direct peers all disclose, that it does not.

This matters because of a property of language that breaks normal AI document tools: **absence is invisible to anyone reading a single document.** A human analyst, or an LLM, reading one company's 10-K cannot tell you what's been left out — there is nothing on the page to react to. You can only detect an omission by comparison. So BlindSpot reframes the question from *"what are this company's risks"* (which any summariser answers) to *"what do its peers flag that this one doesn't"* — a question that is only answerable cross-sectionally, across a peer set, never from the document alone.

That reframe turns a known *weakness* of language models — they can't notice what isn't there — into the entire product.

## What AI does here (and why it's not bolted on)

The hard part isn't reading filings; it's deciding when two differently-worded disclosures are *the same risk*, and when a peer's risk has *no equivalent* in the target. "Significant changes to interest rates could adversely affect results" (Morgan Stanley) and "rising rates may compress net interest margin" (a peer) are the same risk in different words — a keyword search misses this; an embedding model catches it. The semantic matching *is* the product. Without it, every wording difference would look like a gap. A second layer of AI judgement then verifies each candidate gap against the full filing as a natural-language-inference task — distinguishing a genuine omission from the same risk worded differently — which is what keeps the false-positive rate down.

## How it works

1. **Extract** — pull Item 1A (Risk Factors) for the target and each peer from SEC EDGAR via SEC-API's structured extractor (clean section text, no parsing heuristics).
2. **Structure** — an LLM converts each filing's prose into discrete risk factors, each carrying a *verbatim supporting quote* (the quote is both a hallucination guard and the evidence shown to the user).
3. **Consolidate** — collapse each company's risks to a comparable granularity by semantic clustering, so a coarse list and a fine list can be fairly compared.
4. **Cluster cross-sectionally** — embed every risk (MiniLM) and cluster across all companies into themes.
5. **Surface gaps** — a theme that ≥2 peers share but the target is absent from is a candidate.
6. **Classify honestly** — for each candidate, measure the target's closest semantic match: ABSENT (genuine gap), PARTIAL (touches it), or REWORDED (covers it differently). Only ABSENT is claimed as a finding.
7. **Verify against the full filing** — each candidate ABSENT gap is re-checked by a second LLM pass that reads the target's *entire* Item 1A and asks, in strict entailment terms, whether the company discloses that risk anywhere in different wording. If it does, the gap is downgraded to "covered, different framing" with the supporting quote. This catches the false positives semantic clustering produces (e.g. a risk the target frames differently from its peers) and is why the tool can stay silent on a near-identical peer set.
8. **Show receipts** — for every gap, display the peer disclosures (quoted, attributable) beside the target's closest risk and its similarity score. "Look for yourself," not "trust the model."

## What's real (execution)

A working end-to-end pipeline: fetch → structure → consolidate → cluster → classify → cached results → visual report. Results are cached and the report runs offline, so the analysis is deterministic and reproducible — the same run every time, no live API dependency in the demo.

## Honest limitations

A good tool should know where it breaks:

- **Peer selection is an analyst's judgement, not the model's.** Results are fully determined by who is in the peer set; a different set yields different gaps. We don't claim an objective peer set — we make it explicit and configurable.
- **Granularity parity is the central engineering challenge.** Filings structure risk factors very differently (bulleted summaries, sentence-headings, uncategorised prose). If one company's risks are extracted at a coarser grain than its peers', it can look falsely "absent." Consolidation mitigates this but does not fully eliminate it — every ABSENT finding must be verified against the target's full filing before it is relied upon.
- **ABSENT means absent-from-Item-1A, not absent-from-the-company.** A risk disclosed in MD&A or the proxy, but not Item 1A, will register as a gap. A production version would search across the full filing set.
- **Findings describe *relative* disclosure, never intent.** "Discloses less prominently than peers" is what the data supports; "hiding" is an inference the tool cannot and does not make.

## Who it's for

Compliance teams benchmarking their own disclosure against peers before filing; activist investors and short-sellers hunting under-disclosed exposure; audit committees; financial journalists.
