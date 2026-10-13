import os
import requests
import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

HAZE_API = "https://haze-api.onrender.com/haze"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

#keep the embedding model inside the project so Render doesn't throw it away after the build
ONNXMiniLM_L6_V2.DOWNLOAD_PATH = os.path.join(BASE_DIR, "onnx_model")

client = chromadb.PersistentClient(path=os.path.join(BASE_DIR, "chroma_db"))
rules = client.get_collection("advisories")

USE_EMBEDDINGS = os.environ.get("USE_EMBEDDINGS", "1") == "1" #set to 0 on Render

#warm up: load the model when the server starts (only if we're using it)
if USE_EMBEDDINGS:
    rules.query(query_texts=["warm up"], n_results=1)

def get_psi(region):
    """Get the current 24-hr PSI for a Singapore region or area (e.g. 'east', 'bedok')."""
    try:
        resp = requests.get(HAZE_API, params={"region": region}, timeout=60)
        data = resp.json()
    except Exception as e:
        return {"error": f"Haze-API unavailable: {e}"}

    if resp.status_code != 200:
        return {"error": data.get("error", "unknown error"), "details": data}
    return data


def search_advisories(question, psi, n_results=3):
    """Find official NEA/MOM haze advice relevant to the question at this PSI level."""
    psi_filter = {"$and": [{"min_psi": {"$lte": psi}}, {"max_psi": {"$gte": psi}}]}

    if USE_EMBEDDINGS:
        #semantic search: rules for this PSI, ranked by meaning
        results = rules.query(query_texts=[question], n_results=n_results, where=psi_filter)
        docs = results["documents"][0]
        metas = results["metadatas"][0]
    else:
        #no embedding model: return every rule for this PSI and let the AI pick
        results = rules.get(where=psi_filter)
        docs = results["documents"]
        metas = results["metadatas"]

    return [{"source": meta["source"], "text": text} for text, meta in zip(docs, metas)]

if __name__ == "__main__":
    psi_info = get_psi("bedok")
    print("PSI:", psi_info)

    if "error" not in psi_info:
        advice = search_advisories("Can my construction workers work outside?", psi_info["psi"])
        for a in advice:
            print(f"[{a['source']}] {a['text']}")