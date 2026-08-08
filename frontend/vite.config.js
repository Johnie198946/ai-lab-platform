import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxyTarget = env.VITE_API_PROXY_TARGET || env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
  const authProxyTarget =
    env.VITE_AUTH_PROXY_TARGET || env.VITE_AUTH_BASE_URL || "http://127.0.0.1:8001";

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": {
          target: proxyTarget,
          changeOrigin: true,
        },
        "/health": {
          target: proxyTarget,
          changeOrigin: true,
        },
        "/authen-api": {
          target: authProxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/authen-api/, ""),
        },
      },
    },
  };
});
