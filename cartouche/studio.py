"""One page for the whole run of one request: request, gather, sign-off, release, watch.

    cartouche page --request REQUEST/spec.json [--target BUILD] [--port 8790]

The agent gathered candidate clips into REQUEST/candidates/ (ct_chart, ct_wanted, ct_search, ct_offer), and
any rendered clip dropped into REQUEST/incoming/<function>/ is offered on the next poll.
Here the person watches them. A sign-off button stays off until that clip has played through once in
this page. Signing off copies the clip into its shelf slot and runs Cartouche's own `view` and `approve`
on those bytes, so the signal lock is of the clip the person watched. When every path is signed, the
person releases: Cartouche's own `release` writes REQUEST/build_input.json. From then the page shows the
build against that lock, sign by sign, for as long as it is open.

No AI takes part in anything this page does. It binds 127.0.0.1 only, serves only files under
REQUEST/candidates and REQUEST/library, and writes only the clip dictionary, the shelf slots, and the
release, each through Cartouche's own functions.
"""

from __future__ import annotations

import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from cartouche import gather
from cartouche.build_release import release
from cartouche.cartouche_compiler import CartoucheCompiler
from cartouche.clip_library import approve, load_dictionary, save_dictionary, view
from cartouche.page import build_reader
from cartouche.signal_stitcher import SignalStitcher


