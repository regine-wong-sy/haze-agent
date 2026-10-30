import os
os.environ["USE_EMBEDDINGS"] = "0"  #skip loading the embedding model, these tests don't need it
os.environ.setdefault("OLLAMA_API_KEY", "test")  #agent.py reads it at import; no call is made

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ollama import Message

import agent
import obs


def reply(content="", tool_calls=None):
    return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))

def tool_call(name, **args):
    #the real class, because streaming builds an ollama Message out of the calls
    return Message.ToolCall(function=Message.ToolCall.Function(name=name, arguments=args))


class FakeClient:
    """Hands out the scripted replies one by one; an Exception in the script is raised."""
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if kwargs.get("stream"):
            return iter(item)  #a streamed call gets a list of chunks
        return item


class AgentTest(unittest.TestCase):
    def ask(self, script, **kwargs):
        client = FakeClient(script)
        with patch.dict(agent.MODELS["cloud"], {"client": client}):
            info = agent.ask("is it safe to jog in bedok?", **kwargs)
        return info, client

    def setUp(self):
        obs.reset()

    def test_answers_after_a_tool_call(self):
        script = [reply(tool_calls=[tool_call("get_psi", region="bedok")]), reply("It is moderate.")]
        with patch("agent.tools.get_psi", lambda region: {"region": "east", "psi": 73, "level": "Moderate"}):
            info, _ = self.ask(script)
        self.assertEqual(info["answer"], "It is moderate.")
        self.assertEqual(info["psi"], 73)
        self.assertEqual(info["tools_used"], ["get_psi"])
        self.assertIsNone(info["stopped"])

    def test_gives_up_after_max_steps(self):
        script = [reply(tool_calls=[tool_call("get_psi", region="bedok")])] * 3
        with patch("agent.tools.get_psi", lambda region: {"error": "nope"}):
            info, client = self.ask(script, max_steps=3)
        self.assertEqual(info["answer"], agent.SORRY)
        self.assertEqual(info["stopped"], "max_steps")
        self.assertEqual(client.calls, 3)

    def test_gives_up_when_over_the_time_budget(self):
        script = [reply(tool_calls=[tool_call("get_psi", region="bedok")]), reply("never reached")]
        with patch("agent.tools.get_psi", lambda region: {"error": "nope"}):
            info, client = self.ask(script, max_seconds=-1)
        self.assertEqual(info["answer"], agent.SORRY)
        self.assertEqual(info["stopped"], "deadline")
        self.assertEqual(client.calls, 0)

    def test_a_crashing_tool_does_not_end_the_run(self):
        #the model sends a psi that isn't a number, so int() raises inside run_tool
        script = [reply(tool_calls=[tool_call("search_advisories", question="q", psi="high", group="healthy")]),
                  reply("Sorry about that.")]
        info, _ = self.ask(script)
        self.assertEqual(info["answer"], "Sorry about that.")
        self.assertEqual(obs.snapshot()["counts"]["tool.search_advisories.crashed"], 1)

    def test_a_tool_call_missing_its_argument_does_not_end_the_run(self):
        script = [reply(tool_calls=[tool_call("get_psi")]), reply("Which area?")]
        info, _ = self.ask(script)
        self.assertEqual(info["answer"], "Which area?")

    def test_model_errors_still_reach_the_caller(self):
        #web.py turns these into SORRY
        with self.assertRaises(TimeoutError):
            self.ask([TimeoutError("slow")])
        self.assertEqual(obs.snapshot()["counts"]["agent.model_error"], 1)


def chunk(content="", tool_calls=None):
    return reply(content, tool_calls)


class StreamTest(unittest.TestCase):
    def events(self, script):
        """Run the streaming loop; returns (events yielded, info returned)."""
        client = FakeClient(script)
        seen = []
        with patch.dict(agent.MODELS["cloud"], {"client": client}):
            steps = agent.run("is it safe to jog in bedok?", 5, "cloud", 70, stream=True)
            while True:
                try:
                    seen.append(next(steps))
                except StopIteration as done:
                    return seen, done.value

    def test_tokens_come_out_one_piece_at_a_time(self):
        seen, info = self.events([[chunk("It is "), chunk("moderate."), chunk("")]])
        self.assertEqual([e["text"] for e in seen if e["type"] == "token"], ["It is ", "moderate."])
        self.assertEqual(info["answer"], "It is moderate.")

    def test_status_is_sent_while_a_tool_runs_then_the_answer_streams(self):
        script = [[chunk(tool_calls=[tool_call("get_psi", region="bedok")])], [chunk("Fine "), chunk("to jog.")]]
        with patch("agent.tools.get_psi", lambda region: {"region": "east", "psi": 73, "level": "Moderate"}):
            seen, info = self.events(script)
        self.assertEqual([e["type"] for e in seen], ["status", "token", "token"])
        self.assertEqual(seen[0]["text"], agent.STATUS["get_psi"])
        self.assertEqual(info["answer"], "Fine to jog.")
        self.assertEqual(info["psi"], 73)

    def test_tool_calls_are_remembered_for_the_next_model_call(self):
        sent = []
        client = FakeClient([[chunk(tool_calls=[tool_call("get_psi", region="bedok")])], [chunk("ok")]])
        real_chat = client.chat
        client.chat = lambda **kw: (sent.append(list(kw["messages"])), real_chat(**kw))[1]
        with patch.dict(agent.MODELS["cloud"], {"client": client}), \
             patch("agent.tools.get_psi", lambda region: {"region": "east", "psi": 73, "level": "Moderate"}):
            steps = agent.run("q", 5, "cloud", 70, stream=True)
            for _ in steps:
                pass
        assistant = sent[1][-2]  #the message just before the tool result
        self.assertEqual(assistant.role, "assistant")
        self.assertEqual(assistant.tool_calls[0].function.name, "get_psi")


class StreamEndpointTest(unittest.TestCase):
    def post(self, body, script=None):
        import web
        client = FakeClient(script or [])
        with patch.dict(agent.MODELS["cloud"], {"client": client}), \
             patch("web.save_conversation", lambda q, info: None):
            return web.app.test_client().post("/ask/stream", json=body)

    def lines(self, response):
        import json
        return [json.loads(line) for line in response.get_data(as_text=True).splitlines()]

    def test_streams_tokens_then_a_done_line_with_the_full_answer(self):
        response = self.post({"question": "hello"}, [[chunk("Hi "), chunk("there")]])
        self.assertEqual(response.mimetype, "application/x-ndjson")
        lines = self.lines(response)
        self.assertEqual([l["type"] for l in lines], ["token", "token", "done"])
        self.assertEqual(lines[-1]["answer"], "Hi there")

    def test_rejects_bad_requests_like_ask_does(self):
        self.assertEqual(self.post({"question": "  "}).status_code, 400)
        self.assertEqual(self.post({"question": "x" * 301}).status_code, 400)

    def test_model_failure_ends_with_sorry(self):
        lines = self.lines(self.post({"question": "hello"}, [TimeoutError("slow")]))
        self.assertEqual(lines[-1], {"type": "done", "answer": agent.SORRY})


if __name__ == "__main__":
    unittest.main()
