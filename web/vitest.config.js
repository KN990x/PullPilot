import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Separate from vite.config.js on purpose: the PWA plugin has nothing to contribute to a
// jsdom run, and generating a service worker on every test run is pure noise.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
    include: ["src/**/*.test.{js,jsx}"],
    // No `globals: true`: describe/it/expect are imported explicitly so eslint can see
    // them, instead of teaching it another set of ambient names.
    globals: false,
  },
});
