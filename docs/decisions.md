# Decision notes

Short notes on why changes were made, newest first.

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
