import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // The same build runs at localhost / and behind a /market-radar/ proxy.
  base: "./",
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8787", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8787", changeOrigin: true },
    },
  },
});
