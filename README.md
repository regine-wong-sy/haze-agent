# Haze Agent

An AI agent that answers Singapore haze safety questions using **live PSI data** and **official NEA/MOM guidelines**, plus a **conversation review dashboard** for checking and flagging the agent's answers.

**Live:** [haze-agent.onrender.com](https://haze-agent.onrender.com) · also embedded as the Ask box on [Haze Monitor](https://haze-api.onrender.com)

> Free Render instances sleep when idle, so the first request can take 30–60s.

## What it does

Ask something like *"Can construction workers in Jurong work outside right now?"* and the agent:

1. Calls `get_psi` to fetch the live 24-hr PSI for that area (via my [Haze-API](https://github.com/regine-wong-sy/Haze-API))
2. Calls `search_advisories` to find the NEA/MOM guidance for that PSI band
3. Answers using only facts from those tool results, citing NEA or MOM

Every conversation is logged to Postgres, and a password-protected dashboard lets me review answers and **flag** bad ones (wrong advice, made-up facts, formatting problems) to fix in the prompt and add to the eval set.

## Architecture

```
Haze Monitor page ──▶ Haze Agent (Python/Flask) ──▶ Haze-API (live PSI)
                            │       └──▶ ChromaDB (NEA/MOM advisories)
                            ▼
                    Neon Postgres  (conversations table)
                            ▲
Dashboard (React + TS) ◀── Node + TS API (Express, password protected)
```

Three services on Render: Haze-API, Haze Agent, and the dashboard (the Node API serves the built React app, so it's one URL with no CORS).

## Stack

| Part  | Tech |
| Agent | Python, Ollama (cloud `gpt-oss:20b`, local `qwen3:4b`), tool calling |
| Retrieval | ChromaDB, 14 NEA/MOM advisory chunks, each tagged with a PSI band and a group, filtered in code |
| Agent server | Flask, gunicorn, MCP server (`get_psi`, `search_advisories`, `ask_haze_agent`) |
| Database | PostgreSQL (Neon), node-postgres |
| API | Node.js, Express, TypeScript |
| Dashboard | React, TypeScript, Vite |
| Hosting | Render |

## Files

| File       | Purpose |
| `agent.py` | Agent loop: model ⇄ tools until a final answer, returns answer + area, PSI, tools used, route |
| `tools.py` | `get_psi` and `search_advisories` (`USE_EMBEDDINGS` switches semantic vs filter-only search) |
| `ingest.py` | Loads `docs/advisories.txt` into ChromaDB with band, source and group tags |
| `router.py` | Chooses cloud or local model |
| `web.py` | Flask `/ask` endpoint, logs each conversation (a DB failure never blocks the answer) |
| `db.py` | Saves conversations to Postgres with parameterised queries |
| `server.py` | MCP server exposing the tools |
| `eval.py` | 18 test questions run several times each; reports a pass rate and exits non-zero below the threshold |
| `export_flagged.py` | Prints eval test-case skeletons from conversations flagged in the dashboard |
| `test_tools.py` | Unit tests for PSI fallback and group filtering |
| `api/` | Node + TS API: `GET /conversations`, `POST /conversations/:id/flag` (`src/app.ts` is the app, `src/app.test.ts` its tests) |
| `dashboard/` | React + TS review dashboard: list, detail, flag/unflag, stats |

## Evaluation and CI

`eval.py` asks the agent 18 fixed questions, each `TRIALS` times (default 3), because the model's answers vary between runs. Each case checks words that must appear (`must_include`, `any_of`) and words that must not (`must_not_include`, which catches advice from the wrong group leaking in). It prints a pass rate per question and overall, and exits with code 1 if the overall rate is below `MIN_PASS_RATE` (default 0.8).

```bash
TRIALS=3 USE_EMBEDDINGS=0 python eval.py
```

To grow the set: flag bad answers in the dashboard, run `python export_flagged.py`, and paste the skeletons into `TESTS`.

GitHub Actions (`.github/workflows/ci.yml`) runs on every push and pull request:

1. Python unit tests and API tests (no network, no model)
2. The eval against the real model (needs the `OLLAMA_API_KEY` repo secret)
3. On `main` only, if those pass, deploy to Render through deploy hooks (`RENDER_AGENT_DEPLOY_HOOK`, `RENDER_DASHBOARD_DEPLOY_HOOK` secrets). Turn off Render's own auto-deploy, or it will deploy before the eval has run.

## Design decisions

- **Postgres for logs, Chroma for advisories.** Chroma finds text by meaning; the conversation log needs sorting, filtering, counting and updating on exact fields, which is what Postgres is built for.
- **Answers only from tool results.** The prompt forbids adding thresholds or rules from the model's own knowledge, and the agent says so when the guidelines don't cover a question.
- **Logging can't break answers.** Saving is wrapped in `try/except`, so a database outage only loses the log entry, not the user's answer.
- **Dashboard behind a password.** Logged questions can contain personal details, so only the owner can view them.

## Run locally

```bash
# Agent (Python)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python ingest.py
python web.py                # http://localhost:8081

# API + dashboard (Node)
cd dashboard && npm install && npm run build
cd ../api && npm install && npm run dev   # http://localhost:3001
```

`.env` (not committed) needs `OLLAMA_API_KEY`, `DATABASE_URL` and `DASHBOARD_PASSWORD`.