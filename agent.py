import json
import os
import time
from dotenv import load_dotenv
from ollama import Client
import tools

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
local_client = Client(host="http://localhost:11434") #Ollama on my laptop
cloud_client = Client(host="https://ollama.com",
                      headers={"Authorization": "Bearer " + os.environ["OLLAMA_API_KEY"]},
                      timeout=25) #fail fast instead of hanging for a minute per call

SORRY = "Sorry, I don't know how to answer this. Try asking about haze conditions or what to do at the current PSI."

#each route = which client to talk to + which model
MODELS = {
    "local": {"client": local_client, "model": "qwen3:4b"},
    "cloud": {"client": cloud_client, "model": "gpt-oss:20b"},
}
# 1. Describe the tools to the model
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_psi",
            "description": "Get the live 24-hr PSI and level for a Singapore region "
                           "(north/south/east/west/central) or area (e.g. bedok, jurong). "
                           "Use this first whenever the user asks about current haze conditions.",
            "parameters": {
                "type": "object",
                "properties": {"region": {"type": "string", "description": "Region or area, e.g. 'jurong'"}},
                "required": ["region"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_advisories",
            "description": "Search official NEA and MOM haze guidelines for advice relevant to the "
                           "question at a given PSI. Requires a PSI number, so call get_psi first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "What the user wants to do"},
                    "psi": {"type": "integer", "description": "The 24-hr PSI from get_psi"},
                },
                "required": ["question", "psi"],
            },
        },
    },
]

# 2. Rules for how the agent behaves
SYSTEM = (
    "You are a Singapore haze safety assistant. Use get_psi for live PSI, then "
    "search_advisories for official guidance. "
    "Only state facts that appear in the tool results. Do not add thresholds, "
    "agencies, or rules from your own knowledge. "
    "If the advisories do not cover the question, say: 'The NEA/MOM guidelines I have "
    "don't cover this.' "
    "Cite the source (NEA or MOM) after each recommendation. "
    "Reply in plain text with short paragraphs or simple dashes. No tables, no bold, no markdown."
    "If the user is just greeting or not asking about haze, reply briefly and say what you can help with. "
    "Never mention tool names like get_psi or search_advisories in your answer. "
    "If the question is too vague to understand (e.g. 'help me') or is not about haze, "
    "do not call any tools. Reply exactly: Sorry, I don't know how to answer this. "
    "Match advice to the group the user is asking about (healthy people, children/elderly/pregnant, "
    "or people with heart/lung disease) and do not mix advice between groups. "
)
# 3. Map tool names to your real Python functions
def run_tool(name, args):
    if name == "get_psi":
        return tools.get_psi(args["region"])
    if name == "search_advisories":
        return tools.search_advisories(args["question"], int(args["psi"]))
    return {"error": f"Unknown tool: {name}"}

# 4. The agent loop
def ask(question, max_steps=3, route="cloud"):
    client = MODELS[route]["client"]
    model = MODELS[route]["model"]
    info = {"area": None, "psi": None, "tools_used": [], "route": route}


    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
    ]

    for _ in range(max_steps):
        t0 = time.time()
        if route == "local":
            #qwen3 "thinks" out loud by default, turn off so faster
            response = client.chat(model=model, messages=messages, tools=TOOLS, think=False)
        else:
            response = client.chat(model=model, messages=messages, tools=TOOLS)
        print(f"  model call took {time.time() - t0:.1f}s")
        messages.append(response.message)

        if not response.message.tool_calls:          # no tool requested = final answer
            answer = response.message.content or ""
            info["answer"]=answer.split("</think>")[-1].strip()
            return info
    
        for call in response.message.tool_calls:
            name = call.function.name
            args = call.function.arguments
            print(f"  -> calling {name}({args})")
            t1 = time.time()
            output = run_tool(name, args)
            info["tools_used"].append(name)
            if name == "get_psi":
                info["area"]= args["region"]
                if "error" not in output:
                        info["psi"] = output["psi"]
            print(f"  {name} took {time.time() - t1:.1f}s")
            messages.append({"role": "tool", "tool_name": name, "content": json.dumps(output)})
    info["answer"] =SORRY
    return info #ran out of steps without a final answer

if __name__ == "__main__":
    print(ask(input("Ask: "))["answer"])