import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // In development the dashboard calls /api/... on its own origin and Vite
    // forwards it to the local backend. That keeps VITE_API_URL empty locally
    // and avoids CORS entirely while developing.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
