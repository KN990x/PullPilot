import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["assets/logo.png"],
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg}"],
        // El login ya vive dentro de la SPA, así que el service worker debe servirle el
        // shell. Lo único que nunca puede resolver con el shell es una llamada a la API.
        navigateFallbackDenylist: [/^\/api\//],
      },
      manifest: {
        name: "PullPilot",
        short_name: "PullPilot",
        description: "Docker Homelab Updater",
        theme_color: "#ffffff",
        background_color: "#f8fafc",
        display: "standalone",
        orientation: "portrait",
        icons: [
          {
            src: "assets/logo.png",
            sizes: "512x512",
            type: "image/png",
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
      "/login": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
      "/logout": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
