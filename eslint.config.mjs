import js from "@eslint/js";
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import importPlugin from "eslint-plugin-import";
import prettierConfig from "eslint-config-prettier";

// Browser globals — avoids no-undef for window, document, fetch, etc.
const browserGlobals = {
  window: "readonly", document: "readonly", navigator: "readonly",
  fetch: "readonly", Request: "readonly", Response: "readonly", Headers: "readonly",
  URL: "readonly", URLSearchParams: "readonly",
  console: "readonly", setTimeout: "readonly", setInterval: "readonly",
  clearTimeout: "readonly", clearInterval: "readonly",
  indexedDB: "readonly", IDBDatabase: "readonly",
  confirm: "readonly", alert: "readonly", prompt: "readonly",
  localStorage: "readonly", sessionStorage: "readonly",
  location: "readonly", history: "readonly",
  crypto: "readonly", performance: "readonly",
  EventTarget: "readonly", Event: "readonly", CustomEvent: "readonly",
  AbortController: "readonly", AbortSignal: "readonly",
  // Fetch API types (DOM lib) — used in type annotations
  RequestInit: "readonly", RequestInfo: "readonly", ResponseInit: "readonly",
  // Node.js / Expo globals
  process: "readonly", Buffer: "readonly", global: "readonly",
  // JSX transform — React is not imported explicitly
  React: "readonly",
  // Google Maps loaded via @googlemaps/js-api-loader at runtime
  google: "readonly",
};

/** @type {import("eslint").Linter.FlatConfig[]} */
export default [
  // Base JS rules
  js.configs.recommended,

  // TypeScript files
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        project: true,
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: browserGlobals,
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      import: importPlugin,
    },
    rules: {
      // TypeScript recommended (without type-checking strict rules)
      ...tsPlugin.configs["recommended"].rules,

      // Type-checking rules — warn only (codebase not built for strict any)
      "@typescript-eslint/no-unsafe-assignment":    "warn",
      "@typescript-eslint/no-unsafe-member-access": "warn",
      "@typescript-eslint/no-unsafe-argument":      "warn",
      "@typescript-eslint/no-unsafe-return":        "warn",
      "@typescript-eslint/no-unsafe-call":          "warn",

      // Async rules — warn, not error (existing code uses async event handlers)
      "@typescript-eslint/no-floating-promises":    "warn",
      "@typescript-eslint/no-misused-promises":     "warn",
      "@typescript-eslint/promise-function-async":  "off",

      // Promise rejection
      "@typescript-eslint/prefer-promise-reject-errors": "warn",

      // Return types — warn for gradual adoption
      "@typescript-eslint/explicit-function-return-type": [
        "warn",
        { allowExpressions: true, allowTypedFunctionExpressions: true },
      ],

      // No any — warn not error
      "@typescript-eslint/no-explicit-any": "warn",

      // Consistent type imports — warn (auto-fixable)
      "@typescript-eslint/consistent-type-imports": [
        "warn",
        { prefer: "type-imports", fixStyle: "inline-type-imports" },
      ],

      // Unused vars — error for real mistakes, ignore _-prefixed
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],

      // Import order — error (auto-fixable)
      "import/order": [
        "error",
        {
          groups: ["builtin", "external", "internal", "parent", "sibling", "index", "type"],
          "newlines-between": "always",
          alphabetize: { order: "asc", caseInsensitive: true },
        },
      ],
      "import/no-duplicates": "error",

      // General quality
      "no-console":  ["warn", { allow: ["warn", "error"] }],
      "no-debugger": "error",
      "prefer-const": "error",
      "no-var": "error",
    },
  },

  // Test files — relax rules
  {
    files: ["**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}", "**/__tests__/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-explicit-any":       "off",
      "@typescript-eslint/no-non-null-assertion": "off",
      "@typescript-eslint/no-unsafe-assignment":  "off",
    },
  },

  // Prettier last
  prettierConfig,

  // Global ignores
  {
    ignores: [
      "node_modules/**", "dist/**", "build/**",
      ".expo/**", "coverage/**", "**/*.d.ts",
    ],
  },
];
