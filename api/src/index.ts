import express from "express";   // the web server (Node's Flask)
import { Pool } from "pg";       // talks to Postgres (Node's psycopg)

// ===== TYPE: what one row of the conversations table looks like =====
type Conversation = {
  id: number;
  created_at: Date;
  question: string;
  area: string | null;     // "jurong", OR null if get_psi wasn't called
  psi: number | null;      // 206, OR null
  answer: string;          // agent's reply
  tools_used: string[];    // a list of strings, e.g. ["get_psi", "search_advisories"]
  route: string | null;    // "cloud" or "local"
  flagged: boolean;        // true / false
};


const app = express();   // like: app = Flask(__name__)

// Connection to Neon. "Pool" keeps a few connections open and reuses them,
// so each request doesn't have to reconnect.
const pool = new Pool({ connectionString: process.env.DATABASE_URL });

const PORT: number = 3001;

// ===== ROUTE 1: GET /health =====
// checks the server is alive
// app.get = @app.route("/health", methods=["GET"])
// (req, res) => {...} is the function that runs, like def health():
//   req = the incoming request, res = what we send back
app.get("/health", (req, res) => {
  res.json({ ok: true });   // like Flask: return {"ok": True}
});

// ===== ROUTE 2: GET /conversations =====
// Returns the newest 50 conversations as JSON.
// "async" = this function waits for something slow (the database)
app.get("/conversations", async (req, res) => {
  // "await" = wait for the database to answer before going to the next line
  // <Conversation> = tell TypeScript each row has the Conversation shape
  const result = await pool.query<Conversation>(
    "SELECT * FROM conversations ORDER BY created_at DESC LIMIT 50"
  );
  res.json(result.rows);   // result.rows = the list of rows. send it as json
});

// ===== ROUTE 3: POST /conversations/:id/flag =====
// Flips flagged true/false for one conversation.
// ":id" placeholder in the URL. For /conversations/2/flag, req.params.id = "2"
app.post("/conversations/:id/flag", async (req, res) => {
  // turn "2" into number 2
  const id = Number(req.params.id);

  // Reject junk like /conversations/abc/flag
  if (!Number.isInteger(id)) {
    res.status(400).json({ error: "Bad id" });   // like Flask: return {...}, 400
    return;
  }

  // $1 = a safe blank (pg's version of psycopg's %s), filled in by [id]
  // "SET flagged = NOT flagged" flips it: false -> true, true -> false
  // "RETURNING *" = send back the updated row
  const result = await pool.query<Conversation>(
    "UPDATE conversations SET flagged = NOT flagged WHERE id = $1 RETURNING *",
    [id]
  );

  // rowCount = how many rows were changed. 0 means that id doesn't exist.
  if (result.rowCount === 0) {
    res.status(404).json({ error: "Not found" });
    return;
  }

  res.json(result.rows[0]);   // send back the one updated row
});

// ===== START THE SERVER =====
// like Flask: app.run(port=3001)
// `...${PORT}...` with backticks = Python's f"...{PORT}..."
app.listen(PORT, () => {
  console.log(`API running on http://localhost:${PORT}`);   // console.log = print
});