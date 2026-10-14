from flask import Flask, request
from flask_cors import CORS
from agent import ask, SORRY

app = Flask(__name__)
CORS(app, origins=["https://haze-api.onrender.com"]) #only my Haze-API site can call /ask
MAX_QUESTION_LENGTH = 300 #stops people using up the free quota


@app.route("/")
def home():
    return app.send_static_file("index.html")

@app.route("/ask", methods=["POST"])
def ask_route():
    #reads the JSON sent by the page. Now question is "Can workers..."
    data = request.get_json(silent=True)
    if data is None:
        return {"error": "No JSON body"}, 400

    question = data.get("question", "").strip()
    if question == "":
        return {"error": "No question"}, 400

    if len(question) > MAX_QUESTION_LENGTH:
        return {"error": "Question too long",
                "max_length": MAX_QUESTION_LENGTH
        }, 400

    #runs the agent loop (get_psi -> search_advisories -> answer)
    try:
        answer = ask(question)
    except Exception as e:
        print(f"Agent failed: {e}")
        #timeouts and model errors: say sorry instead of hanging or showing an error
        return {"question": question, "answer": SORRY}

    return {"question": question, "answer": answer}

if __name__ == "__main__":
    app.run(port=8081, debug=True)