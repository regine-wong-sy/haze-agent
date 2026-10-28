# Decision notes

Short notes on why changes were made, newest first.

## data.gov.sg fallback for `get_psi`
**Change:** `get_psi` tries Haze-API first and falls back to data.gov.sg if it fails (timeout, connection error or non-200).
**Why:** Haze-API sleeps on Render's free tier and sometimes failed, so the agent answered "I don't have the PSI". The fallback keeps the agent useful when one source is down.
**Alternatives:** retrying Haze-API (doesn't help if it's down); caching the last PSI (could serve stale health advice).
**Trade-offs:** data.gov.sg only has five regions, so a small `AREA_TO_REGION` map covers common areas and unknown areas return an error. PSI levels are computed from NEA's bands in `psi_level`, so they must match Haze-API's labels.
**Tests:** `test_tools.py` (run `python -m unittest test_tools`).
