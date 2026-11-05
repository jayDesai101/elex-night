import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Absolute site URL for the share card (LinkedIn needs absolute og:image URLs).
const SITE_URL = (process.env.VITE_SITE_URL ?? "https://elex-night.vercel.app").replace(/\/$/, "");

export default defineConfig({
  plugins: [
    react(),
    {
      name: "site-url",
      transformIndexHtml: (html) => html.replaceAll("%SITE_URL%", SITE_URL),
    },
  ],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
