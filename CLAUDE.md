# LeadFlow: notes for Claude Code

LangGraph workflow for small-business enquiries: ingest → guard → classify → (confident spam → archive) → extract → score → retrieve (RAG) → draft_reply → check_reply (retry loop) → human_review [HITL] → log_to_sheet ‖ notify_team ‖ send_reply → finalize. Portfolio project by Niket Korgaonkar. He must be able to explain every line in interviews, so keep the code simple and explain your changes.

Live: https://leadflow-ai-two-sooty.vercel.app (Vercel project `leadflow-ai`). Vercel auto-deploys on push to `main`. There is no vercel.json; Vercel detects the FastAPI `app` in `app.py`.

## Layout
- `app.py`: demo endpoints (`/api/run`, `/api/resume`, `/api/followup[/send]`, `/api/extract-text`, `/api/meta`, `/api/health`, `/api/eval`) and real-intake endpoints (`/api/intake` with `X-Intake-Key`; `/api/leads` and `/api/business` with `X-Admin-Token`; `/api/whatsapp` verify + HMAC-signed POST). `_require()` returns 403 while the secret env var is unset.
- `leadflow/graph.py`: all nodes, routers, `build_graph()`, `start()` and `resume()`. The module docstring has the flow.
- `leadflow/rules.py`: no-LLM classify/extract/draft plus `score` and `check_reply`, which are **always** rules.
- `leadflow/profiles.py`: 3 fictional businesses (`ca`, `dental`, `coaching`), 16 samples, and the `Profile` pydantic schema for custom businesses (settings page / `resolve_profile`). The state carries the full `profile` dict.
- `leadflow/retriever.py` + `leadflow/docs/<id>/*.md`: BM25 RAG. Documents reach the `retrieve` node through `config["configurable"]["docs"]`, NOT the state (keeps the token small). Only the top `sources` go into state.
- `leadflow/storage.py`: optional Supabase via PostgREST (`scripts/supabase_schema.sql`). `leadflow/followup.py`: follow-up drafts.
- `evals/` + `scripts/eval.py`: 50 labelled enquiries + 16 reply-check cases → `evals/report_*.json` (shown in the Evaluation tab). `test_eval_rules_mode_does_not_regress` enforces the thresholds. Add a case for every bug you fix; never special-case an eval example.
- `evals/holdout.jsonl`: 12 enquiries written after the fixes, reported separately in the eval report (`holdout`). Never tune rules on it.
- **LangSmith:** opt-in via `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY`; run names/tags from `llm.run_config()`. Tests set `LANGSMITH_TRACING=false`.
- `leadflow/integrations.py`: Sheets (Apps Script webhook), Telegram, Resend. Each returns `mode`: live / simulated / manual (manual = no email address, e.g. WhatsApp).
- `leadflow/llm.py`, `leadflow/state_token.py`: same pattern as JobPilot.

## Rules / gotchas
- Every LLM node: `llm = get_llm(); if llm: try ... except: llm_failed(...)`, then the rules path. Tag trace entries with `mode` (llm / rules / human / tool / simulated / manual); the UI colours them.
- `check_reply` allows only numbers found in `kb_text(profile)`, the retrieved sources or the enquiry, and only offer phrases (`OFFER_PHRASES`: "free X", "N% off", "discount…") that appear in the facts. `[n]` citations are stripped before the number check. If you add a fact to a reply template, add it to the profile.
- `guard` is always rules (`rules.detect_injection`); customer text is wrapped in `<customer_message>` in every prompt. `needs_human` (reducer) collects reasons; spam below `LOW_CONFIDENCE` is not auto-archived.
- `actions`, `trace` and `needs_human` use an `operator.add` reducer because the three action nodes run in the same superstep. Nodes return **only new** trace entries (`_t(...)`), never the full list.
- Resume re-seeds with `update_state(cfg, state, as_node="check_reply")`; `route_after_check` must send it to `human_review` (it does, because the check passed or drafts == MAX_DRAFTS). A `revise` resets `drafts` to 0.
- Tests set `GROQ_API_KEY=""` and blank all integration keys **before** importing. LLM paths use `StubLLM`. Never hit the network in tests.
- Demo leads live in the browser (`localStorage` key `leadflow:inbox:<biz>`; the custom business is `leadflow:custom`, docs `leadflow:docs`). Live-inbox leads come from Supabase. When switching business, set `BIZ` then `load()`; never `save()` before loading (that wrote the old inbox under the new key once).

## Run
```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app:app --reload
```
