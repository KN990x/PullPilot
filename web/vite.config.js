import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // "prompt", not "autoUpdate": autoUpdate never fires main.jsx's onNeedRefresh, so
      // the confirm() and its two translations were dead code. It also reloads the tab on
      // its own, which is the wrong thing to do to someone watching an update run.
      registerType: "prompt",
      includeAssets: ["assets/logo.png"],
      workbox: {
        // The screenshots for the README used to live in public/assets and matched this
        // glob, so a 310 KB image nothing referenced was precached into every install.
        // They are in docs/ now; keep this list to what the app actually loads.
        globPatterns: ["**/*.{js,css,html,ico,svg}", "assets/logo.png"],
        // Login lives in the SPA, so the service worker serves it the shell. The only
        // thing the shell can never answer is an API call.
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
    // Only /api. /login and /logout were proxied too, but the SPA has never called them:
    // they are 302 shims the backend keeps for bookmarks on the old bundle.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
