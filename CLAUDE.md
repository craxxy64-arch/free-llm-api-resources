# CLAUDE.md

A curated list of free / trial LLM API providers. `README.md` is **generated** — never edit it directly.

## How it works

- `src/README_template.md` — hand-written content; `{{MODEL_LIST}}` is replaced with the generated table. Trial-credit providers are edited here.
- `src/pull_available_models.py` — fetches models + rate limits from Groq, OpenRouter, Cloudflare, OVH, Hyperbolic, Gemini (GCP quotas), builds an HTML table, writes `../README.md`.
- `MODEL_TO_NAME_MAPPING` maps API ids → display names. Unknown ids print under "Missing models:" — add them to the mapping (keys lowercase).
- Static providers (Cohere, HF, glhf, Lambda…) are hard-coded HTML in `main()`.

## Run

```sh
cd src                      # script uses relative paths
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python pull_available_models.py
```

Needs `src/.env` (gitignored): `GROQ_API_KEY`, `CLOUDFLARE_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `GCP_PROJECT_ID` (+ gcloud ADC for Gemini quotas).

## Rules

- Change content in the template or script, then regenerate `README.md`; commit both.
- Only legitimate providers — no reverse-engineered chatbot wrappers.
- Keep HTML `rowspan` counts in sync with row counts when editing static tables.
- Python 3.12+ (nested f-string quotes).
- Never commit `.env` or keys.
