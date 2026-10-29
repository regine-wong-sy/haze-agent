// ===== IMPORTS =====
import express from "express";
import type { Request, Response, NextFunction } from "express";
import path from "path";   // builds file paths, like Python's os.path

// ===== TYPE: one row of the conversations table =====
export type Conversation = {
  id: number;
  created_at: Date;
  question: string;
  area: string | null;
  psi: number | null;
  answer: string;
  tools_used: string[];
  route: string | null;
  flagged: boolean;
};

// The only part of pg's Pool the routes use, so tests can pass a fake
export type Db = {
  query<T = Conversation>(text: string, values?: unknown[]): Promise<{ rows: T[]; rowCount: number | null }>;
};

// ===== PASSWORD CHECK =====
// The browser shows its own login popup
// Username: admin, password: DASHBOARD_PASSWORD
// Fails closed: if DASHBOARD_PASSWORD isn't set, nobody gets in
export function requireLogin(req: Request, res: Response, next: NextFunction) {
  if (req.path === "/health") return next();   // health check doesn't need a password

  const password = process.env.DASHBOARD_PASSWORD;
  // The browser sends the login as "Basic " + base64("admin:password")
  const expected = "Basic " + Buffer.from(`admin:${password}`).toString("base64");

  // Wrong or missing password (or no password set at all) -> block
  if (!password || req.headers.authorization !== expected) {
    res.set("WWW-Authenticate", 'Basic realm="Haze dashboard"');   // tells the browser to show the popup
    res.status(401).send("Login required");
    return;
  }
  next();   // correct password -> carry on to the routes
}

// ===== APP =====
export function createApp(db: Db) {
  const app = express();

  // app.use = runs for EVERY request, before the routes below (middleware)
  app.use(requireLogin);

  // Like Flask's static folder: the built React files in dashboard/dist become the website
  app.use(express.static(path.join(process.cwd(), "../dashboard/dist")));

  // ===== ROUTE: GET /health =====
  app.get("/health", (req, res) => {
    res.json({ ok: true });
  });

  // ===== ROUTE: GET /conversations (newest 50) =====
  app.get("/conversations", async (req, res) => {
    const result = await db.query(
      "SELECT * FROM conversations ORDER BY created_at DESC LIMIT 50"
    );
    res.json(result.rows);
  });

  // ===== ROUTE: POST /conversations/:id/flag (flip flagged) =====
  app.post("/conversations/:id/flag", async (req, res) => {
    const id = Number(req.params.id);
    if (!Number.isInteger(id)) {
      res.status(400).json({ error: "Bad id" });
      return;
    }

    const result = await db.query(
      "UPDATE conversations SET flagged = NOT flagged WHERE id = $1 RETURNING *",
      [id]
    );

    if (result.rowCount === 0) {
      res.status(404).json({ error: "Not found" });
      return;
    }
    res.json(result.rows[0]);
  });

  return app;
}
