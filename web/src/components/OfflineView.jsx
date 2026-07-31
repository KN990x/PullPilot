import { RefreshCw, ServerCrash } from "lucide-react";

import AuthLayout from "./AuthLayout";

/**
 * El backend no responde. Antes esto caía en el modo demo y el usuario veía un panel con
 * proyectos falsos (Plex, Pi-hole, Vaultwarden) como si fueran suyos — justo lo que pasa
 * mientras PullPilot se actualiza a sí mismo y su propio contenedor se está recreando.
 */
export default function OfflineView({ t, i18n, onToggleLanguage, onRetry, retrying }) {
  return (
    <AuthLayout
      t={t}
      i18n={i18n}
      onToggleLanguage={onToggleLanguage}
      subtitle={t("offline.subtitle")}
    >
      <div className="flex flex-col items-center gap-4">
        <ServerCrash size={32} className="text-slate-400" />
        <p className="text-sm text-slate-600 text-center">
          {t("auth.backend_unreachable")}
        </p>
        <p className="text-xs text-slate-400 text-center">{t("offline.hint")}</p>
        <button
          type="button"
          onClick={onRetry}
          disabled={retrying}
          className="w-full flex items-center justify-center gap-2 bg-slate-800 text-white text-sm font-medium py-2.5 rounded-lg hover:bg-slate-700 disabled:opacity-60 transition-colors"
        >
          <RefreshCw size={16} className={retrying ? "animate-spin" : undefined} />
          {retrying ? t("offline.retrying") : t("offline.retry")}
        </button>
      </div>
    </AuthLayout>
  );
}
