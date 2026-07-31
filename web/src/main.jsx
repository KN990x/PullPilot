import React from "react";
import ReactDOM from "react-dom/client";
import { registerSW } from "virtual:pwa-register";

import App from "./App.jsx";
import "./index.css";
import i18n from "./i18n";

const updateSW = registerSW({
  onNeedRefresh() {
    if (confirm(i18n.t("pwa.update_available"))) {
      updateSW(true);
    }
  },
  onOfflineReady() {
    console.log("App ready to work offline");
  },
});

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
