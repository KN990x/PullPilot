import js from "@eslint/js";
import globals from "globals";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default [
  { ignores: ["dist"] },
  js.configs.recommended,
  // Mind the preset: `configs["recommended-latest"]` is still eslintrc format and eslint
  // 10 rejects it. The flat one lives under `configs.flat` and is an object, not an array.
  reactHooks.configs.flat["recommended-latest"],
  // Same trap: the flat preset is `flatConfigs.recommended`. It caught none of what was
  // already broken by hand — seven unassociated labels in the schedule form, a table with
  // no headers, a progress bar with no role — but it is what stops those coming back.
  jsxA11y.flatConfigs.recommended,
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        sourceType: "module",
      },
    },
    plugins: {
      "react-refresh": reactRefresh,
    },
    rules: {
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // The v7 preset also brings the React Compiler rules. This is plain React 18, and
      // these two reject idiomatic code: App.jsx's fetch-on-mount and the useCallback that
      // reschedules itself. rules-of-hooks and exhaustive-deps stay on. Turning them back
      // on means rewriting the polling cycle.
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/immutability": "off",
    },
  },
];
