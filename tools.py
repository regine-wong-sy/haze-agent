import requests
import chromadb

HAZE_API = "https://haze-api.onrender.com/haze"

client = chromadb.PersistentClient(path="chroma_db")
rules = client.get_collection("advisories")


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
    results = rules.query(
        query_texts=[question],
        n_results=n_results,
        where={"$and": [{"min_psi": {"$lte": psi}}, {"max_psi": {"$gte": psi}}]},
    )
    return [
        {"source": meta["source"], "text": text}
        for text, meta in zip(results["documents"][0], results["metadatas"][0])
    ]


if __name__ == "__main__":
    psi_info = get_psi("bedok")
    print("PSI:", psi_info)

    if "error" not in psi_info:
        advice = search_advisories("Can my construction workers work outside?", psi_info["psi"])
        for a in advice:
            print(f"[{a['source']}] {a['text']}")