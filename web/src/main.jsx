import React from "react";
import ReactDOM from "react-dom/client";
import { registerSW } from "virtual:pwa-register";

import App from "./App.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import "./index.css";
import i18n from "./i18n";

// The one confirm() left, and deliberately: it fires from outside the React tree, before
// the app may even have mounted, so there is no dialog component available to it.
const updateSW = registerSW({
  onNeedRefresh() {
    if (confirm(i18n.t("pwa.update_available"))) {
      updateSW(true);
    }
  },
  onOfflineReady() {
    console.info("App ready to work offline");
  },
});

// The document language follows i18n from inside App; set once here so the very first
// paint is already correct rather than whatever index.html hardcodes.
document.documentElement.lang = i18n.language?.split("-")[0] === "en" ? "en" : "es";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
