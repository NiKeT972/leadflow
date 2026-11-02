# LeadFlow: notes for Claude Code

LangGraph workflow for small-business enquiries: ingest → classify → (spam → archive) → extract → score → draft_reply → check_reply (retry loop) → human_review [HITL] → log_to_sheet ‖ notify_team ‖ send_reply → finalize. Portfolio project by Niket Korgaonkar. He must be able to explain every line in interviews, so keep the code simple and explain your changes.

Live: https://leadflow-ai-two-sooty.vercel.app (Vercel project `leadflow-ai`). Vercel auto-deploys on push to `main`. There is no vercel.json; Vercel detects the FastAPI `app` in `app.py`.

## Layout
- `app.py`: `POST /api/run`, `POST /api/resume` (signed token only, never raw state), `GET /api/meta`, `GET /api/health`, and `/` serves `public/index.html`.
- `leadflow/graph.py`: all nodes, routers, `build_graph()`, `start()` and `resume()`. The module docstring has the flow.
- `leadflow/rules.py`: no-LLM classify/extract/draft plus `score` and `check_reply`, which are **always** rules.
- `leadflow/profiles.py`: 3 fictional businesses (`ca`, `dental`, `coaching`) with services, prices, FAQs and 16 sample enquiries. `kb_text()` is the only source of facts a reply may quote.
- `leadflow/integrations.py`: Sheets (Apps Script webhook), Telegram, Resend. Each returns `mode`: live / simulated / manual (manual = no email address, e.g. WhatsApp).
- `leadflow/llm.py`, `leadflow/state_token.py`: same pattern as JobPilot.

## Rules / gotchas
- Every LLM node: `llm = get_llm(); if llm: try ... except: llm_failed(...)`, then the rules path. Tag trace entries with `mode` (llm / rules / human / tool / simulated / manual); the UI colours them.
- `check_reply` allows only numbers found in `kb_text(profile)` or the enquiry. If you add a fact to a reply template, add it to the profile.
- `actions` and `trace` use an `operator.add` reducer because the three action nodes run in the same superstep. Nodes return **only new** trace entries (`_t(...)`), never the full list.
- Resume re-seeds with `update_state(cfg, state, as_node="check_reply")`; `route_after_check` must send it to `human_review` (it does, because the check passed or drafts == MAX_DRAFTS). A `revise` resets `drafts` to 0.
- Tests set `GROQ_API_KEY=""` and blank all integration keys **before** importing. LLM paths use `StubLLM`. Never hit the network in tests.
- Leads are stored in the browser's localStorage per business (demo), not server-side.

## Run
```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app:app --reload
```
