# Haze Agent

An AI agent that answers haze safety questions in Singapore using live PSI data and NEA and MOM guidelines, with a citation for every recommendation.

*"Can construction workers in Jurong work outside right now?"*
→ checks the live PSI (e.g. 156, Unhealthy), retrieves the matching MOM guidelines, and answers: employers should provide fit-tested masks, schedule regular breaks and keep workers hydrated, or risk enforcement under the Workplace Safety and Health Act (MOM).

**Live demo:** [haze-api.onrender.com](https://haze-api.onrender.com).
*(Free hosting: the first request after a quiet period can take up to a minute to wake up.)*

## How it works

1. **Agent loop.** The model decides which tool to call
my code runs it and returns the result, until the model has enough to answer.
2. **`get_psi`.** Calls my [Haze-API](https://github.com/regine-wong-sy/Haze-API), which serves live 24-hr PSI from NEA data.
3. **`search_advisories`.** Retrieves the official guidelines for that PSI level:
   - **Metadata filter** keeps only rules whose PSI range contains the current PSI (maths handled by code).
   - **Embedding search** ranks those rules by meaning, so "construction workers" matches "employers… outdoor work".
4. **Grounded answer.** The system prompt limits the model to facts from the retrieved rules, and makes it say so when the guidelines don't cover a question.

## Features

- **RAG** over 13 real NEA and MOM haze guideline chunks, tagged with PSI ranges
- **Tool calling** with an agent loop written from scratch (step limit, timeouts, errors returned as data)
- **MCP server** (server.py) exposes the same tools to any MCP client, such as Claude Desktop
- **Web chat** (web.py) deployed on Render and embedded in the Haze Monitor page via CORS
- **Eval suite** (eval.py) with 10 test cases and a fixed PSI so runs are repeatable

## Evaluation

eval.py runs 10 questions across all PSI bands, different groups (healthy adults, children, elderly, people with heart disease, employers) and one out-of-scope question, which the agent must admit it can't answer.


**Bug:** with all matching rules in context, the agent mixed advice between groups (it gave heart-patient advice to children). Adding a group-matching instruction to the system prompt fixed it, confirmed on re-runs.

Scores vary slightly between runs because LLM output isn't deterministic.

## Design decisions

- **Code for numbers, embeddings for meaning.** Embedding search alone matched "PSI 150" to the "PSI 0–50 good" rule, because it matched the words "outdoor activities". Filtering by PSI range first fixed this.
- **Two retrieval modes.** The ONNX embedding model stalled on Render's free-tier CPU, so production uses metadata filtering only (`USE_EMBEDDINGS=0`) and lets the model pick from the handful of matching rules. The eval measures the accuracy cost of that trade-off.
- **Separate services.** The agent runs as its own Render service, apart from Haze-API, so an agent failure doesn't take down the PSI site.

## Project structure

`docs/advisories.txt`: NEA and MOM guideline chunks, labelled with PSI range and source
`ingest.py`: Splits the rules into chunks and stores them in Chroma
`tools.py`: `get_psi` and `search_advisories`
`agent.py`: Agent loop (Ollama Cloud, `gpt-oss:20b`)
`server.py`: MCP server exposing the tools
`web.py` + `static/`: Flask `/ask` endpoint and chat page
`eval.py`: Evaluation suite

## Run locally

python -m venv .venv
.venv\Scripts\activate # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt


Create a `.env` file:
OLLAMA_API_KEY=your_key_here

python ingest.py     # build the rule database
python agent.py      # ask a question in the terminal
python web.py        # chat page at http://localhost:8081
python eval.py       # run the evaluation

To use the tools in Claude Desktop, add `server.py` under `mcpServers` in `claude_desktop_config.json`.

## Tech

Python · Flask · Chroma · ONNX MiniLM embeddings · Ollama Cloud (`gpt-oss:20b`) · MCP Python SDK · Render

## Sources

Guidelines are taken from the [NEA haze advisories](https://www.nea.gov.sg) and the [MOM guidelines for employers on protecting employees from haze](https://www.mom.gov.sg/haze/guidelines-on-protecting-employees-from-haze). This project is for learning and demonstration; check official sources for current advice.