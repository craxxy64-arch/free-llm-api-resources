# Personal LLM Gateway

One key of yours (`sk-gw-...`) → many free providers. OpenAI-compatible. Zero dependencies.

## Quick start
```bash
cd gateway
python gateway.py keys create --name me --rpm 60      # prints your key once
export GROQ_API_KEY=... OPENROUTER_API_KEY=... GEMINI_API_KEY=... CEREBRAS_API_KEY=...
python gateway.py serve                               # http://127.0.0.1:8787
```
```bash
curl localhost:8787/v1/chat/completions -H "Authorization: Bearer sk-gw-..." \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"hi"}]}'
```
Works with any OpenAI SDK: `base_url="http://localhost:8787/v1"`, `api_key="sk-gw-..."`.

## Features
- Own keys: hashed at rest, per-key rpm/daily limits, model allowlist, revoke, usage tracking (`/v1/usage`)
- Models: `auto` (all providers), `provider/model`, or named chains (`fast`, `smart`) from `providers.json`
- Auto-fallback on 429/5xx/timeouts, with per-provider cooldown (honors Retry-After)
- Streaming (SSE) passthrough
- `keys list` / `keys revoke <prefix>`; `/health`

Copy `providers.example.json` to `providers.json` to customize. Provider keys stay in env vars, never in files.

**Deploying publicly?** Put it behind HTTPS (Caddy/nginx/Cloudflare Tunnel) and bind `--host 0.0.0.0` only then.
