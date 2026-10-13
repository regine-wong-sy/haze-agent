import chromadb

client = chromadb.Client()
rules = client.create_collection("advisories")

rules.add(
    ids=["NEA-good", "NEA-moderate", "NEA-unhealthy", "NEA-very-unhealthy", "NEA-hazardous"],
    documents=[
        "PSI 0-50 good: normal outdoor activities",
        "PSI 51-100 moderate: normal outdoor activities",
        "PSI 101-200 unhealthy: reduce prolonged or strenuous outdoor exertion; elderly, pregnant women and children should minimise it",
        "PSI 201-300 very unhealthy: avoid prolonged or strenuous outdoor exertion",
        "PSI above 300 hazardous: minimise all outdoor activity",
    ],
    metadatas=[
        {"min_psi": 0,   "max_psi": 50},
        {"min_psi": 51,  "max_psi": 100},
        {"min_psi": 101, "max_psi": 200},
        {"min_psi": 201, "max_psi": 300},
        {"min_psi": 301, "max_psi": 999},
    ],
)

psi = 150  # later, this comes from your Haze-API
question = "Can my class do a 2 hour outdoor sports session?"

results = rules.query(
    query_texts=[question],
    n_results=1,
    where={"$and": [{"min_psi": {"$lte": psi}}, {"max_psi": {"$gte": psi}}]},
)

print(f"PSI: {psi}\nQuestion: {question}\n")
for rule_id, text in zip(results["ids"][0], results["documents"][0]):
    print(f"{rule_id}  {text}")