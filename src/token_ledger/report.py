"""Render the shared rows into one self-contained report.html (no server, no external files)."""
from __future__ import annotations

import json
from pathlib import Path

from .pricing import PRICES_DATE


def load_units(out_dir: Path) -> tuple[dict, set]:
    """({prompt id: canonical unit name}, {names flagged NEW}) from units/ and vocabulary.jsonl."""
    from .vocab import Vocabulary, read_assignments

    v = Vocabulary(out_dir)
    ids = {i: v.resolve(u) for i, u in read_assignments(out_dir).items()}
    return ids, {n for n, e in v.entries.items() if e.get("new")}


def build(rows: list[dict], units: dict, new_units: set, excerpts: dict, title: str) -> str:
    data = []
    for r in rows:
        data.append({
            "id": r["id"], "ts": r["ts"], "member": r.get("member"), "session": r.get("session"),
            "title": r.get("title"), "branch": r.get("branch"), "worktree": r.get("worktree"), "tag": r.get("tag"),
            "unit": units.get(r["id"]), "models": r.get("models", {}), "cost": r.get("cost"),
            "files": r.get("files", []), "excerpt": excerpts.get(r["id"]),
        })
    payload = json.dumps({"rows": data, "newUnits": sorted(new_units), "pricesDate": PRICES_DATE, "title": title},
                         ensure_ascii=False).replace("<", "\\u003c")  # no "</script>" or "<!--" can end the script
    return TEMPLATE.replace("__DATA__", payload).replace("__TITLE__", _esc(title))


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · token ledger</title>
<style>
:root{color-scheme:light dark;--bg:#f7f7f5;--panel:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e4e3de;--accent:#3b5bdb;--bar:#c5d0fa;--new:#c2410c}
@media (prefers-color-scheme:dark){:root{--bg:#15161a;--panel:#1d1f24;--ink:#ecebe6;--muted:#9a9a94;--line:#2c2e35;--accent:#8ea4ff;--bar:#34407a;--new:#fb923c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:20px;margin:0 0 2px}.sub{color:var(--muted);margin:0 0 20px;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:18px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}.kpi span{color:var(--muted);font-size:12px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:16px}
.filters{display:flex;flex-wrap:wrap;gap:8px}.filters label{display:flex;flex-direction:column;font-size:11px;color:var(--muted);gap:3px}
select{font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:5px 7px;width:150px}
.modes{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 12px}
.modes button{font:inherit;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:999px;padding:5px 12px;cursor:pointer}
.modes button[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:var(--panel)}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:11px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.03em}td.n,th.n{text-align:right}
.barcell{width:34%}.bar{height:10px;border-radius:5px;background:var(--bar)}.bar i{display:block;height:100%;border-radius:5px;background:var(--accent)}
.new{color:var(--new);font-size:11px;font-weight:600;margin-left:6px}.muted{color:var(--muted)}.files{color:var(--muted);font-size:12px}
.scroll{overflow-x:auto}h2{font-size:14px;margin:0 0 8px}
@media (max-width:640px){.barcell{display:none}.hide-sm{display:none}}
</style></head><body><main>
<h1>__TITLE__</h1><p class="sub" id="sub"></p>
<div class="kpis" id="kpis"></div>
<section class="panel"><div class="filters" id="filters"></div></section>
<section class="panel"><h2>Group by</h2><div class="modes" id="modes" role="group" aria-label="Group by"></div>
<div class="scroll"><table id="groups"></table></div></section>
<section class="panel"><h2>Most expensive prompts</h2><div class="scroll"><table id="prompts"></table></div></section>
</main>
<script>
const D=__DATA__;
const FIELDS={unit:"Work unit",tag:"Tag",branch:"Branch",worktree:"Worktree",member:"Member",model:"Model",day:"Day",session:"Session"};
const FILTERS=["member","branch","worktree","tag","unit","model"];
const st={mode:"unit",f:{},from:"",to:""};
const $=id=>document.getElementById(id);
const usd=v=>v==null?"—":"$"+(v<10?v.toFixed(2):v.toFixed(1));
const tok=v=>v>=1e9?(v/1e9).toFixed(1)+"B":v>=1e6?(v/1e6).toFixed(1)+"M":v>=1e3?(v/1e3).toFixed(0)+"K":String(v);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
// one record per (prompt, model) so model filters and grouping split mixed prompts correctly
const recs=D.rows.flatMap(r=>Object.entries(r.models).map(([m,u])=>({r,model:m,u,day:r.ts.slice(0,10)})));
const val=(x,k)=>k==="model"?x.model:k==="day"?x.day:k==="session"?(x.r.title||x.r.session):x.r[k];
function keep(x){if(st.from&&x.day<st.from)return false;if(st.to&&x.day>st.to)return false;
 return FILTERS.every(k=>!st.f[k]||String(val(x,k)??"(none)")===st.f[k]);}
function tot(xs){const t={cost:0,unknown:0,ids:new Set(),inp:0,out:0};for(const x of xs){t.ids.add(x.r.id);
 if(x.u.cost==null)t.unknown++;else t.cost+=x.u.cost;t.inp+=x.u.input+x.u.cache_read+x.u.cache_write;t.out+=x.u.output}return t}
function render(){const xs=recs.filter(keep),t=tot(xs);
 $("sub").textContent=`${D.rows.length} prompts in the ledger · cost at API list prices (${D.pricesDate})`;
 $("kpis").innerHTML=[["Cost",usd(t.cost)+(t.unknown?" +?":"")],["Prompts",t.ids.size],["Input incl. cache",tok(t.inp)],["Output",tok(t.out)],
  ["Per prompt",usd(t.ids.size?t.cost/t.ids.size:0)]].map(([k,v])=>`<div class="kpi"><b>${v}</b><span>${k}</span></div>`).join("");
 const g=new Map();for(const x of xs){const k=val(x,st.mode)??"(none)";(g.get(k)||g.set(k,[]).get(k)).push(x)}
 const rows=[...g].map(([k,v])=>[k,tot(v)]).sort((a,b)=>b[1].cost-a[1].cost),max=rows.length?rows[0][1].cost||1:1;
 $("groups").innerHTML=`<tr><th>${FIELDS[st.mode]}</th><th class="barcell"></th><th class="n">Cost</th><th class="n">Prompts</th><th class="n hide-sm">Input</th><th class="n hide-sm">Output</th></tr>`+
  rows.map(([k,v])=>`<tr><td>${esc(k)}${st.mode==="unit"&&D.newUnits.includes(k)?'<span class="new">NEW</span>':""}</td>
  <td class="barcell"><div class="bar"><i style="width:${(100*v.cost/max).toFixed(1)}%"></i></div></td>
  <td class="n">${usd(v.cost)}</td><td class="n">${v.ids.size}</td><td class="n hide-sm">${tok(v.inp)}</td><td class="n hide-sm">${tok(v.out)}</td></tr>`).join("");
 const byId=new Map();for(const x of xs){const p=byId.get(x.r.id)||{r:x.r,cost:0,models:[]};p.cost+=x.u.cost||0;p.models.push(x.model.replace("claude-",""));byId.set(x.r.id,p)}
 $("prompts").innerHTML=`<tr><th>When</th><th>Prompt</th><th class="hide-sm">Work unit · branch</th><th class="n">Cost</th></tr>`+
  [...byId.values()].sort((a,b)=>b.cost-a.cost).slice(0,25).map(p=>`<tr><td class="muted">${esc(p.r.ts.slice(5,16).replace("T"," "))}<br>${esc(p.r.member)}</td>
  <td>${p.r.excerpt?esc(p.r.excerpt):`<span class="muted">${esc(p.r.title||"(no excerpt — another member's prompt)")}</span>`}
  <div class="files">${esc(p.r.files.slice(0,3).join(", "))}${p.r.files.length>3?" …":""}</div></td>
  <td class="hide-sm">${esc(p.r.unit||"—")}<br><span class="muted">${esc(p.r.branch||"")}${p.r.tag?" · #"+esc(p.r.tag):""}</span></td>
  <td class="n">${usd(p.cost)}<br><span class="muted">${esc(p.models.join(", "))}</span></td></tr>`).join("");}
function setup(){const f=$("filters");
 const days=[...new Set(recs.map(x=>x.day))].sort(),dayOpts=days.map(d=>`<option>${esc(d)}</option>`).join("");
 f.innerHTML=`<label>From<select id="from"><option value="">Any</option>${dayOpts}</select></label><label>To<select id="to"><option value="">Any</option>${dayOpts}</select></label>`+FILTERS.map(k=>{
  const vs=[...new Set(recs.map(x=>String(val(x,k)??"(none)")))].sort();
  return `<label>${FIELDS[k]}<select data-k="${k}"><option value="">All</option>${vs.map(v=>`<option>${esc(v)}</option>`).join("")}</select></label>`}).join("");
 f.querySelectorAll("select").forEach(s=>s.onchange=()=>{st.f[s.dataset.k]=s.value;render()});
 $("from").onchange=e=>{st.from=e.target.value;render()};$("to").onchange=e=>{st.to=e.target.value;render()};
 const m=$("modes");m.innerHTML=["unit","tag","session","branch","worktree","model","day","member"].map(k=>`<button data-k="${k}" aria-pressed="${k===st.mode}">${FIELDS[k]}</button>`).join("");
 m.querySelectorAll("button").forEach(b=>b.onclick=()=>{st.mode=b.dataset.k;m.querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",x===b));render()});
 render();}
setup();
</script></body></html>
"""
