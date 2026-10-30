import json
from flask import Flask, request, Response
from flask_cors import CORS
from agent import ask, run, SORRY, MAX_SECONDS
from db import save_conversation
import obs
app = Flask(__name__)
CORS(app, origins=["https://haze-api.onrender.com"]) #only my Haze-API site can call /ask
MAX_QUESTION_LENGTH = 300 #stops people using up the free quota


@app.route("/")
def home():
    return app.send_static_file("index.html")

def read_question():
    """Returns (question, None), or (None, error response) if the request is not usable."""
    #reads the JSON sent by the page. Now question is "Can workers..."
    data = request.get_json(silent=True)
    if data is None:
        return None, ({"error": "No JSON body"}, 400)

    question = data.get("question", "").strip()
    if question == "":
        return None, ({"error": "No question"}, 400)

    if len(question) > MAX_QUESTION_LENGTH:
        return None, ({"error": "Question too long",
                       "max_length": MAX_QUESTION_LENGTH
        }, 400)
    return question, None

@app.route("/ask/stream", methods=["POST"])
def ask_stream_route():
    """Same as /ask, but sends the answer as it is written: one JSON object per line,
    {"type": "status"|"token", "text": ...} while working, then {"type": "done", "answer": ...}.
    The done line always carries the full answer, so the page can replace what it typed."""
    question, error = read_question()
    if error:
        return error

    def events():
        obs.count("web.stream")
        info = None
        try:
            steps = run(question, max_steps=5, route="cloud", max_seconds=MAX_SECONDS, stream=True)
            while True:
                try:
                    yield json.dumps(next(steps)) + "\n"
                except StopIteration as done:
                    info = done.value
                    break
        except Exception as e:
            obs.count("web.agent_failed")
            obs.event("agent_failed", error=repr(e))
            yield json.dumps({"type": "done", "answer": SORRY}) + "\n"
            return
        try:
            save_conversation(question, info)
        except Exception as e:
            obs.count("web.save_failed")
            obs.event("save_failed", error=repr(e))
        yield json.dumps({"type": "done", "answer": info["answer"]}) + "\n"

    #no-transform and X-Accel-Buffering stop proxies from holding the lines back until the end
    return Response(events(), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})

@app.route("/ask", methods=["POST"])
def ask_route():
    question, error = read_question()
    if error:
        return error

    #runs the agent loop (get_psi -> search_advisories -> answer)
    try:
        info = ask(question)
    except Exception as e:
        obs.count("web.agent_failed")
        obs.event("agent_failed", error=repr(e))
        #timeouts and model errors: say sorry instead of hanging or showing an error
        return {"question": question, "answer": SORRY}
    try:
        save_conversation(question, info)
    except Exception as e:
        obs.count("web.save_failed")
        obs.event("save_failed", error=repr(e))
    return {"question": question, "answer": info["answer"]}

@app.route("/metrics")
def metrics():
    #counts and timings only, nothing a user typed
    return obs.snapshot()

if __name__ == "__main__":
    app.run(port=8081, debug=True)