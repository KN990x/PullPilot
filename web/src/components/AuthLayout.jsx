import { Languages, Loader2 } from "lucide-react";

import { normalizeUiLocale } from "../lib/api";
import HeaderButton from "./HeaderButton";

export default function AuthLayout({
  t,
  i18n,
  onToggleLanguage,
  title,
  subtitle,
  loading = false,
  children,
}) {
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-sm animate-in fade-in slide-in-from-bottom-4 duration-300">
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex flex-col items-center gap-2 mb-6">
            <img
              src="/assets/logo.png"
              alt="PullPilot"
              className="w-16 h-16 object-contain"
            />
            <h1 className="text-xl font-bold text-slate-800 tracking-tight">
              {title ?? t("app.title")}
            </h1>
            {subtitle && (
              <p className="text-sm text-slate-500 text-center">{subtitle}</p>
            )}
          </div>

          {loading ? (
            <div className="flex items-center justify-center gap-2 py-6 text-slate-500">
              <Loader2 size={20} className="animate-spin" />
              <span className="text-sm">{t("auth.loading")}</span>
            </div>
          ) : (
            children
          )}
        </div>

        <div className="flex justify-center mt-4">
          <HeaderButton
            variant="lang"
            icon={Languages}
            label={t("app.change_language")}
            onClick={onToggleLanguage}
          >
            <span className="text-xs font-bold">
              {normalizeUiLocale(i18n.language).toUpperCase()}
            </span>
          </HeaderButton>
        </div>
      </div>
    </div>
  );
}
