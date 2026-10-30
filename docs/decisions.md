# Decision notes

Short notes on why changes were made, newest first.

## Streamed answers on `/ask/stream`
**Change:** `agent.run` is a generator that yields `status` (while a tool runs) and `token` events; `ask()` drives it without streaming, so `eval.py` and the MCP server behave as before. `web.py` adds `POST /ask/stream`, which sends one JSON object per line (NDJSON) and ends with a `done` line holding the full answer. `static/index.html` types the tokens as they arrive.
**Why:** the whole run takes 5-30s and the page showed "Thinking..." the entire time. Only the final answer can stream, because the model must finish its tool calls first, so the status lines cover the wait before it.
**Alternatives:** Server-Sent Events (`EventSource` can't POST, so the question would go in the URL); websockets (more than one-way text needs).
**Trade-offs:** `/ask` is unchanged for the Haze Monitor page, so it still waits for the whole answer. The `done` line always replaces what was typed, which covers a model error or running out of steps after tokens were shown. If the model writes text before a tool call, that text is shown too. A `gunicorn` sync worker is still tied up for the whole stream, so check the Render start command has a `--timeout` above 70s.
**Tests:** `test_agent.py` (`StreamTest`, `StreamEndpointTest`).

## PSI cache, circuit breaker and agent time budget
**Change:** `get_psi` now goes cache (10 min) -> Haze-API (skipped for 60s after 2 failures in a row) -> data.gov.sg (one retry) -> cached reading up to 2 h old. `agent.ask` stops after `MAX_SECONDS` (70) as well as `max_steps`, and a tool that crashes becomes an error the model reads. Every run, model call and tool call is logged as one JSON line, and `/metrics` on `web.py` returns counters and timings.
**Why:** Haze-API can take up to 60s to wake on Render, and every question paid that wait again while it was down. The breaker makes that cost once a minute instead of once per question. A bad tool argument from the model (e.g. `psi="high"`) used to end the whole run with an exception.
**Alternatives:** retrying Haze-API (still waits out the timeout each time, so only data.gov.sg gets a retry); a longer cache (PSI is hourly, but the older it gets the less the health advice can be trusted).
**Trade-offs:** an old reading is only used when both sources are down, and it looks identical to a live one (an extra key confused the model before, see below), so the log line `source: stale-cache` and the `psi.stale_served` counter are the only signs. The cache, breaker and metrics live in memory per gunicorn worker and reset on deploy. Logs hold the region and counts, not the question, because the local route exists to keep health details private.
**Tests:** `test_tools.py` (cache, breaker, retry, stale), `test_reliability.py`, `test_agent.py` (step and time limits, crashing tools).

## Advisory chunks tagged by group, filtered in code
**Change:** every chunk in `docs/advisories.txt` has a `group` (healthy, sensitive, chronic, worker, or all). `search_advisories` takes a required `group`, and Chroma is filtered on PSI band and `group IN (group, all)`.
**Why:** the prompt said "don't mix advice between groups", but the model was handed every group's rule for that PSI and sometimes blended them (e.g. "reduce" for someone who should "avoid"). Now the wrong group's advice never reaches the model.
**Alternatives:** keep the prompt rule (unreliable, scored 9-10/10); detect the group in code from keywords (brittle, misses "my nan").
**Trade-offs:** the model must pick the group correctly, and the 201-999 "vulnerable persons" rule is stored twice (sensitive and chronic). A healthy adult at PSI above 200 gets no group-specific rule, so the agent says it isn't covered.
**Tests:** `test_tools.py` (group filtering) and the `must_not_include` cases in `eval.py`.

## Eval runs several trials and gates deploys
**Change:** `eval.py` runs each question `TRIALS` times and fails below `MIN_PASS_RATE`; CI runs it before deploying.
**Why:** one run of 10 hides flaky cases (the healthy-adult jogging question failed in one run and passed in the next, with the same code).
**Trade-offs:** CI calls the real model, so it is slower and can fail on server errors (those are skipped, not counted).

## Express app split from server start
**Change:** `api/src/app.ts` exports `createApp(db)`; `index.ts` only creates the pool and listens.
**Why:** routes and auth can be tested with a fake database. `api/src/app.test.ts` proves the login "fails closed" (no password set means everyone is blocked).

## data.gov.sg fallback for `get_psi`
**Change:** `get_psi` tries Haze-API first and falls back to data.gov.sg if it fails (timeout, connection error or non-200).
**Why:** Haze-API sleeps on Render's free tier and sometimes failed, so the agent answered "I don't have the PSI". The fallback keeps the agent useful when one source is down.
**Alternatives:** retrying Haze-API (doesn't help if it's down); caching the last PSI (could serve stale health advice).
**Trade-offs:** data.gov.sg only has five regions, so a small `AREA_TO_REGION` map covers common areas and unknown areas return an error. PSI levels are computed from NEA's bands in `psi_level`, so they must match Haze-API's labels.
**Tests:** `test_tools.py` (run `python -m unittest test_tools`).
