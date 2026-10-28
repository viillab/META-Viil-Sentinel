import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Same-origin browser API path. Member 2 must enforce server-side auth
  // and per-camera RBAC; this local proxy is NOT an authorization boundary.
  server: {
    port: 5173, strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
});
