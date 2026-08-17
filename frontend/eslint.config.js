import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // This codebase's convention for "intentionally discarded" destructured
      // values (e.g. `const { page: _page, ...rest } = filter`) is an
      // underscore prefix -- recognize it instead of flagging every instance.
      "@typescript-eslint/no-unused-vars": ["error", { varsIgnorePattern: "^_", argsIgnorePattern: "^_" }],
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // Flags IngestionPage/ReviewPage's "reset local state when an id/page prop
      // changes" effects. The rule's own suggested fix (remount via a `key` prop
      // on the parent instead) resets the *entire* subtree, not just the one
      // piece of state -- a real behavior change to a live app, not a safe
      // mechanical lint fix, so left as a deliberate exception rather than
      // reworked here.
      "react-hooks/set-state-in-effect": "off",
    },
  },
);
