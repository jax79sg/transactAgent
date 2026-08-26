/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    // e2e/ holds Playwright specs (real-browser tests against a running
    // docker-compose stack, not jsdom) -- excluded here so vitest doesn't try to
    // execute them with its own `test`/`expect` globals, which aren't compatible.
    exclude: ["node_modules/**", "e2e/**"],
  },
});
