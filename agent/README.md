# Agents

Two coding agents for your website. Zero dependencies (Node 18+).

| Agent | Does | Tools |
|---|---|---|
| **Nova** (`coder`) | Explores, writes, edits, tests code | list, read, search, write, edit, run |
| **Atlas** (`architect`) | Read-only code review + design | list, read, search |

## Run
```bash
cp .env.example .env   # add AGENT_API_KEY
node server.js         # http://localhost:8787
```
Works with any OpenAI-compatible API (Groq, OpenRouter, OpenAI...) - see the provider list in the repo root README. Change `AGENT_BASE_URL` and model names in `agents.json` (or `CODER_MODEL` / `ARCHITECT_MODEL`).

## Add to your website
```html
<script src="https://YOUR-SERVER/widget.js" data-api="https://YOUR-SERVER"></script>
```
Set `ALLOWED_ORIGINS=https://yoursite.com` in `.env`.

## Safety
- API key stays on the server, never in the browser.
- Each visitor gets an isolated `workspace/<session>` folder; paths can't escape it.
- `run_command` is **off** by default. Enable (`ENABLE_SHELL=true`) only inside a container.
- Per-IP rate limit (`RATE_LIMIT_PER_MIN`).

## Customize
Edit `agents.json`: system prompts, model, tools, `maxSteps`. Add a third agent by adding a key.
