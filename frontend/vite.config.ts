/// <reference types="vitest/config" />
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import { parseVersion } from "./src/lib/parseVersion";

// The release number comes from the one VERSION file (issue #27): at the repository root in a checkout, copied next to
// this config in the Docker build. A missing or malformed file builds as "unknown" rather than failing the build.
function readAppVersion(): string {
  for (const candidate of [resolve(__dirname, "VERSION"), resolve(__dirname, "../VERSION")]) {
    if (existsSync(candidate)) return parseVersion(readFileSync(candidate, "utf-8"));
  }
  return parseVersion(null);
}

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(readAppVersion()),
  },
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
