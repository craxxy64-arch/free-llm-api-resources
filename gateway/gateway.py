#!/usr/bin/env python3
"""Personal LLM gateway: your own API key -> many free providers, with fallback.

Zero dependencies (stdlib only). OpenAI-compatible: /v1/chat/completions, /v1/models.

  python gateway.py keys create --name me --rpm 60
  export GROQ_API_KEY=... OPENROUTER_API_KEY=... 
  python gateway.py serve
"""
import argparse, hashlib, hmac, json, os, secrets, sys, threading, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.environ.get("GW_KEYS_FILE", os.path.join(HERE, "keys.json"))
CONFIG_FILE = os.environ.get("GW_CONFIG", os.path.join(HERE, "providers.json"))
LOCK = threading.Lock()


# ---------- own keys ----------
def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def _save_keys(data):
    tmp = KEYS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, KEYS_FILE)


def _hash(k):
    return hashlib.sha256(k.encode()).hexdigest()


def create_key(name, rpm, daily, models):
    raw = "sk-gw-" + secrets.token_urlsafe(32)
    with LOCK:
        d = _load(KEYS_FILE, {})
        d[_hash(raw)] = {"name": name, "rpm": rpm, "daily": daily, "models": models,
                         "created": int(time.time()), "requests": 0, "tokens": 0, "revoked": False}
        _save_keys(d)
    return raw


class Limiter:
    """Sliding-window per-minute + per-day counters, in memory."""
    def __init__(self):
        self.hits = {}

    def allow(self, kid, rpm, daily):
        now = time.time()
        with LOCK:
            h = [t for t in self.hits.get(kid, []) if now - t < 86400]
            if daily and len(h) >= daily:
                self.hits[kid] = h
                return False, "daily limit reached"
            if rpm and sum(1 for t in h if now - t < 60) >= rpm:
                self.hits[kid] = h
                return False, "rate limit exceeded"
            h.append(now)
            self.hits[kid] = h
        return True, ""


LIMITER = Limiter()


def auth(header):
    if not header or not header.lower().startswith("bearer "):
        return None, None
    raw = header[7:].strip()
    h = _hash(raw)
    d = _load(KEYS_FILE, {})
    for kid, info in d.items():
        if hmac.compare_digest(kid, h) and not info.get("revoked"):
            return kid, info
    return None, None


def record_usage(kid, tokens):
    with LOCK:
        d = _load(KEYS_FILE, {})
        if kid in d:
            d[kid]["requests"] += 1
            d[kid]["tokens"] += tokens
            d[kid]["last_used"] = int(time.time())
            _save_keys(d)


# ---------- providers ----------
DEFAULT_PROVIDERS = {
    "groq": {"base": "https://api.groq.com/openai/v1", "env": "GROQ_API_KEY",
             "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]},
    "openrouter": {"base": "https://openrouter.ai/api/v1", "env": "OPENROUTER_API_KEY",
                   "models": ["meta-llama/llama-3.3-70b-instruct:free", "deepseek/deepseek-r1:free"]},
    "cerebras": {"base": "https://api.cerebras.ai/v1", "env": "CEREBRAS_API_KEY",
                 "models": ["llama-3.3-70b", "llama3.1-8b"]},
    "gemini": {"base": "https://generativelanguage.googleapis.com/v1beta/openai", "env": "GEMINI_API_KEY",
               "models": ["gemini-2.0-flash", "gemini-1.5-flash"]},
    "mistral": {"base": "https://api.mistral.ai/v1", "env": "MISTRAL_API_KEY",
                "models": ["mistral-small-latest"]},
}


class Providers:
    def __init__(self):
        cfg = _load(CONFIG_FILE, None) or {"providers": DEFAULT_PROVIDERS, "chains": {}}
        self.providers = cfg.get("providers", DEFAULT_PROVIDERS)
        self.chains = cfg.get("chains", {})
        self.cooldown = {}  # provider -> unix time until usable
        self.stats = {}

    def key(self, p):
        return os.environ.get(self.providers[p].get("env", ""), "")

    def active(self):
        return [p for p in self.providers if self.key(p)]

    def route(self, model):
        """Return ordered list of (provider, upstream_model)."""
        if model in self.chains:                       # named chain: "fast", "smart"...
            out = []
            for step in self.chains[model]:
                p, _, m = step.partition("/")
                out.append((p, m))
            return out
        if "/" in model and model.split("/")[0] in self.providers:   # "groq/llama-3.3-70b-versatile"
            p, _, m = model.partition("/")
            return [(p, m)]
        # "auto" or unknown: every model of every active provider
        return [(p, m) for p in self.active() for m in self.providers[p]["models"]]

    def usable(self, p):
        return self.key(p) and self.cooldown.get(p, 0) <= time.time()

    def fail(self, p, secs):
        self.cooldown[p] = time.time() + secs
        s = self.stats.setdefault(p, {"ok": 0, "err": 0}); s["err"] += 1

    def ok(self, p):
        s = self.stats.setdefault(p, {"ok": 0, "err": 0}); s["ok"] += 1


PROV = None


def upstream(p, model, body, stream):
    cfg = PROV.providers[p]
    payload = dict(body); payload["model"] = model
    req = urllib.request.Request(cfg["base"].rstrip("/") + "/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + PROV.key(p),
                                          "Content-Type": "application/json",
                                          "User-Agent": "personal-gateway/1"})
    return urllib.request.urlopen(req, timeout=120)


