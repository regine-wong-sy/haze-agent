import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import type { Server } from "node:http";
import { createApp } from "./app";
import type { Db } from "./app";

const PASSWORD = "s3cret";
const login = (password: string) => "Basic " + Buffer.from(`admin:${password}`).toString("base64");

const row = { id: 7, question: "Can kids play?", answer: "No", flagged: false };

// Fake database: records every query and replies with whatever the test set
let calls: { text: string; values?: unknown[] }[];
let reply: { rows: unknown[]; rowCount: number | null };
let failWith: Error | null;
const db: Db = {
  async query<T>(text: string, values?: unknown[]) {
    calls.push({ text, values });
    if (failWith) throw failWith;
    return reply as { rows: T[]; rowCount: number | null };
  },
};

let server: Server;
let base: string;

beforeEach(async () => {
  calls = [];
  reply = { rows: [row], rowCount: 1 };
  failWith = null;
  process.env.DASHBOARD_PASSWORD = PASSWORD;
  server = createApp(db).listen(0);
  await new Promise((resolve) => server.once("listening", resolve));
  base = `http://localhost:${(server.address() as AddressInfo).port}`;
});

afterEach(() => {
  server.close();
});

const asAdmin = { Authorization: login(PASSWORD) };

test("health check needs no login", async () => {
  const res = await fetch(`${base}/health`);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { ok: true });
});

test("no login -> 401 with a browser login popup, and the database is never touched", async () => {
  const res = await fetch(`${base}/conversations`);
  assert.equal(res.status, 401);
  assert.match(res.headers.get("www-authenticate") ?? "", /^Basic/);
  assert.equal(calls.length, 0);
});

test("wrong password -> 401", async () => {
  const res = await fetch(`${base}/conversations`, { headers: { Authorization: login("wrong") } });
  assert.equal(res.status, 401);
  assert.equal(calls.length, 0);
});

test("wrong username -> 401", async () => {
  const auth = "Basic " + Buffer.from(`root:${PASSWORD}`).toString("base64");
  const res = await fetch(`${base}/conversations`, { headers: { Authorization: auth } });
  assert.equal(res.status, 401);
});

test("flagging without login -> 401 and nothing is updated", async () => {
  const res = await fetch(`${base}/conversations/7/flag`, { method: "POST" });
  assert.equal(res.status, 401);
  assert.equal(calls.length, 0);
});

test("fails closed: no DASHBOARD_PASSWORD set -> everything is blocked", async () => {
  delete process.env.DASHBOARD_PASSWORD;
  // includes logging in with the literal text "undefined", which a careless check would accept
  for (const auth of [login("undefined"), login(""), undefined]) {
    const res = await fetch(`${base}/conversations`, auth ? { headers: { Authorization: auth } } : {});
    assert.equal(res.status, 401);
  }
  assert.equal(calls.length, 0);
});

test("fails closed: empty DASHBOARD_PASSWORD blocks an empty-password login", async () => {
  process.env.DASHBOARD_PASSWORD = "";
  const res = await fetch(`${base}/conversations`, { headers: { Authorization: login("") } });
  assert.equal(res.status, 401);
});

test("GET /conversations with login returns the newest 50", async () => {
  const res = await fetch(`${base}/conversations`, { headers: asAdmin });
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), [row]);
  assert.match(calls[0].text, /ORDER BY created_at DESC LIMIT 50/);
});

test("POST flag flips the row using a parameterised query", async () => {
  const res = await fetch(`${base}/conversations/7/flag`, { method: "POST", headers: asAdmin });
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), row);
  assert.deepEqual(calls[0].values, [7]);
  assert.doesNotMatch(calls[0].text, /7/);
});

test("POST flag with a non-numeric id -> 400 and no query", async () => {
  const res = await fetch(`${base}/conversations/abc/flag`, { method: "POST", headers: asAdmin });
  assert.equal(res.status, 400);
  assert.equal(calls.length, 0);
});

test("POST flag with a SQL-looking id -> 400 and no query", async () => {
  const id = encodeURIComponent("1; DROP TABLE conversations");
  const res = await fetch(`${base}/conversations/${id}/flag`, { method: "POST", headers: asAdmin });
  assert.equal(res.status, 400);
  assert.equal(calls.length, 0);
});

test("POST flag on a missing row -> 404", async () => {
  reply = { rows: [], rowCount: 0 };
  const res = await fetch(`${base}/conversations/999/flag`, { method: "POST", headers: asAdmin });
  assert.equal(res.status, 404);
});

test("database failure -> 500, not a hang", async () => {
  failWith = new Error("db down");
  const quiet = console.error;
  console.error = () => {};   // Express logs the error; keep test output clean
  try {
    const res = await fetch(`${base}/conversations`, { headers: asAdmin });
    assert.equal(res.status, 500);
  } finally {
    console.error = quiet;
  }
});
