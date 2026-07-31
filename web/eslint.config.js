import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default [
  { ignores: ["dist"] },
  js.configs.recommended,
  // Ojo con el preset: `configs["recommended-latest"]` sigue siendo el formato eslintrc
  // (con `plugins` como array de strings) y eslint 10 lo rechaza. El de flat config vive
  // bajo `configs.flat`, y es un objeto, no un array: se pasa tal cual, sin spread.
  reactHooks.configs.flat["recommended-latest"],
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
      // El preset de la v7 trae además el juego de reglas del React Compiler. Aquí no se
      // usa el compilador (React 18 a pelo), y estas dos rechazan código idiomático:
      //   set-state-in-effect -> el "carga los datos al montar" de App.jsx,
      //   immutability        -> el useCallback que se reprograma a sí mismo (checkProgress).
      // Lo que de verdad protegía antes (rules-of-hooks y exhaustive-deps) sigue activo.
      // Reactivarlas exige rehacer el ciclo de polling; no es parte de este cambio.
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/immutability": "off",
    },
  },
];
