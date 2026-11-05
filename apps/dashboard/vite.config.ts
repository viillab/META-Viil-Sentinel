import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Explicit local-only development opt-in. Never proxy camera preview
// endpoints to a public server or bypass authorization at the Vite layer.
export default defineConfig(({ mode }) => {
  const localBridge = loadEnv(mode, ".", "VIIL_").VIIL_LOCAL_CAMERA_BRIDGE === "1";
  const bridge = { target: "http://127.0.0.1:8001", changeOrigin: false };

  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1", port: 5173, strictPort: true,
      proxy: {
        ...(localBridge ? {
          "/api/v1/operator/": bridge,
          "/api/v1/integrations/overview": bridge,
          "/api/v1/cameras/": bridge,
        } : {}),
        "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
      },
    },
  };
});
