import http from "node:http";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { specsFor, runTool } from "./tools.js";

const DIR = path.dirname(fileURLToPath(import.meta.url));

// tiny .env loader
try {
  for (const line of fs.readFileSync(path.join(DIR, ".env"), "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m && !line.trim().startsWith("#") && !(m[1] in process.env)) process.env[m[1]] = m[2];
  }
} catch {}

const env = process.env;
const AGENTS = JSON.parse(fs.readFileSync(path.join(DIR, "agents.json"), "utf8"));
const BASE = (env.AGENT_BASE_URL || "https://api.groq.com/openai/v1").replace(/\/$/, "");
const SHELL = env.ENABLE_SHELL === "true";
const ORIGINS = (env.ALLOWED_ORIGINS || "*").split(",").map((s) => s.trim());
const LIMIT = +env.RATE_LIMIT_PER_MIN || 20;
const PUBLIC = path.join(DIR, "public");
const hits = new Map();

const send = (res, code, body, headers = {}) => {
  res.writeHead(code, { "Content-Type": "application/json", ...headers });
  res.end(typeof body === "string" ? body : JSON.stringify(body));
};

function cors(req) {
  const o = req.headers.origin;
  const ok = ORIGINS.includes("*") || (o && ORIGINS.includes(o));
  return ok
    ? { "Access-Control-Allow-Origin": ORIGINS.includes("*") ? "*" : o, "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Methods": "GET,POST,OPTIONS", Vary: "Origin" }
    : {};
}

function limited(ip) {
  const now = Date.now();
  const arr = (hits.get(ip) || []).filter((t) => now - t < 60000);
  arr.push(now);
  hits.set(ip, arr);
  return arr.length > LIMIT;
}

async function llm(agent, messages, tools) {
  const model = env[agent.id.toUpperCase() + "_MODEL"] || agent.model;
  const body = { model, messages, temperature: agent.temperature };
  if (tools.length) body.tools = tools;
  for (let attempt = 0; attempt < 3; attempt++) {
    const r = await fetch(`${BASE}/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.AGENT_API_KEY}` },
      body: JSON.stringify(body),
    });
    if (r.status === 429 || r.status >= 500) { await new Promise((s) => setTimeout(s, 1000 * 2 ** attempt)); continue; }
    const j = await r.json();
    if (!r.ok) throw new Error(j.error?.message || `LLM error ${r.status}`);
    return j.choices[0].message;
  }
  throw new Error("LLM unavailable, try again");
}

async function runAgent(agent, history, root) {
  const tools = specsFor(agent.tools, SHELL);
  const messages = [{ role: "system", content: agent.system }, ...history];
  const trace = [];
  for (let step = 0; step < agent.maxSteps; step++) {
    const msg = await llm(agent, messages, tools);
    messages.push(msg);
    if (!msg.tool_calls?.length) return { reply: msg.content || "", trace };
    for (const call of msg.tool_calls) {
      let args = {};
      try { args = JSON.parse(call.function.arguments || "{}"); } catch {}
      const result = await runTool(call.function.name, args, root, SHELL);
      trace.push({ tool: call.function.name, args, result: result.slice(0, 500) });
      messages.push({ role: "tool", tool_call_id: call.id, content: result });
    }
  }
  return { reply: "Reached the step limit. Ask me to continue.", trace };
}

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };

http.createServer(async (req, res) => {
  const h = cors(req);
  const url = new URL(req.url, "http://x");
  if (req.method === "OPTIONS") return send(res, 204, "", h);

  if (url.pathname === "/api/agents") {
    return send(res, 200, Object.entries(AGENTS).map(([id, a]) => ({ id, name: a.name, role: a.role })), h);
  }

  if (url.pathname === "/api/chat" && req.method === "POST") {
    const ip = req.socket.remoteAddress;
    if (limited(ip)) return send(res, 429, { error: "Too many requests" }, h);
    if (!env.AGENT_API_KEY) return send(res, 500, { error: "Server missing AGENT_API_KEY" }, h);
    let raw = "";
    for await (const c of req) { raw += c; if (raw.length > 200000) return send(res, 413, { error: "Too large" }, h); }
    try {
      const { agent: id = "coder", messages = [], session = "default" } = JSON.parse(raw);
      const agent = AGENTS[id];
      if (!agent) return send(res, 400, { error: "Unknown agent" }, h);
      const history = messages.slice(-30).filter((m) => ["user", "assistant"].includes(m.role) && typeof m.content === "string");
      const root = path.resolve(DIR, "workspace", String(session).replace(/[^\w-]/g, "").slice(0, 64) || "default");
      await fsp.mkdir(root, { recursive: true });
      return send(res, 200, await runAgent({ ...agent, id }, history, root), h);
    } catch (e) {
      return send(res, 500, { error: e.message }, h);
    }
  }

  // static files
  const file = path.resolve(PUBLIC, "." + (url.pathname === "/" ? "/index.html" : url.pathname));
  if (file.startsWith(PUBLIC + path.sep) && fs.existsSync(file) && fs.statSync(file).isFile()) {
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream", ...h });
    return fs.createReadStream(file).pipe(res);
  }
  send(res, 404, { error: "Not found" }, h);
}).listen(+env.PORT || 8787, () => console.log(`Agents ready on :${env.PORT || 8787}`));
