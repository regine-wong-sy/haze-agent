import os
import requests
import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

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
    "woodlands": "north", "yishun": "north", "sembawang": "north", "ang mo kio": "north",
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
    return {"region": key, "psi": psi, "level": psi_level(psi), "source": "data.gov.sg"}

def get_psi(region):
    """Get the current 24-hr PSI for a Singapore region or area (e.g. 'east', 'bedok').
    Tries Haze-API first, then falls back to data.gov.sg directly."""
    try:
        resp = requests.get(HAZE_API, params={"region": region}, timeout=60)
        data = resp.json()
        if resp.status_code == 200:
            return data
        primary_error = data.get("error", f"HTTP {resp.status_code}")
    except Exception as e:
        primary_error = str(e)

    print(f"  Haze-API failed ({primary_error}), falling back to data.gov.sg", flush=True)
    try:
        return get_psi_direct(region)
    except Exception as e:
        return {"error": f"Haze-API and data.gov.sg both unavailable: {primary_error}; {e}"}


def search_advisories(question, psi, n_results=3):
    """Find official NEA/MOM haze advice relevant to the question at this PSI level."""
    psi_filter = {"$and": [{"min_psi": {"$lte": psi}}, {"max_psi": {"$gte": psi}}]}
    print(f"  search_advisories start | embeddings={USE_EMBEDDINGS} psi={psi}", flush=True)

    if USE_EMBEDDINGS:
        #semantic search: rules for this PSI, ranked by meaning
        results = get_rules().query(query_texts=[question], n_results=n_results, where=psi_filter)
        docs = results["documents"][0]
        metas = results["metadatas"][0]
    else:
        #no embedding model: return every rule for this PSI and let the AI pick
        results = get_rules().get(where=psi_filter)
        docs = results["documents"]
        metas = results["metadatas"]

    print(f"  search_advisories done | {len(docs)} rules found", flush=True)
    return [{"source": meta["source"], "text": text} for text, meta in zip(docs, metas)]

if __name__ == "__main__":
    psi_info = get_psi("bedok")
    print("PSI:", psi_info)

    if "error" not in psi_info:
        advice = search_advisories("Can my construction workers work outside?", psi_info["psi"])
        for a in advice:
            print(f"[{a['source']}] {a['text']}")