# ---------- server ----------
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _err(self, code, msg):
        self._json(code, {"error": {"message": msg, "type": "gateway_error", "code": code}})

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"ok": True, "providers": PROV.active()})
        kid, info = auth(self.headers.get("Authorization"))
        if not kid:
            return self._err(401, "invalid api key")
        if self.path == "/v1/models":
            ids = ["auto"] + list(PROV.chains) + [f"{p}/{m}" for p in PROV.active() for m in PROV.providers[p]["models"]]
            return self._json(200, {"object": "list", "data": [{"id": i, "object": "model", "owned_by": "gateway"} for i in ids]})
        if self.path == "/v1/usage":
            return self._json(200, {"name": info["name"], "requests": info["requests"], "tokens": info["tokens"],
                                    "providers": PROV.stats})
        self._err(404, "not found")

    def do_POST(self):
        kid, info = auth(self.headers.get("Authorization"))
        if not kid:
            return self._err(401, "invalid api key")
        if self.path != "/v1/chat/completions":
            return self._err(404, "not found")
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n))
        except Exception:
            return self._err(400, "invalid json")
        model = body.get("model", "auto")
        allowed = info.get("models")
        if allowed and model not in allowed:
            return self._err(403, "model not allowed for this key")
        okk, why = LIMITER.allow(kid, info.get("rpm"), info.get("daily"))
        if not okk:
            return self._err(429, why)
        stream = bool(body.get("stream"))
        route = PROV.route(model)
        if not route:
            return self._err(503, "no providers configured (set provider env keys)")
        last = "no usable provider"
        for p, m in route:
            if not PROV.usable(p):
                continue
            try:
                r = upstream(p, m, body, stream)
            except urllib.error.HTTPError as e:
                last = f"{p}: HTTP {e.code}"
                if e.code == 429:
                    PROV.fail(p, int(e.headers.get("Retry-After", 60) or 60))
                elif e.code in (401, 403):
                    PROV.fail(p, 3600)
                elif e.code >= 500:
                    PROV.fail(p, 30)
                continue                       # 4xx model errors: try next
            except Exception as e:
                last = f"{p}: {e}"
                PROV.fail(p, 30)
                continue
            PROV.ok(p)
            return self._relay(r, kid, stream, p, m)
        self._err(502, "all providers failed; last: " + last)

    def _relay(self, r, kid, stream, p, m):
        tokens = 0
        self.send_response(200)
        self.send_header("X-Gateway-Provider", p)
        self.send_header("X-Gateway-Model", m)
        if stream:
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                for line in r:
                    if b'"total_tokens"' in line:
                        try:
                            tokens = json.loads(line.split(b"data:", 1)[1])["usage"]["total_tokens"]
                        except Exception:
                            pass
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(line), line))
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            data = r.read()
            try:
                tokens = json.loads(data).get("usage", {}).get("total_tokens", 0)
            except Exception:
                pass
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        record_usage(kid, tokens)


def main():
    global PROV
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keys").add_subparsers(dest="kcmd", required=True)
    c = k.add_parser("create"); c.add_argument("--name", required=True)
    c.add_argument("--rpm", type=int, default=60); c.add_argument("--daily", type=int, default=0)
    c.add_argument("--models", nargs="*", default=None)
    k.add_parser("list")
    rv = k.add_parser("revoke"); rv.add_argument("prefix", help="first chars of key id from `keys list`")
    s = sub.add_parser("serve"); s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8787)
    a = ap.parse_args()

    if a.cmd == "keys":
        if a.kcmd == "create":
            print("Your key (shown once, store it safely):\n  " + create_key(a.name, a.rpm, a.daily, a.models))
        elif a.kcmd == "list":
            for kid, i in _load(KEYS_FILE, {}).items():
                print(f"{kid[:10]}  {i['name']:<15} rpm={i['rpm']} req={i['requests']} tok={i['tokens']} {'REVOKED' if i['revoked'] else ''}")
        else:
            with LOCK:
                d = _load(KEYS_FILE, {}); hit = [x for x in d if x.startswith(a.prefix)]
                if len(hit) != 1: sys.exit("prefix must match exactly one key")
                d[hit[0]]["revoked"] = True; _save_keys(d)
            print("revoked")
        return
    PROV = Providers()
    if not PROV.active():
        print("warning: no provider API keys in env (GROQ_API_KEY, OPENROUTER_API_KEY, ...)", file=sys.stderr)
    print(f"gateway on http://{a.host}:{a.port}  providers: {', '.join(PROV.active()) or 'none'}")
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()


if __name__ == "__main__":
    main()
