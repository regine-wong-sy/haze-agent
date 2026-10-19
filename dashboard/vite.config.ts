import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Any request to /conversations gets forwarded to the API on port 3001.
    // The browser thinks it's talking to 5173, so there's no CORS problem.
    proxy: {
      "/conversations": "http://localhost:3001",
    },
  },
});