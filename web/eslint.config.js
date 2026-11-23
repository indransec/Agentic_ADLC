// Lint rules for the browser application (feature 022, research R-11).
//
// Besides the usual TypeScript, React and accessibility checks, these rules hold the
// application's safety and boundary rules (contracts/pages.md, FR-010 and FR-018):
// - no raw HTML: dangerouslySetInnerHTML, innerHTML, outerHTML and insertAdjacentHTML are errors;
// - only src/api/client.ts reaches the network (fetch, XMLHttpRequest);
// - only src/api/ imports the typed client library;
// - every file name is kebab-case (constitution XIII, SA Annex A.1).
import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import unicorn from "eslint-plugin-unicorn";
import globals from "globals";
import tseslint from "typescript-eslint";

const RAW_HTML = [
  { property: "innerHTML", message: "Show text with <Literal>; never write HTML (FR-010)." },
  { property: "outerHTML", message: "Show text with <Literal>; never write HTML (FR-010)." },
  {
    property: "insertAdjacentHTML",
    message: "Show text with <Literal>; never write HTML (FR-010).",
  },
];
const NETWORK = "Only src/api/client.ts talks to the platform (FR-018).";

export default tseslint.config(
  {
    ignores: [
      "dist/",
      "coverage/",
      "node_modules/",
      "test-results/",
      "playwright-report/",
      "src/api/schema.d.ts",
      "src/test/lint-fixtures/",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
      globals: { ...globals.browser },
    },
  },
  react.configs.flat.recommended,
  react.configs.flat["jsx-runtime"],
  reactHooks.configs.flat["recommended-latest"],
  jsxA11y.flatConfigs.recommended,
  {
    settings: { react: { version: "detect" } },
    plugins: { unicorn },
    rules: {
      "react/no-danger": "error",
      "react/prop-types": "off",
      "no-restricted-properties": ["error", ...RAW_HTML],
      "no-restricted-globals": [
        "error",
        { name: "fetch", message: NETWORK },
        { name: "XMLHttpRequest", message: NETWORK },
      ],
      "no-restricted-imports": ["error", { paths: [{ name: "openapi-fetch", message: NETWORK }] }],
      "unicorn/filename-case": ["error", { case: "kebabCase" }],
      "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
    },
  },
  {
    // The one module that reaches the network, and the API folder that owns the typed client
    files: ["src/api/client.ts"],
    rules: { "no-restricted-globals": "off" },
  },
  {
    files: ["src/api/**"],
    rules: { "no-restricted-imports": "off" },
  },
  {
    // Node-side test and build tooling: Playwright fixtures and config run outside the browser
    files: ["e2e/**", "*.config.ts"],
    languageOptions: { globals: { ...globals.node } },
    rules: { "no-restricted-globals": "off" },
  },
  // Last, so no typed rule above applies to plain JavaScript (this file)
  {
    files: ["**/*.js"],
    ...tseslint.configs.disableTypeChecked,
    languageOptions: {
      ...tseslint.configs.disableTypeChecked.languageOptions,
      globals: { ...globals.node },
    },
  },
);
