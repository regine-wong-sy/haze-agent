import chromadb

client = chromadb.PersistentClient(path="chroma_db")
rules = client.get_collection("advisories")

psi = 150
question = "Can my construction workers work outside?"

# Turns the question into an embedding and searches for chunks closest in meaning
# It’s in a list [ ] because Chroma can search several questions at once
results = rules.query(
    query_texts=[question],
    # Return the top 3 closest chunks
    n_results=3,
    where={"$and": [{"min_psi": {"$lte": psi}}, {"max_psi": {"$gte": psi}}]},
)

for text, meta in zip(results["documents"][0], results["metadatas"][0]):
    print(f"[{meta['source']}] {text}\n")