class Studio:
    def __init__(self, spec_path: Path, target: Path | None = None) -> None:
        self.spec_path = spec_path.resolve()
        self.base = self.spec_path.parent
        self.dictionary_path = self.base / "clip_dictionary.json"
        self.contract_path = self.base / "build_input.json"
        self.target = (target or self.base / "build").resolve()
        self.lock = threading.Lock()
        self._watch: Callable[[], dict[str, Any]] | None = None

    def spec(self) -> dict[str, Any]:
        return json.loads(self.spec_path.read_text(encoding="utf-8"))

    def released(self) -> dict[str, Any] | None:
        if not self.contract_path.is_file():
            return None
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        if contract.get("released") is not True:
            return None
        if contract.get("cartouche_sha256") != self._spec_sha():
            # The chart changed after release: the old lock is kept beside the new one, and the page goes
            # back to sign-off and release instead of showing a lock the spec no longer hashes to.
            aside = self.contract_path.with_name(f"build_input.{contract['cartouche_sha256'][:8]}.json")
            self.contract_path.rename(aside)
            self._watch = None
            return None
        return contract

    def _spec_sha(self) -> str:
        stamp = self.spec_path.stat().st_mtime_ns
        if getattr(self, "_sha_at", None) != stamp:
            track = SignalStitcher(self.spec(), base_dir=self.base).compile_montage_and_signals()
            self._sha, self._sha_at = CartoucheCompiler(track).compile_cartouche()["cartouche_sha256"], stamp
        return self._sha

    def state(self) -> dict[str, Any]:
        with self.lock:
            spec = self.spec()
            lines = gather.wanted(spec, self.dictionary_path, self.base)
            if not self.released():
                gather.sweep_incoming(spec, self.base)  # rendered clips dropped in incoming/<function>/
            for line in lines["lines"]:
                line["candidates"] = gather.candidates(spec, self.base, line["phrase"])
                source = self.base / (Path(line["slot"]).with_suffix("").as_posix() + ".source.json") if line["slot"] else None
                line["signed"] = (
                    json.loads(source.read_text(encoding="utf-8")) if source and source.is_file() and line["status"] == "approved" else None
                )
            contract = self.released()
            state: dict[str, Any] = {
                "request": spec.get("request", ""),
                "domain_id": spec.get("domain_id"),
                "interaction": spec.get("interaction"),
                "lines": lines["lines"],
                "counts": lines["counts"],
                "stage": "gather",
                "target": str(self.target),
                "paths": self.paths(spec),
            }
        if contract:
            watch = self._watch or build_reader(self.spec_path, self.contract_path, self.target)
            self._watch = watch
            state["stage"] = "watch"
            state["cartouche_sha256"] = contract["cartouche_sha256"]
            state["paths"] = f"{contract['paths_covered']}/{contract['paths']}"
            state["watch"] = watch()
        elif lines["counts"]["paths"] and lines["counts"]["paths_covered"] == lines["counts"]["paths"]:
            state["stage"] = "release"
        state["counts"]["paths_text"] = f"{lines['counts']['paths_covered']}/{lines['counts']['paths']}"
        return state

    def paths(self, spec: dict[str, Any]) -> list[list[dict[str, Any]]]:
        """Every way the interaction can go, root to end, as the lines in order."""

        from cartouche.broll_fetcher import BRollFetcher

        nodes = spec["nodes"]
        out = []
        for path in BRollFetcher(spec, base_dir=self.base).rehearsal_paths():
            items: list[dict[str, Any]] = []
            for k, nid in enumerate(path):
                if k:
                    heard = next((b.get("heard") for b in nodes[path[k - 1]].get("branches", []) if b.get("target_node") == nid), None)
                    if heard:
                        clip = gather.heard_clip(self.base, heard)
                        items.append({"heard": heard, "clip": str(clip.relative_to(self.base)) if clip.is_file() else None})
                items.append({"line": spec["b_roll_atoms"][nodes[nid]["token_id"]]["phrase"]})
            out.append(items)
        return out

    def sign_off(self, phrase: str, candidate_id: str) -> dict[str, Any]:
        with self.lock:
            if self.released():
                return {"signed": False, "reason": "already released; the lock does not change"}
            spec = self.spec()
            chosen = gather.choose(spec, self.dictionary_path, self.base, phrase, candidate_id)
            if not chosen["chosen"]:
                return {"signed": False, "reason": chosen["reason"]}
            dictionary = load_dictionary(self.dictionary_path)
            seen = view(dictionary, spec["interaction"], phrase, self.base)
            if not seen.get("seen"):
                return {"signed": False, "reason": f"view: {seen.get('reason', 'unseen')}"}
            entry = approve(dictionary, spec["interaction"], phrase, self.base)
            if entry.get("reason"):
                return {"signed": False, "reason": f"approve: {entry['reason']}"}
            save_dictionary(self.dictionary_path, dictionary)
            return {"signed": True, "phrase": phrase, "candidate": candidate_id, "signal_lock": entry.get("signal_lock")}

    def release(self) -> dict[str, Any]:
        with self.lock:
            if self.released():
                return {"released": True, "reason": "already released"}
            contract = release(self.spec(), load_dictionary(self.dictionary_path), self.base)
            if not contract["released"]:
                return {"released": False, "blocks": contract.get("blocks", [])}
            self.contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
            self.target.mkdir(parents=True, exist_ok=True) if self.target.suffix == "" else self.target.parent.mkdir(parents=True, exist_ok=True)
            return {"released": True, "cartouche_sha256": contract["cartouche_sha256"]}

    def media(self, rel: str) -> Path | None:
        path = (self.base / rel).resolve()
        for root in (self.base / "candidates", self.base / "library", self.base / "heard"):
            if root.resolve() in path.parents and path.is_file() and path.suffix == ".mp4":
                return path
        return None


def port_of(server: Any) -> int:
    return int(server.server_address[1])


