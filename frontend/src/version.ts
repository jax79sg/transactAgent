// Baked in at build time from the repository's VERSION file (vite.config.ts), so the interface always knows which
// release it is -- "unknown" if the file was missing or malformed (issue #27).
declare const __APP_VERSION__: string;

export const appVersion: string = __APP_VERSION__;
