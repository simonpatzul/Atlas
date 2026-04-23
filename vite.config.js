import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/context": "http://127.0.0.1:8000",
      "/context-all": "http://127.0.0.1:8000",
      "/market": "http://127.0.0.1:8000",
      "/mt4": "http://127.0.0.1:8000",
    },
  },
});
