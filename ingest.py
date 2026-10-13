import chromadb

client = chromadb.PersistentClient(path="chroma_db")
try:
    # Deletes the old advisories collection if it exists
    client.delete_collection("advisories")
except Exception:
    pass
rules = client.create_collection("advisories")

# Reads the whole text file and splits it at every blank line (\n\n = two newlines)
with open("docs/advisories.txt", encoding="utf-8") as f:
    blocks = f.read().strip().split("\n\n")

ids, docs, metas = [], [], []
for i, block in enumerate(blocks):
    # header = ## band=101-200 | source=NEA
    # text = Healthy persons: If 24 hr PSI is Unhealthy...
    header, text = block.split("\n", 1)

    header_text = header[2:]             # "band=101-200 | source=NEA"
    parts = header_text.split("|")       # ["band=101-200 ", " source=NEA"]

    fields = {}
    for part in parts:
        part = part.strip()              # "band=101-200"
        key, value = part.split("=")     # key="band", value="101-200"
        fields[key] = value

    # fields is now {"band": "101-200", "source": "NEA"}

    band = fields["band"]                # "101-200"
    lo, hi = band.split("-")             # lo="101", hi="200"
    
    ids.append(f"chunk-{i}")
    docs.append(text.strip())
    metas.append({"min_psi": int(lo), "max_psi": int(hi), "source": fields["source"]})

rules.add(ids=ids, documents=docs, metadatas=metas)
print(f"Loaded {len(ids)} chunks")