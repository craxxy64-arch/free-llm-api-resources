# Agent notes

- This is not a web app: the product is `README.md` (a list of free LLM APIs). `src/pull_available_models.py` regenerates it from `src/README_template.md` (`{{MODEL_LIST}}` placeholder) by calling provider APIs.
- Preview (port 3000): the `preview` service in `docker-compose.base44.yml` renders `README.md` live from the bind mount on each request (renderer is an inline compose `config`, not repo code). Refresh the page to see edits.
- Regenerate the README: `docker compose -f docker-compose.base44.yml run --rm generator` (profile `generate`). It must run from `src/` (relative paths to the mp3 and `../README.md`) and needs Python 3.12+ (nested same-quote f-strings). Requires GROQ_API_KEY, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_KEY, GCP_PROJECT_ID, and GCP_SERVICE_ACCOUNT_JSON (written to /tmp and used as GOOGLE_APPLICATION_CREDENTIALS). It overwrites `README.md`, and sections outside the template's model list are hardcoded in the script.
- Verify: `curl -s localhost:3000/ | grep markdown-body`.
- No tests.
