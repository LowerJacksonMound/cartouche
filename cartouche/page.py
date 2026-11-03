"""The live page: the cartouche filling in while the build is written. It only reads.

Two ways to feed it:
  cartouche page --session SESSION         follow the session file `cartouche start` writes
  cartouche page SPEC CONTRACT TARGET      look at the build itself, the same comparison as ct_look,
                                           for a build watched through the MCP server (ct_watch)

It binds 127.0.0.1 only. It writes nothing: not the build, not the request, not the release.
The MCP server never opens a port; this command is the only thing that does.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from cartouche.live import live_view

DEFAULT_PORT = 8790


def session_reader(session_path: Path) -> Callable[[], dict[str, Any]]:
    def read() -> dict[str, Any]:
        if not session_path.is_file():
            return {"state": "waiting", "note": f"no session yet at {session_path}", "signs": []}
        try:
            state = json.loads(session_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"state": "waiting", "note": "the session file is being written", "signs": []}
        state.setdefault("signs", [])
        state["source"] = "session"
        return state

    return read


def build_reader(spec_path: Path, contract_path: Path, target: Path, every: float = 0.5) -> Callable[[], dict[str, Any]]:
    """Look at the build at most once per `every` seconds, however many pages are open."""

    lock = threading.Lock()
    cache: dict[str, Any] = {"at": 0.0, "state": {}}

    def read() -> dict[str, Any]:
        with lock:
            now = time.time()
            if not cache["state"] or now - cache["at"] >= every:
                try:
                    spec_data = json.loads(spec_path.read_text(encoding="utf-8"))
                    contract = json.loads(contract_path.read_text(encoding="utf-8"))
                    view = live_view(spec_data, contract, target, spec_path.parent)
                    view.update(
                        {
                            "source": "build",
                            "target": str(target),
                            "cartouche_sha256": contract.get("cartouche_sha256"),
                            "updated": now,
                        }
                    )
                    issues = []
                    for sign in view["signs"]:
                        if sign["fault"] and sign["fault"] != "sealed":
                            where = f" lines={sign['lines'][0]}-{sign['lines'][1]}" if sign.get("lines") else ""
                            issues.append(f"fault={sign['fault']} function={sign['function']} sign={sign['sign']}{where}")
                    view["issues"] = issues
                except (OSError, ValueError, KeyError) as error:
                    view = {"state": "waiting", "note": f"{type(error).__name__}: {error}"[:300], "signs": []}
                cache.update({"at": now, "state": view})
            state: dict[str, Any] = cache["state"]
            return state

    return read


def serve(read: Callable[[], dict[str, Any]], port: int = DEFAULT_PORT, ready: Callable[[str], None] | None = None) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (the stdlib's name)
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                body, kind = PAGE.encode("utf-8"), "text/html; charset=utf-8"
            elif path == "/state.json":
                body, kind = json.dumps(read()).encode("utf-8"), "application/json"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 (the stdlib's name)
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    if ready:
        ready(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cartouche</title>
<style>
:root{--room:#151413;--panel:#1d1b19;--rule:#2c2926;--paper:#f4f0e6;--dim:#9a948a;--faint:#5c5750;
--gold:#e8b04a;--red:#d9533c;--lapis:#2f5aa0;--ochre:#c9962c;--green:#10b981;--rust:#b4532f}
*{box-sizing:border-box}
html,body{margin:0;background:var(--room);color:var(--paper);font:15px ui-monospace,"SF Mono",Menlo,Consolas,monospace}
header{display:flex;align-items:center;gap:22px;padding:18px 28px;border-bottom:1px solid var(--rule)}
.brand{font-size:22px;letter-spacing:.34em;font-weight:700}
.live{display:flex;align-items:center;gap:8px;color:var(--dim);font-size:13px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--gold);animation:pulse 1.6s infinite}
.dot.off{background:var(--faint);animation:none}
@keyframes pulse{50%{opacity:.25}}
.lock{margin-left:auto;color:var(--gold);font-size:13px}
main{display:grid;grid-template-columns:minmax(260px,38%) 1fr;gap:28px;padding:24px 28px}
.glyph{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:22px;color:var(--paper);display:flex;align-items:center;justify-content:center;min-height:420px;position:sticky;top:76px;align-self:start;max-height:calc(100vh - 100px)}
.glyph>svg{width:100%;max-height:72vh}
.state{display:flex;align-items:baseline;gap:18px;padding:14px 18px;border:1px solid var(--rule);border-radius:10px;margin-bottom:16px}
.state .word{font-size:26px;letter-spacing:.18em;text-transform:uppercase;font-weight:700}
.state .count{color:var(--dim)}
.rows{display:flex;flex-direction:column;gap:10px}
.row{display:grid;grid-template-columns:1fr auto;gap:4px 14px;padding:12px 16px;border:1px solid var(--rule);border-radius:10px;background:var(--panel);transition:border-color .4s}
.fn{font-weight:700}
.fault{text-transform:uppercase;letter-spacing:.12em;font-size:13px;text-align:right}
.meta{grid-column:1/-1;color:var(--dim);font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar{grid-column:1/-1;height:4px;border-radius:2px;background:var(--rule);overflow:hidden}
.bar i{display:block;height:100%;width:0;transition:width .6s,background .6s}
.issues{margin-top:16px;color:var(--dim);font-size:12.5px;line-height:1.6;white-space:pre-wrap}
.note{color:var(--dim);font-size:13px;margin-top:10px}
@media (max-width:760px){main{grid-template-columns:1fr;padding:16px}header{padding:14px 16px;flex-wrap:wrap}.lock{margin-left:0}}
</style></head><body>
<header><div class="brand">CARTOUCHE</div><div class="live"><span class="dot" id="dot"></span><span id="live">watching</span></div><div class="lock" id="lock"></div></header>
<main>
  <section class="glyph" id="glyph" aria-label="the cartouche as it stands"></section>
  <section>
    <div class="state" id="state"><span class="word">—</span></div>
    <div class="rows" id="rows"></div>
    <div class="issues" id="issues"></div>
    <div class="note" id="note"></div>
  </section>
</main>
<script>
const COLOR={sealed:'var(--green)',missing:'var(--faint)',template:'var(--red)',locked:'var(--red)',skew:'var(--rust)','':'var(--faint)'};
const STATE={sealed:['sealed','var(--green)'],open:['writing','var(--gold)'],waiting:['waiting','var(--dim)'],locked:['locked','var(--red)'],SYNTAX:['syntax','var(--red)'],unreleased:['not signed off','var(--red)']};
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let lastSvg='';
async function tick(){
  let s=null;
  try{s=await (await fetch('state.json',{cache:'no-store'})).json()}catch(e){}
  const dot=document.getElementById('dot');
  if(!s){dot.className='dot off';document.getElementById('live').textContent='page lost the watch';setTimeout(tick,1000);return}
  const running=s.running!==false;
  dot.className=running?'dot':'dot off';
  document.getElementById('live').textContent=running?'watching · stays on the whole build':'stopped';
  if(s.cartouche_sha256)document.getElementById('lock').textContent='lock '+s.cartouche_sha256.slice(0,16)+'…';
  if(s.svg&&s.svg!==lastSvg){document.getElementById('glyph').innerHTML=s.svg;lastSvg=s.svg}
  const [w,c]=STATE[s.state]||[s.state||'—','var(--dim)'];
  const total=s.signs_total!=null?s.signs_total:(s.signs||[]).length;
  document.getElementById('state').innerHTML=`<span class="word" style="color:${c}">${esc(w)}</span><span class="count">${s.signs_sealed||0} of ${total} signs sealed</span>`;
  document.getElementById('state').style.borderColor=s.state==='sealed'?'var(--green)':'var(--rule)';
  document.getElementById('rows').innerHTML=(s.signs||[]).map(r=>{const col=COLOR[r.fault]||'var(--ochre)';const pct=Math.round((r.fidelity||0)*100);
    return `<div class="row" style="border-color:${r.fault==='sealed'?'rgba(16,185,129,.45)':'var(--rule)'}"><span class="fn">${esc(r.function)}</span><span class="fault" style="color:${col}">${esc(r.fault||'not yet')}</span><span class="meta">${esc(r.sign)} · “${esc(r.phrase)}”${r.lines?` · lines ${r.lines[0]}-${r.lines[1]}`:''}</span><span class="bar"><i style="width:${pct}%;background:${col}"></i></span></div>`}).join('');
  document.getElementById('issues').textContent=(s.issues||[]).join('\n');
  document.getElementById('note').textContent=s.note||s.view_error||'';
  setTimeout(tick,500);
}
tick();
</script></body></html>
"""
