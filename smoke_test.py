"""
smoke_test.py — CLI wrapper over pipeline.run_analysis.

    python smoke_test.py                # default TARGET/PEERS below
    python smoke_test.py TSLA F GM RIVN # target then peers
"""
import sys
from pipeline import run_analysis

TARGET = "TSLA"
PEERS = ["F", "GM", "RIVN"]

if __name__ == "__main__":
    if len(sys.argv) > 2:
        target, peers = sys.argv[1], sys.argv[2:]
    else:
        target, peers = TARGET, PEERS
    out = run_analysis(target, peers, use_cache=True)
    res = out["results"]
    absent = [r for r in res if r["classification"] == "ABSENT"]
    print(f"\n{'='*70}\n  {out['target']} vs {', '.join(out['peers'])}  ·  "
          f"{len(res)} candidates · ABSENT {len(absent)}\n{'='*70}\n")
    for r in absent:
        print(f"[ABSENT {r['similarity']:.2f}] {r['theme'] or (r['peer_examples'][0]['title'][:60] if r['peer_examples'] else '')}")
        print(f"   disclosed by {', '.join(r['peers'])}; {out['target']} closest: "
              f"\"{r['closest_in_target']['title'][:70]}\"\n")
    print("Run `python build_report.py` for the HTML, or `uvicorn app:app` for the web app.")