def serve_studio(studio: Studio, port: int, ready: Callable[[str], None] | None = None) -> None:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: dict[str, Any], code: int = 200) -> None:
            self._send(code, json.dumps(data).encode("utf-8"), "application/json")

        def do_GET(self) -> None:  # noqa: N802 (the stdlib's name)
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, STUDIO_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/state.json":
                try:
                    self._json(studio.state())
                except (OSError, ValueError, KeyError) as error:
                    self._json({"error": f"{type(error).__name__}: {error}"[:300]}, 500)
            elif path.startswith("/media/"):
                from urllib.parse import unquote

                file = studio.media(unquote(path[len("/media/"):]))
                if file is None:
                    self.send_error(404)
                    return
                self._send(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "video/mp4")
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            own = f"http://127.0.0.1:{port_of(self.server)}"
            if self.headers.get("Origin") not in (None, own):
                self._json({"error": "cross-origin request refused"}, 403)
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._json({"error": "body is not JSON"}, 400)
                return
            if path == "/signoff":
                self._json(studio.sign_off(str(body.get("phrase", "")), str(body.get("candidate", ""))))
            elif path == "/release":
                self._json(studio.release())
            else:
                self.send_error(404)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 (the stdlib's name)
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port_of(server)}/"
    if ready:
        ready(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


STUDIO_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cartouche</title>
<style>
:root{--room:#151413;--panel:#1d1b19;--rule:#2c2926;--paper:#f4f0e6;--dim:#9a948a;--faint:#5c5750;
--gold:#e8b04a;--red:#d9533c;--ochre:#c9962c;--green:#10b981;--rust:#b4532f}
*{box-sizing:border-box}html,body{margin:0;background:var(--room);color:var(--paper);font:15px ui-monospace,"SF Mono",Menlo,Consolas,monospace}
header{display:flex;align-items:center;gap:22px;padding:16px 28px;border-bottom:1px solid var(--rule);position:sticky;top:0;background:var(--room);z-index:2}
.brand{font-size:22px;letter-spacing:.34em;font-weight:700}
.steps{display:flex;gap:8px;margin-left:12px}.steps span{padding:5px 11px;border:1px solid var(--rule);border-radius:999px;color:var(--faint);font-size:12px;letter-spacing:.1em;text-transform:uppercase}
.steps span.on{color:var(--room);background:var(--gold);border-color:var(--gold)}.steps span.done{color:var(--green);border-color:rgba(16,185,129,.5)}
.lock{margin-left:auto;color:var(--gold);font-size:13px}
.wrap{padding:22px 28px;max-width:1500px}
.request{border:1px solid var(--rule);border-radius:10px;padding:16px 18px;background:var(--panel);margin-bottom:18px}
.request b{color:var(--dim);font-weight:400;font-size:12px;letter-spacing:.14em;text-transform:uppercase;display:block;margin-bottom:6px}
.line{border:1px solid var(--rule);border-radius:10px;margin-bottom:16px;background:var(--panel);overflow:hidden}
.line.signed{border-color:rgba(16,185,129,.55)}
.lh{display:flex;gap:14px;align-items:baseline;padding:12px 16px 8px}
.lh .ph{font-size:17px}.lh .fn{color:var(--dim);font-size:12.5px}.lh .edge{color:var(--rust);font-size:11.5px;letter-spacing:.12em;text-transform:uppercase}
.lh .stepn{color:var(--gold);font-weight:700;min-width:1.4em}
.tree{padding:0 16px 10px 46px;color:var(--faint);font-size:12px;border-bottom:1px solid var(--rule);margin-top:-6px}
.line.edgecase{margin-left:34px;border-style:dashed}
.lh .st{margin-left:auto;font-size:12px;letter-spacing:.12em;text-transform:uppercase}
.cands{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;padding:14px 16px}
.cand{border:1px solid var(--rule);border-radius:8px;overflow:hidden;background:#11100f}
.cand.picked{border-color:var(--green)}
.cand video{display:block;width:100%;aspect-ratio:16/9;background:#000}
.cm{padding:9px 11px;font-size:12px;color:var(--dim);line-height:1.5}
.cm .t{color:var(--paper);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cm .lic{color:var(--faint)}
button{font:inherit;font-size:12.5px;letter-spacing:.08em;padding:8px 12px;border-radius:6px;border:1px solid var(--gold);background:transparent;color:var(--gold);cursor:pointer;margin:0 11px 11px}
button:disabled{border-color:var(--rule);color:var(--faint);cursor:default}
.none{padding:16px;color:var(--faint)}
.rel{display:flex;align-items:center;gap:18px;padding:16px 18px;border:1px solid var(--rule);border-radius:10px;margin-bottom:18px}
.rel button{margin:0;font-size:15px;padding:10px 18px}
.watch{display:grid;grid-template-columns:minmax(260px,36%) 1fr;gap:26px}
.glyph{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:22px;color:var(--paper);display:flex;align-items:center;justify-content:center;min-height:420px;position:sticky;top:76px;align-self:start;max-height:calc(100vh - 100px)}
.glyph>svg{width:100%;max-height:72vh}
.state{display:flex;align-items:baseline;gap:18px;padding:14px 18px;border:1px solid var(--rule);border-radius:10px;margin-bottom:14px}
.state .word{font-size:24px;letter-spacing:.18em;text-transform:uppercase;font-weight:700}.state .count{color:var(--dim)}
.row{display:grid;grid-template-columns:auto 1fr auto;gap:4px 14px;align-items:center;padding:10px 14px;border:1px solid var(--rule);border-radius:10px;background:var(--panel);margin-bottom:9px}
.row video{width:150px;aspect-ratio:16/9;border-radius:5px;grid-row:1/3;background:#000}
.row .fn{font-weight:700}.row .fault{text-transform:uppercase;letter-spacing:.12em;font-size:12.5px;text-align:right}
.row .meta{grid-column:2/4;color:var(--dim);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar{grid-column:1/-1;height:4px;border-radius:2px;background:var(--rule);overflow:hidden}.bar i{display:block;height:100%;width:0;transition:width .6s,background .6s}
.paths{border:1px solid var(--rule);border-radius:10px;background:var(--panel);padding:14px 16px;margin-bottom:18px}
.paths b{color:var(--dim);font-weight:400;font-size:12px;letter-spacing:.14em;text-transform:uppercase}
.pp{display:grid;grid-template-columns:minmax(300px,480px) 1fr;gap:16px;margin-top:10px}
.pp video{width:100%;aspect-ratio:16/9;background:#000;border-radius:8px}
.plist{display:flex;flex-direction:column;gap:6px;max-height:360px;overflow:auto;padding-right:6px}
.prow{display:flex;gap:8px;align-items:center;font-size:12px;color:var(--dim);flex-wrap:wrap}
.prow button{margin:0;padding:4px 9px;font-size:11.5px}
.chip{padding:3px 7px;border:1px solid var(--rule);border-radius:999px;white-space:nowrap}
.plist.tree{gap:2px;max-height:420px}
.tr{display:flex;align-items:baseline;gap:8px;padding:3px 6px 3px calc(8px + var(--d)*18px);border-left:2px solid transparent;font-size:12.5px}
.tr.ours .tt{color:var(--paper)}.tr.ours.signed .tt{color:var(--green)}
.tr.theirs .tt{color:var(--dim);font-style:italic}.tr .tq{color:var(--faint);font-size:11px;text-transform:uppercase;letter-spacing:.1em}
.tr .tn{color:var(--gold);font-weight:700;min-width:1.6em}.tr .ta{color:var(--faint);font-size:11.5px}
.tr.now{border-left-color:var(--gold);background:rgba(232,176,74,.07)}
.tp{margin:0;padding:1px 7px;font-size:11px;border-radius:4px}
.chip.heard{border-style:dashed;color:var(--faint);font-style:italic}
.chip.now{border-color:var(--gold);color:var(--gold)}.chip.signed{color:var(--green)}
.heardnext{display:flex;flex-wrap:wrap;gap:8px;padding:0 16px 14px;font-size:12px;color:var(--faint)}
.heardnext .hn{border:1px dashed var(--rule);border-radius:999px;padding:3px 9px;color:var(--dim);font-style:italic}
.msg{color:var(--red);font-size:13px;padding:0 11px 10px}
@media (max-width:760px){.wrap{padding:16px}header{padding:12px 16px;flex-wrap:wrap}.watch{grid-template-columns:1fr}.lock{margin-left:0}}
</style></head><body>
<header><div class="brand">CARTOUCHE</div>
<div class="steps"><span id="s-gather">1 gather</span><span id="s-sign">2 sign off</span><span id="s-release">3 release</span><span id="s-watch">4 watch</span></div>
<div class="lock" id="lock"></div></header>
<div class="wrap">
  <div class="request"><b>the request</b><div id="request"></div></div>
  <div class="paths" id="paths"></div>
  <div id="body"></div>
</div>
<script>
const COLOR={sealed:'var(--green)',missing:'var(--faint)',template:'var(--red)',locked:'var(--red)',skew:'var(--rust)','':'var(--faint)'};
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const media=p=>'media/'+p.split('/').map(encodeURIComponent).join('/');
const watched=new Set(); let built='', lastSvg='', busy=false;
function steps(s){const st=s.stage, signed=s.lines.filter(l=>l.status==='approved'||l.status==='reused').length, any=s.lines.some(l=>l.candidates.length);
  const set=(id,cls)=>document.getElementById(id).className=cls;
  set('s-gather', any?'done':'on'); set('s-sign', st==='gather'?(any?'on':''):'done');
  set('s-release', st==='release'?'on':(st==='watch'?'done':'')); set('s-watch', st==='watch'?'on':'');}
async function post(url,body){busy=true;try{return await (await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})})).json()}finally{busy=false}}
async function signOff(phrase,id,btn){btn.disabled=true;btn.textContent='signing off…';const r=await post('signoff',{phrase,candidate:id});
  if(!r.signed){btn.disabled=false;btn.textContent='sign off this clip';btn.insertAdjacentHTML('afterend',`<div class="msg">${esc(r.reason)}</div>`)} built='';tick(true)}
function signable(s){return (s.lines||[]).filter(l=>l.status!=='approved'&&l.status!=='reused').map(l=>({phrase:l.phrase,ids:l.candidates.filter(c=>watched.has(l.phrase+'|'+c.id)).map(c=>c.id)})).filter(x=>x.ids.length===1)}
async function signAll(btn){btn.disabled=true;for(const x of signable(lastState)){const r=await post('signoff',{phrase:x.phrase,candidate:x.ids[0]});if(!r.signed){alertBox(r.reason);break}}built='';tick(true)}
async function doRelease(btn){btn.disabled=true;const r=await post('release');if(!r.released){btn.disabled=false;alertBox((r.blocks||[]).join('\n')||r.reason)}built='';tick(true)}
function alertBox(t){document.getElementById('relmsg').textContent=t}
function gatherView(s){
  const rel=s.stage==='release'?`<div class="rel"><button onclick="doRelease(this)">release: lock these signed clips</button><span id="relmsg" class="count">every path is signed (${esc(s.counts.paths_text)})</span></div>`:'';
  const n=s.stage==='gather'?signable(s).length:0;
  const all=n>1?`<div class="rel"><button onclick="signAll(this)">sign off all ${n} clips you watched through</button><span id="relmsg" class="count">one watched clip per line; lines with two watched clips are left for you</span></div>`:'';
  return rel+all+s.lines.map(l=>{const signed=l.status==='approved'||l.status==='reused';
    const short=t=>'“'+esc(t.length>38?t.slice(0,36)+'…':t)+'”';
    const where=l.instead_of?`<div class="tree">${l.edge_case?'edge case, ':''}instead of ${short(l.instead_of)} · after ${l.after.map(short).join(' or ')}</div>`
      :((l.heard_before||[]).length?`<div class="tree">when they say ${l.heard_before.map(short).join(' or ')}</div>`
      :(l.after.length?`<div class="tree">after ${l.after.map(short).join(' or ')}</div>`:'<div class="tree">the first line</div>'));
    const head=`<div class="lh"><span class="stepn">${l.step}</span><span class="ph">“${esc(l.phrase)}”</span><span class="fn">${esc(l.function)}</span>${l.edge_case?'<span class="edge">edge case</span>':''}<span class="st" style="color:${signed?'var(--green)':'var(--dim)'}">${signed?'signed off':(l.candidates.length?l.candidates.length+' candidates':'searching…')}</span></div>${where}`;
    if(!l.candidates.length) return `<div class="line${l.edge_case?' edgecase':''}">${head}<div class="none">the agent has not offered a clip for this line yet</div></div>`;
    const picked=l.signed&&l.signed.id;
    const cards=l.candidates.map(c=>{const key=l.phrase+'|'+c.id;const can=!signed&&watched.has(key);
      return `<div class="cand${picked===c.id?' picked':''}"><video controls preload="metadata" src="${media(c.clip)}" data-key="${esc(key)}"></video>
      <div class="cm"><div class="t">${esc(c.title||c.page)}</div><div>${esc(c.why)}</div><div class="lic">${esc(c.source)} · ${esc(c.licence)} · ${esc(c.seconds)} s</div></div>
      ${signed?(picked===c.id?'<div class="cm" style="color:var(--green)">signed off</div>':''):`<button ${can?'':'disabled'} data-phrase="${esc(l.phrase)}" data-id="${esc(c.id)}">${can?'sign off this clip':'watch it through to sign off'}</button>`}</div>`}).join('');
    const next=(l.heard_next||[]).length?`<div class="heardnext"><span>they might say next:</span>${l.heard_next.map(h=>{const t=s.lines.find(x=>x.phrase===h.then);return `<span class="hn">“${esc(h.heard)}” → ${t?t.step:'?'}</span>`}).join('')}</div>`:'';
    return `<div class="line${signed?' signed':''}${l.edge_case?' edgecase':''}">${head}<div class="cands">${cards}</div>${next}</div>`}).join('');}
function watchView(s){const w=s.watch||{};const total=w.signs_total!=null?w.signs_total:(w.signs||[]).length;
  const word={sealed:['sealed','var(--green)'],open:['writing','var(--gold)'],waiting:['waiting for code','var(--dim)'],locked:['locked','var(--red)'],SYNTAX:['syntax','var(--red)']}[w.state]||[w.state||'—','var(--dim)'];
  const clipOf=fn=>{const l=s.lines.find(x=>x.function===fn);return l&&l.slot?media(l.slot):''};
  return `<div class="watch"><section class="glyph" id="glyph"></section><section>
   <div class="state" style="border-color:${w.state==='sealed'?'var(--green)':'var(--rule)'}"><span class="word" style="color:${word[1]}">${esc(word[0])}</span><span class="count">${w.signs_sealed||0} of ${total} signs sealed · ${esc(s.target)}</span></div>
   ${(w.signs||[]).map(r=>{const col=COLOR[r.fault]||'var(--ochre)';return `<div class="row"><video muted loop autoplay playsinline src="${clipOf(r.function)}"></video><span class="fn">${esc(r.function)}</span><span class="fault" style="color:${col}">${esc(r.fault||'not yet')}</span><span class="meta">${esc(r.sign)} · “${esc(r.phrase)}”${r.lines?` · lines ${r.lines[0]}-${r.lines[1]}`:''}</span><span class="bar"><i style="width:${Math.round((r.fidelity||0)*100)}%;background:${col}"></i></span></div>`}).join('')}
  </section></div>`}
let pathsBuilt='';
function clipFor(s,phrase){const l=s.lines.find(x=>x.phrase===phrase);if(!l)return null;
  if(l.signed&&l.slot)return media(l.slot); const c=l.candidates[0]; return c?media(c.clip):null}
function itemClip(s,it){return it.line?clipFor(s,it.line):(it.clip?media(it.clip):null)}
let routes=[];
function pathsView(s){if(!s.lines||!s.lines.length)return '';
  routes=[]; const by={}; s.lines.forEach(l=>by[l.phrase]=l); const seen=new Set();
  const root=s.lines.find(l=>l.step===1); if(!root)return '';
  const isSigned=l=>l&&(l.status==='approved'||l.status==='reused');
  const rows=[];
  const play=route=>{routes.push(route);return `<button class="tp" data-route="${routes.length-1}" title="play the conversation up to here">▶</button>`};
  function walk(l,route,depth){
    const here=route.concat([{line:l.phrase}]);
    const again=seen.has(l.phrase);
    rows.push(`<div class="tr ours${isSigned(l)?' signed':''}" style="--d:${depth}">${play(here)}<span class="tn">${l.step}</span><span class="tt">“${esc(l.phrase)}”</span>${again?'<span class="ta">↑ continues as above</span>':''}</div>`);
    if(again)return; seen.add(l.phrase);
    const heard=l.heard_next||[];
    if(heard.length){ heard.forEach(h=>{const t=by[h.then];if(!t)return;
        const hr=here.concat([{heard:h.heard,clip:h.clip||null}]);
        rows.push(`<div class="tr theirs" style="--d:${depth+1}">${play(hr)}<span class="tq">they say</span><span class="tt">“${esc(h.heard)}”</span></div>`);
        walk(t,hr,depth+2);}); }
    else (l.next||[]).forEach(n=>{const t=by[n];if(t)walk(t,here,depth+1)});
  }
  walk(root,[],0);
  const n=(s.paths||[]).length;
  return `<b>every way it can go · ${n} paths, each of our lines once · ▶ plays the conversation up to that point</b><div class="pp"><video id="pathvid" controls playsinline></video><div class="plist tree">${rows.join('')}</div></div>`}
function routeClip(s,it){ if(it.line)return clipFor(s,it.line);
  if(it.clip)return media(it.clip);
  for(const p of (s.paths||[]))for(const x of p)if(x.heard===it.heard&&x.clip)return media(x.clip); return null}
function playRoute(s,i,btn){const v=document.getElementById('pathvid');const r=routes[i];let k=0;
  document.querySelectorAll('.tr').forEach(x=>x.classList.remove('now')); if(btn)btn.parentElement.classList.add('now');
  const go=()=>{while(k<r.length&&!routeClip(s,r[k]))k++; if(k>=r.length)return; v.src=routeClip(s,r[k]);v.play();k++};
  v.onended=go;go()}
let lastState=null;
function wire(){
  document.querySelectorAll('button[data-route]').forEach(b=>{b.onclick=()=>playRoute(lastState,+b.dataset.route,b)});document.querySelectorAll('video[data-key]').forEach(v=>{v.onended=()=>{watched.add(v.dataset.key);built='';tick(true)}});
  document.querySelectorAll('button[data-id]').forEach(b=>{b.onclick=()=>signOff(b.dataset.phrase,b.dataset.id,b)});}
async function tick(once){
  if(busy){if(!once)setTimeout(tick,700);return}
  let s=null;try{s=await (await fetch('state.json',{cache:'no-store'})).json()}catch(e){}
  if(s&&!s.error){lastState=s;document.getElementById('request').textContent=s.request||s.domain_id;steps(s);
    const pv=document.getElementById('pathvid');const pathSig=JSON.stringify([s.paths,s.lines.map(l=>[l.status,l.candidates.length])]);
    if(s.stage!=='watch'&&pathSig!==pathsBuilt&&!(pv&&!pv.paused)){document.getElementById('paths').innerHTML=pathsView(s);pathsBuilt=pathSig;wire()}
    if(s.stage==='watch')document.getElementById('paths').style.display='none';
    document.getElementById('lock').textContent=s.cartouche_sha256?'lock '+s.cartouche_sha256.slice(0,16)+'…':'';
    const playing=[...document.querySelectorAll('video[data-key]')].some(v=>!v.paused&&!v.ended);
    if(s.stage==='watch'){const html=watchView(s);const sig=JSON.stringify((s.watch.signs||[]).map(r=>[r.fault,r.fidelity]))+s.watch.state;
      if(built!=='w'+sig){document.getElementById('body').innerHTML=html;built='w'+sig;lastSvg=''}
      if(s.watch.svg&&s.watch.svg!==lastSvg){const g=document.getElementById('glyph');if(g){g.innerHTML=s.watch.svg;lastSvg=s.watch.svg}}}
    else{const sig=JSON.stringify(s.lines.map(l=>[l.status,l.candidates.map(c=>c.id)]))+s.stage;
      if(built!==sig&&!playing){document.getElementById('body').innerHTML=gatherView(s);built=sig;wire()}}}
  if(!once)setTimeout(tick,700)}
tick();
</script></body></html>
"""
