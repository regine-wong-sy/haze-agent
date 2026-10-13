import os
from dotenv import load_dotenv
from ollama import Client

load_dotenv()
client = Client(host="https://ollama.com",
                headers={"Authorization": "Bearer " + os.environ["OLLAMA_API_KEY"]})

for m in client.list().models:
    print(m.model)