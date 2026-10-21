"""MCP Apps UI resource: a small Shabbos-times card for screen devices.

Per the MCP Apps extension (io.modelcontextprotocol/ui) the host renders this
HTML in a sandboxed iframe and sends the tool result by postMessage
(JSON-RPC `ui/notifications/tool-result`). For local previews the card also
accepts the structured result in the URL fragment: card.html#<url-encoded JSON>.
No network access, no external assets.
"""

SHABBOS_CARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shabbos times</title>
<style>
 :root{--bg:#0f1b2d;--card:#16263f;--gold:#e9c46a;--ink:#f4f1ea;--mute:#a9b4c6}
 *{box-sizing:border-box}body{margin:0;font:16px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
 .card{max-width:560px;margin:0 auto;padding:22px 24px;background:var(--card);border-radius:18px}
 h1{margin:0 0 4px;font-size:22px}.where{color:var(--mute);margin-bottom:16px}
 .row{display:flex;justify-content:space-between;align-items:baseline;padding:12px 0;border-top:1px solid #24375a}
 .label{color:var(--mute)}.time{font-size:28px;font-weight:700;color:var(--gold)}
 .parsha{margin-top:14px;font-size:18px}.attr{margin-top:18px;font-size:12px;color:var(--mute)}
</style></head><body><main class="card" aria-live="polite">
<h1 id="title">Shabbos times</h1><div class="where" id="where">Waiting for data…</div>
<div id="rows"></div><div class="parsha" id="parsha"></div>
<div class="attr" id="attr">Data: Hebcal.com, CC BY 4.0</div></main>
<script>
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function render(r){
  if(!r)return;
  document.getElementById("title").textContent=r.kind==="yom_tov"?"Yom Tov times":"Shabbos times";
  document.getElementById("where").textContent=(r.location&&r.location.title)||"";
  var h="";
  (r.candle_lighting||[]).forEach(function(c){h+='<div class="row"><span class="label">Candle lighting · '+esc(c.day)+'</span><span class="time">'+esc(c.spoken)+'</span></div>'});
  if(r.havdalah)h+='<div class="row"><span class="label">Havdalah · '+esc(r.havdalah.day)+'</span><span class="time">'+esc(r.havdalah.spoken)+'</span></div>';
  document.getElementById("rows").innerHTML=h;
  var p=[];if(r.parsha)p.push(r.parsha);(r.holidays||[]).forEach(function(x){p.push(x)});
  document.getElementById("parsha").textContent=p.join(" · ");
  if(r.attribution)document.getElementById("attr").textContent=r.attribution;
}
window.addEventListener("message",function(e){
  var m=e.data;if(!m||typeof m!=="object")return;
  if(m.id===1&&(m.result||m.error)){try{window.parent.postMessage({jsonrpc:"2.0",method:"ui/notifications/initialized",params:{}},"*")}catch(x){}return}
  if(m.method==="ui/notifications/tool-result"&&m.params){render(m.params.structuredContent||m.params.structured_content)}
});
if(window.parent!==window){try{window.parent.postMessage({jsonrpc:"2.0",id:1,method:"ui/initialize",params:{appInfo:{name:"shabbos-card",version:"0.1.0"},appCapabilities:{availableDisplayModes:["inline"]},protocolVersion:"2025-06-18"}},"*")}catch(e){}}
if(location.hash.length>1){try{render(JSON.parse(decodeURIComponent(location.hash.slice(1))))}catch(e){}}
</script></body></html>
"""
