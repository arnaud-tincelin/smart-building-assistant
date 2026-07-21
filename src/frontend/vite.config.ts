import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend URL is provided at runtime via public/config.js (rendered by the
// container entrypoint from BACKEND_URL). During local dev, /api is proxied to a
// locally running backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
