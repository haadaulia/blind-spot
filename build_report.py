"""
build_report.py — turn data/last_run.json into a self-contained report.html.

Run after smoke_test.py:   python build_report.py
Opens offline, no server, data inlined — ideal for a demo / Loom recording
and for the venue (no network needed).
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent
RUN = ROOT / "data" / "last_run.json"
OUT = ROOT / "report.html"

data = json.loads(RUN.read_text(encoding="utf-8"))
payload = json.dumps(data).replace("</", "<\\/")

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BlindSpot — peer-set risk gap analysis</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root{
    --ink:#0d0e11; --panel:#15171c; --panel2:#1b1e25; --line:#2a2e38;
    --paper:#ece6da; --muted:#8c93a1; --dim:#5a606e;
    --absent:#e8a13a; --partial:#6fa8c7; --reworded:#5a606e;
    --serif:"Fraunces",Georgia,serif; --mono:"IBM Plex Mono",monospace;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--ink);color:var(--paper);
    font-family:var(--mono);font-size:15px;line-height:1.6;
    -webkit-font-smoothing:antialiased}
  .wrap{max-width:1040px;margin:0 auto;padding:64px 28px 120px}
  .eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.32em;
    text-transform:uppercase;color:var(--absent);margin-bottom:18px}
  h1{font-family:var(--serif);font-weight:500;font-size:clamp(40px,7vw,72px);
    line-height:.98;letter-spacing:-.02em;margin:0 0 8px}
  h1 em{font-style:italic;color:var(--absent)}
  .sub{font-family:var(--serif);font-size:21px;font-style:italic;
    color:var(--muted);margin:0 0 40px;max-width:60ch;line-height:1.4}
  .meta{display:flex;flex-wrap:wrap;gap:0;border:1px solid var(--line);
    border-radius:10px;overflow:hidden;margin-bottom:14px}
  .meta div{padding:16px 22px;border-right:1px solid var(--line);flex:1;min-width:140px}
  .meta div:last-child{border-right:none}
  .meta .k{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);margin-bottom:6px}
  .meta .v{font-family:var(--serif);font-size:26px;color:var(--paper)}
  .meta .v.amber{color:var(--absent)}
  .note{font-size:12.5px;color:var(--dim);margin:0 0 52px;line-height:1.6}
  .sec-label{font-family:var(--mono);font-size:11px;letter-spacing:.28em;
    text-transform:uppercase;color:var(--muted);margin:48px 0 18px;
    display:flex;align-items:center;gap:14px}
  .sec-label::after{content:"";flex:1;height:1px;background:var(--line)}
  .gap{border:1px solid var(--line);border-radius:12px;background:var(--panel);
    margin-bottom:18px;overflow:hidden}
  .gap.absent{border-color:#3a2f1c;background:linear-gradient(180deg,#191510,var(--panel))}
  .gap-head{padding:22px 26px;display:flex;justify-content:space-between;
    align-items:flex-start;gap:20px}
  .gap-title{font-family:var(--serif);font-size:23px;line-height:1.2;margin:0;color:var(--paper)}
  .badge{font-family:var(--mono);font-size:10px;letter-spacing:.14em;
    text-transform:uppercase;padding:6px 11px;border-radius:100px;white-space:nowrap;
    border:1px solid currentColor}
  .badge.ABSENT{color:var(--absent)} .badge.PARTIAL{color:var(--partial)}
  .badge.REWORDED{color:var(--reworded)}
  .disclosed{padding:0 26px 6px;font-size:12.5px;color:var(--muted)}
  .disclosed b{color:var(--paper)}
  .body{padding:8px 26px 24px;display:grid;grid-template-columns:1fr 1fr;gap:1px;
    background:var(--line);border-top:1px solid var(--line);margin-top:14px}
  .col{background:var(--panel);padding:20px 22px}
  .col.target{background:var(--panel2)}
  .col h4{font-family:var(--mono);font-size:10px;letter-spacing:.2em;
    text-transform:uppercase;margin:0 0 14px}
  .col.peers h4{color:var(--partial)} .col.target h4{color:var(--absent)}
  .item{margin-bottom:14px;padding-bottom:14px;border-bottom:1px dashed var(--line)}
  .item:last-child{margin-bottom:0;padding-bottom:0;border-bottom:none}
  .tick{font-size:10px;font-weight:600;letter-spacing:.1em;color:var(--dim);display:block;margin-bottom:4px}
  .item .t{font-family:var(--serif);font-size:15px;color:var(--paper);line-height:1.35}
  .item .q{font-size:11.5px;color:var(--muted);margin-top:6px;line-height:1.5;
    border-left:2px solid var(--line);padding-left:10px}
  .sim{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:10px}
  .sim b{color:var(--absent)}
  .empty{font-size:13px;color:var(--dim);font-style:italic;font-family:var(--serif)}
  footer{margin-top:80px;padding-top:28px;border-top:1px solid var(--line);
    font-size:11.5px;color:var(--dim);line-height:1.7}
  @media(max-width:680px){.body{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <div class="eyebrow">Peer-set disclosure analysis</div>
  <h1>Blind<em>Spot</em></h1>
  <p class="sub">Absence is invisible to anyone reading a single filing. This finds the risks a company's peers disclose — and it does not.</p>

  <div class="meta" id="meta"></div>
  <p class="note" id="note"></p>

  <div id="findings"></div>

  <footer>
    <b>How it works.</b> For each company, BlindSpot pulls the Risk Factors section (Item 1A) of its
    latest annual report, uses an LLM to break it into individual risks (each kept with a verbatim quote),
    then groups similar risks across all the companies by meaning — not keywords. A risk the peers share
    but the target never matches is flagged as a gap, and a second pass re-reads the target's full filing
    to throw out anything it actually discloses in different words.<br><br>
    <b>Reading the scores.</b> Match strength (0–100) is how closely the target's nearest risk matches the
    peers' — by meaning, not wording. <b>65+</b> the target clearly covers it · <b>50–64</b> partial overlap ·
    <b>below 50</b> no real match, counted as a genuine gap.<br><br>
    Findings show <em>relative</em> disclosure — what a company says less about than its peers — never a
    claim about intent. Always confirm a flagged gap against the original filing before relying on it.
  </footer>
</div>

<script>
const DATA = __PAYLOAD__;
const results = DATA.results || [];
const absent = results.filter(r=>r.classification==="ABSENT");
const order = {ABSENT:0,PARTIAL:1,REWORDED:2};
results.sort((a,b)=>(order[a.classification]-order[b.classification])||(a.similarity-b.similarity));

document.getElementById("meta").innerHTML = `
  <div><div class="k">Target</div><div class="v">${DATA.target||"—"}</div></div>
  <div><div class="k">Peer set</div><div class="v" style="font-size:18px">${(DATA.peers||[]).join(" · ")}</div></div>
  <div><div class="k">Period</div><div class="v" style="font-size:18px">${DATA.period||"—"}</div></div>
  <div><div class="k">Candidate gaps</div><div class="v">${results.length}</div></div>
  <div><div class="k">Genuinely absent</div><div class="v amber">${absent.length}</div></div>`;

document.getElementById("note").textContent =
  `${results.length} candidate gaps surfaced · ${absent.length} classified as genuinely absent from ${DATA.target}'s Item 1A · the rest the target covers in adjacent or reworded language.`;

function gapCard(r, i){
  const peers = (r.peer_examples||[]).map(p=>`
    <div class="item"><span class="tick">${p.ticker}</span>
      <div class="t">${esc((p.title||p.heading))}</div>
      ${(p.quote||p.body)?`<div class="q">${esc(p.quote||p.body)}</div>`:""}
    </div>`).join("");
  const ct = r.closest_in_target||{}; const ctT=ct.title||ct.heading; const ctQ=ct.quote||ct.body;
  const heading = (r.peer_examples&&r.peer_examples[0]&&(r.peer_examples[0].title||r.peer_examples[0].heading))||"Risk theme";
  return `
  <div class="gap ${r.classification==="ABSENT"?"absent":""}">
    <div class="gap-head">
      <h3 class="gap-title">${esc(shorten(heading))}</h3>
      <span class="badge ${r.classification}">${r.classification} · ${Math.round(r.similarity*100)}/100</span>
    </div>
    <div class="disclosed">Disclosed by <b>${(r.peers||[]).join(", ")}</b> — ${DATA.target} has no close match</div>
    <div class="body">
      <div class="col peers"><h4>What the peers disclose</h4>${peers}</div>
      <div class="col target"><h4>Closest in ${DATA.target}</h4>
        ${ctT?`<div class="item"><div class="t">${esc(ctT)}</div>${ctQ?`<div class="q">${esc(ctQ)}</div>`:""}<div class="sim">match strength <b>${Math.round(r.similarity*100)}/100</b> — below the 50-point line we count as covered</div></div>`:`<div class="empty">No semantically close risk found.</div>`}
      </div>
    </div>
  </div>`;
}
function esc(s){return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]))}
function shorten(s){s=s||"";return s.length>110?s.slice(0,107)+"…":s}

let html="";
if(absent.length){html+=`<div class="sec-label">Genuinely absent — the findings</div>`+absent.map(gapCard).join("");}
const rest=results.filter(r=>r.classification!=="ABSENT");
if(rest.length){html+=`<div class="sec-label">Partial &amp; reworded — target covers these</div>`+rest.map(gapCard).join("");}
if(!results.length){html=`<p class="empty">No candidate gaps surfaced — the target discloses comparably to its peers across all clustered themes.</p>`;}
document.getElementById("findings").innerHTML=html;
</script>
</body>
</html>"""

OUT.write_text(HTML.replace("__PAYLOAD__", payload), encoding="utf-8")
print(f"Wrote {OUT}  ({len(data.get('results', []))} gaps)")