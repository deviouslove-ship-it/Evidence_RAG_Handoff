import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendTarget = process.env.VITE_BACKEND_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 1420,
    strictPort: true,
    proxy: {
      "/api": backendTarget,
      "/health": backendTarget,
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 1420,
    proxy: {
      "/api": backendTarget,
      "/health": backendTarget,
    },
  },
  build: {
    target: "es2022",
    sourcemap: true,
  },
});
