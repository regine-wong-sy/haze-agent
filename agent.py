import json
import os
import time
import uuid
from dotenv import load_dotenv
from ollama import Client, Message
import obs
import tools

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
local_client = Client(host="http://localhost:11434") #Ollama on my laptop
cloud_client = Client(host="https://ollama.com",
                      headers={"Authorization": "Bearer " + os.environ["OLLAMA_API_KEY"].strip()},
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
                           "question at a given PSI for one group of people. Requires a PSI number, so call get_psi first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "What the user wants to do"},
                    "psi": {"type": "integer", "description": "The 24-hr PSI from get_psi"},
                    "group": {"type": "string", "enum": tools.GROUPS,
                              "description": "Who the question is about: healthy (healthy adults), "
                                             "sensitive (children, elderly, pregnant), "
                                             "chronic (heart or lung disease), "
                                             "worker (employers and outdoor workers)"},
                },
                "required": ["question", "psi", "group"],
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
    "Choose the group the user is asking about when you call search_advisories; "
    "it only returns advice for that group. "
)
# 3. Map tool names to your real Python functions
def run_tool(name, args):
    if name == "get_psi":
        return tools.get_psi(args["region"])
    if name == "search_advisories":
        return tools.search_advisories(args["question"], int(args["psi"]), args.get("group", ""))
    return {"error": f"Unknown tool: {name}"}

def safe_run_tool(name, args):
    """A tool that crashes (e.g. the model sent psi='high') becomes an error the model can read,
    instead of ending the whole run."""
    try:
        return run_tool(name, args)
    except Exception as e:
        obs.count(f"tool.{name}.crashed")
        obs.event("tool_crashed", tool=name, error=repr(e))
        return {"error": f"{name} failed: {e}"}

# 4. The agent loop
#the cloud client times out each model call at 25s; this caps the whole run so a slow
#get_psi plus several model calls can't hold the request open past the host's limit
MAX_SECONDS = 70

#shown on the page while a tool runs
STATUS = {"get_psi": "Checking the live PSI...", "search_advisories": "Looking up NEA/MOM guidelines..."}

def ask(question, max_steps=5, route="cloud", max_seconds=MAX_SECONDS):
    """Run the agent and return the finished info dict."""
    steps = run(question, max_steps, route, max_seconds, stream=False)
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value

def run(question, max_steps, route, max_seconds, stream):
    """The agent loop as a generator. It yields {"type": "status"|"token", "text": ...} while it
    works (tokens only when stream=True) and returns the info dict when it finishes."""
    #max_steps 5: 3 ran out when get_psi had to be retried for an unknown area
    client = MODELS[route]["client"]
    model = MODELS[route]["model"]
    info = {"area": None, "psi": None, "tools_used": [], "route": route, "stopped": None}
    run_id = uuid.uuid4().hex[:8] #ties together all the log lines of one question
    started = time.monotonic()
    obs.count("agent.runs")
    obs.event("agent_start", run=run_id, route=route, question_chars=len(question))

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
    ]

    for step in range(1, max_steps + 1):
        if time.monotonic() - started > max_seconds:
            info["stopped"] = "deadline"
            break
        t0 = time.time()
        try:
            kwargs = {"model": model, "messages": messages, "tools": TOOLS}
            if route == "local":
                #qwen3 "thinks" out loud by default, turn off so faster
                kwargs["think"] = False
            if not stream:
                message = client.chat(**kwargs).message
            else:
                content, calls = "", []
                for chunk in client.chat(stream=True, **kwargs):
                    piece = chunk.message.content or ""
                    if piece:
                        content += piece
                        yield {"type": "token", "text": piece}
                    calls += chunk.message.tool_calls or []
                message = Message(role="assistant", content=content, tool_calls=calls or None)
        except Exception as e:
            obs.count("agent.model_error")
            obs.event("model_error", run=run_id, step=step, error=repr(e),
                      seconds=round(time.monotonic() - started, 1))
            raise
        obs.observe(f"model.{route}", time.time() - t0)
        obs.event("model_call", run=run_id, step=step, model=model, seconds=round(time.time() - t0, 2))
        messages.append(message)

        if not message.tool_calls:          # no tool requested = final answer
            answer = message.content or ""
            info["answer"]=answer.split("</think>")[-1].strip()
            return finish(info, run_id, started)

        for call in message.tool_calls:
            name = call.function.name
            args = call.function.arguments
            yield {"type": "status", "text": STATUS.get(name, "Working...")}
            t1 = time.time()
            output = safe_run_tool(name, args)
            info["tools_used"].append(name)
            if name == "get_psi":
                info["area"]= args.get("region")
                if "error" not in output:
                        info["psi"] = output["psi"]
            obs.observe(f"tool.{name}", time.time() - t1)
            #not the full args: search_advisories gets the user's question, which can hold health details
            obs.event("tool_call", run=run_id, step=step, tool=name, region=args.get("region"),
                      ok="error" not in output if isinstance(output, dict) else True,
                      seconds=round(time.time() - t1, 2))
            messages.append({"role": "tool", "tool_name": name, "content": json.dumps(output)})
    #ran out of steps or time without a final answer
    info["stopped"] = info["stopped"] or "max_steps"
    obs.count(f"agent.stopped.{info['stopped']}")
    info["answer"] =SORRY
    return finish(info, run_id, started)

def finish(info, run_id, started):
    seconds = time.monotonic() - started
    obs.observe("agent.run", seconds)
    obs.event("agent_done", run=run_id, route=info["route"], tools=info["tools_used"],
              psi=info["psi"], stopped=info["stopped"], seconds=round(seconds, 1))
    return info

if __name__ == "__main__":
    print(ask(input("Ask: "))["answer"])