/* Embed: <script src="https://YOUR-SERVER/widget.js" data-api="https://YOUR-SERVER"></script> */
(() => {
  const s = document.currentScript;
  const API = (s?.dataset.api || new URL(s.src).origin).replace(/\/$/, "");
  const session = (localStorage.agentSession ||= Math.random().toString(36).slice(2, 12));
  const css = `
  .ag-b{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;border:0;background:#6d5efc;color:#fff;font-size:24px;cursor:pointer;box-shadow:0 6px 24px #0004;z-index:99999}
  .ag-p{position:fixed;right:20px;bottom:88px;width:min(400px,calc(100vw - 40px));height:min(600px,calc(100vh - 110px));background:#0f1117;color:#e6e6ef;border-radius:14px;display:none;flex-direction:column;overflow:hidden;font:14px/1.5 system-ui,sans-serif;box-shadow:0 10px 40px #0007;z-index:99999}
  .ag-p.o{display:flex}.ag-h{display:flex;gap:8px;padding:10px;background:#181b25;align-items:center}
  .ag-h select{flex:1;background:#0f1117;color:inherit;border:1px solid #2a2f3d;border-radius:8px;padding:6px}
  .ag-m{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:10px}
  .ag-m div{padding:8px 11px;border-radius:10px;max-width:92%;white-space:pre-wrap;word-break:break-word}
  .ag-u{align-self:flex-end;background:#6d5efc}.ag-a{background:#1d2130}.ag-t{font-size:12px;opacity:.6;background:none!important;padding:0 4px!important}
  .ag-a pre{background:#0a0c12;padding:8px;border-radius:8px;overflow:auto;margin:6px 0}
  .ag-f{display:flex;gap:6px;padding:10px;border-top:1px solid #2a2f3d}
  .ag-f textarea{flex:1;resize:none;background:#181b25;color:inherit;border:1px solid #2a2f3d;border-radius:8px;padding:8px;font:inherit}
  .ag-f button{background:#6d5efc;color:#fff;border:0;border-radius:8px;padding:0 14px;cursor:pointer}`;
  document.head.append(Object.assign(document.createElement("style"), { textContent: css }));
  const el = (t, c, p) => { const e = document.createElement(t); if (c) e.className = c; p?.append(e); return e; };
  const btn = el("button", "ag-b", document.body); btn.textContent = "💬";
  const panel = el("div", "ag-p", document.body);
  const head = el("div", "ag-h", panel), sel = el("select", "", head);
  const msgs = el("div", "ag-m", panel), form = el("div", "ag-f", panel);
  const input = el("textarea", "", form); input.rows = 2; input.placeholder = "Ask the agent to build something…";
  const send = el("button", "", form); send.textContent = "Send";
  const hist = {};
  btn.onclick = () => panel.classList.toggle("o");
  fetch(API + "/api/agents").then((r) => r.json()).then((a) => a.forEach((x) => { const o = el("option", "", sel); o.value = x.id; o.textContent = `${x.name} - ${x.role}`; }));
  const add = (cls, text) => { const d = el("div", cls, msgs); d.textContent = text; msgs.scrollTop = msgs.scrollHeight; return d; };
  const render = (d, text) => { // minimal safe code-block rendering
    d.textContent = "";
    text.split(/```/).forEach((part, i) => {
      if (i % 2) { const pre = el("pre", "", d); pre.textContent = part.replace(/^\w*\n/, ""); } else d.append(document.createTextNode(part));
    });
  };
  async function go() {
    const text = input.value.trim(); if (!text) return;
    input.value = ""; const id = sel.value; (hist[id] ||= []).push({ role: "user", content: text });
    add("ag-u", text); const wait = add("ag-a", "Working…"); send.disabled = true;
    try {
      const r = await fetch(API + "/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ agent: id, messages: hist[id], session }) });
      const j = await r.json(); if (!r.ok) throw new Error(j.error);
      wait.remove();
      j.trace.forEach((t) => add("ag-t", `⚙ ${t.tool}(${Object.values(t.args).join(", ").slice(0, 60)})`));
      render(add("ag-a", ""), j.reply); hist[id].push({ role: "assistant", content: j.reply });
    } catch (e) { wait.textContent = "Error: " + e.message; }
    send.disabled = false;
  }
  send.onclick = go;
  input.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(); } };
})();
