import os
import time
import requests
import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
import obs
from reliability import TTLCache, CircuitBreaker

HAZE_API = "https://haze-api.onrender.com/haze"
DATA_GOV_PSI = "https://api-open.data.gov.sg/v2/real-time/api/psi"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

#keep the embedding model inside the project so Render doesn't throw it away after the build
ONNXMiniLM_L6_V2.DOWNLOAD_PATH = os.path.join(BASE_DIR, "onnx_model")

_rules = None

def get_rules():
    """Open Chroma on first use, inside the worker process.
    Opening it at import time breaks under gunicorn --preload: the client is created
    in the master and then forked, and queries in the worker hang."""
    global _rules
    if _rules is None:
        client = chromadb.PersistentClient(path=os.path.join(BASE_DIR, "chroma_db"))
        _rules = client.get_collection("advisories")
    return _rules

USE_EMBEDDINGS = os.environ.get("USE_EMBEDDINGS", "1") == "1" #set to 0 on Render
print("USE_EMBEDDINGS =", USE_EMBEDDINGS, "| env value:", repr(os.environ.get("USE_EMBEDDINGS")))

#warm up: load the model when the server starts (only if we're using it)
if USE_EMBEDDINGS:
    get_rules().query(query_texts=["warm up"], n_results=1)

def psi_level(psi):
    """NEA's 24-hr PSI bands."""
    if psi <= 50: return "Good"
    if psi <= 100: return "Moderate"
    if psi <= 200: return "Unhealthy"
    if psi <= 300: return "Very Unhealthy"
    return "Hazardous"

#fallback only: Haze-API knows more areas, this covers the common ones
AREA_TO_REGION = {
    "bedok": "east", "tampines": "east", "pasir ris": "east", "changi": "east", "geylang": "east",
    "jurong": "west", "clementi": "west", "bukit batok": "west", "choa chu kang": "west", "tuas": "west",
    "woodlands": "north", "yishun": "north", "sembawang": "north", "ang mo kio": "north", "punggol": "north",
    "orchard": "central", "toa payoh": "central", "bishan": "central", "novena": "central",
    "queenstown": "south", "tanjong pagar": "south", "harbourfront": "south", "marina bay": "south",
}

def get_psi_direct(region):
    """Backup: read the 24-hr PSI straight from data.gov.sg when Haze-API is down."""
    key = region.strip().lower()
    key = AREA_TO_REGION.get(key, key)
    resp = requests.get(DATA_GOV_PSI, timeout=15)
    resp.raise_for_status()
    readings = resp.json()["data"]["items"][0]["readings"]["psi_twenty_four_hourly"]
    if key not in readings:
        return {"error": f"Unknown region '{region}'. Try north, south, east, west or central."}
    psi = readings[key]
    #same keys as Haze-API's reply; an extra "source" key made the model confuse it with NEA/MOM citations
    return {"region": key, "psi": psi, "level": psi_level(psi)}

#the 24-hr PSI only changes about once an hour, so a few minutes old is still correct.
#older readings are only used when both sources are down, and not past PSI_MAX_STALE
PSI_CACHE_TTL = 600
PSI_MAX_STALE = 7200
psi_cache = TTLCache(PSI_CACHE_TTL, PSI_MAX_STALE)
#Haze-API can take 60s to wake up on Render, so after 2 failures skip it for a minute
haze_breaker = CircuitBreaker(failures=2, cooldown=60)
GOV_RETRIES = 2 #data.gov.sg is the last resort, so one retry on a network error
GOV_RETRY_DELAY = 0.5

def reset_psi_state():
    """For tests: forget cached readings and breaker history."""
    psi_cache.clear()
    haze_breaker.success()

def get_psi_haze(region):
    """Ask Haze-API. Returns (reply, error); exactly one of them is None."""
    t0 = time.time()
    try:
        resp = requests.get(HAZE_API, params={"region": region}, timeout=60)
        data = resp.json()
    except Exception as e:
        haze_breaker.failure()
        obs.count("psi.haze_api.error")
        return None, str(e)
    finally:
        obs.observe("psi.haze_api", time.time() - t0)
    if resp.status_code == 200:
        haze_breaker.success()
        return data, None
    #a 4xx means it answered but didn't know the area, which is not an outage
    if resp.status_code >= 500:
        haze_breaker.failure()
        obs.count("psi.haze_api.error")
    else:
        haze_breaker.success()
    return None, data.get("error", f"HTTP {resp.status_code}")

