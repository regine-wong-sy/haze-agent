import { Pool } from "pg";
import { createApp } from "./app";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

// Render chooses the port and puts it in process.env.PORT
// falls back to 3001
const PORT: number = Number(process.env.PORT) || 3001;

// ===== START =====
createApp(pool).listen(PORT, () => {
  console.log(`API running on http://localhost:${PORT}`);
});