def get_psi_direct_retry(region):
    for attempt in range(1, GOV_RETRIES + 1):
        try:
            return get_psi_direct(region)
        except Exception as e:
            obs.count("psi.data_gov.error")
            if attempt == GOV_RETRIES:
                raise
            obs.event("psi_retry", source="data.gov.sg", attempt=attempt, error=str(e))
            time.sleep(GOV_RETRY_DELAY * attempt)

def get_psi(region):
    """Get the current 24-hr PSI for a Singapore region or area (e.g. 'east', 'bedok').
    Order: recent cached reading, Haze-API (unless its breaker is open), data.gov.sg,
    and finally an older cached reading."""
    key = region.strip().lower()
    cached = psi_cache.get_fresh(key)
    if cached is not None:
        obs.count("psi.cache_hit")
        obs.event("psi", region=key, source="cache")
        return cached

    primary_error = None
    if haze_breaker.allow():
        data, primary_error = get_psi_haze(region)
        if data is not None:
            psi_cache.put(key, data)
            obs.event("psi", region=key, source="haze-api")
            return data
    else:
        primary_error = "Haze-API skipped, it failed recently"
        obs.count("psi.haze_api.skipped")

    obs.event("psi_fallback", region=key, reason=primary_error, breaker=haze_breaker.state)
    try:
        data = get_psi_direct_retry(region)
    except Exception as e:
        stale = psi_cache.get_stale(key)
        if stale is not None:
            obs.count("psi.stale_served")
            obs.event("psi", region=key, source="stale-cache", error=str(e))
            return stale
        obs.event("psi_failed", region=key, haze_error=primary_error, gov_error=str(e))
        return {"error": f"Haze-API and data.gov.sg both unavailable: {primary_error}; {e}"}
    if "error" not in data:
        psi_cache.put(key, data)
    obs.event("psi", region=key, source="data.gov.sg")
    return data


#who an advisory is written for; "all" chunks apply to everyone and are always included
GROUPS = ["healthy", "sensitive", "chronic", "worker"]
#healthy = healthy adults, sensitive = elderly/pregnant/children,
#chronic = chronic lung or heart disease, worker = employers and outdoor workers (MOM)

def advisory_filter(psi, group):
    """Chroma filter: chunks whose PSI band covers this PSI AND that are written for this group
    (or for everyone). Done here in code so the model can never be handed another group's advice."""
    return {"$and": [
        {"min_psi": {"$lte": psi}},
        {"max_psi": {"$gte": psi}},
        {"group": {"$in": [group, "all"]}},
    ]}

def search_advisories(question, psi, group, n_results=3):
    """Find official NEA/MOM haze advice for this question, PSI level and group of people."""
    if group not in GROUPS:
        return {"error": f"Unknown group '{group}'. Use one of: {', '.join(GROUPS)}."}
    where = advisory_filter(psi, group)
    t0 = time.time()

    if USE_EMBEDDINGS:
        #semantic search: rules for this PSI and group, ranked by meaning
        results = get_rules().query(query_texts=[question], n_results=n_results, where=where)
        docs = results["documents"][0]
        metas = results["metadatas"][0]
    else:
        #no embedding model: return every rule for this PSI and group and let the AI pick
        results = get_rules().get(where=where)
        docs = results["documents"]
        metas = results["metadatas"]

    obs.observe("search_advisories", time.time() - t0)
    obs.event("search_advisories", embeddings=USE_EMBEDDINGS, psi=psi, group=group, rules=len(docs),
              seconds=round(time.time() - t0, 2))
    return [{"source": meta["source"], "text": text} for text, meta in zip(docs, metas)]

if __name__ == "__main__":
    psi_info = get_psi("bedok")
    print("PSI:", psi_info)

    if "error" not in psi_info:
        advice = search_advisories("Can my construction workers work outside?", psi_info["psi"], "worker")
        for a in advice:
            print(f"[{a['source']}] {a['text']}")