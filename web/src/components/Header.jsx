import { AlertTriangle, Languages, LogOut, UserCircle } from "lucide-react";

import { normalizeUiLocale } from "../lib/api";
import HeaderButton from "./HeaderButton";

export default function Header({
  t,
  i18n,
  isMockMode,
  activeTab,
  onChangeTab,
  onOpenAccount,
  onToggleLanguage,
  onLogout,
}) {
  return (
    <>
      <header className="bg-white border-b border-slate-200 px-4 py-3 md:px-6 md:py-4 flex items-center justify-between sticky top-0 z-10 shadow-sm">
        <div className="flex items-center gap-3">
          <img
            src="/assets/logo.png"
            alt=""
            aria-hidden="true"
            className="w-8 h-8 md:w-10 md:h-10 object-contain"
          />

          <div>
            <h1 className="text-xl font-bold text-slate-800 tracking-tight">{t("app.title")}</h1>
            <p className="text-xs text-slate-500 font-medium hidden md:block">{t("app.subtitle")}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 md:gap-4">
          {isMockMode && (
            /* Visible on a phone too: hidden behind lg: the badge defeated its own
               purpose, leaving no sign that the projects on screen were invented. */
            <span className="inline-flex items-center gap-1 text-xs font-mono bg-yellow-100 text-yellow-800 px-2 py-1 rounded border border-yellow-200">
              <AlertTriangle size={12} aria-hidden="true" />
              <span className="hidden lg:inline">{t("app.demo_mode")}</span>
              <span className="lg:hidden">{t("app.demo_mode_short")}</span>
            </span>
          )}

          {/* aria-current, not role="tablist": the active tab was conveyed by background
              colour alone and no assistive tech could tell which view was showing. A real
              tablist also promises arrow-key navigation, which these buttons do not do. */}
          <nav
            aria-label={t("nav.sections")}
            className="hidden sm:flex gap-1 bg-slate-100 p-1 rounded-lg"
          >
            {["dashboard", "schedule", "history"].map((tab) => (
              <button
                key={tab}
                type="button"
                aria-current={activeTab === tab ? "page" : undefined}
                onClick={() => onChangeTab(tab)}
                className={`px-3 py-1.5 md:px-4 md:py-2 rounded-md text-xs md:text-sm font-medium transition-all ${
                  activeTab === tab
                    ? "bg-white text-blue-600 shadow-sm"
                    : "text-slate-600 hover:text-slate-800"
                }`}
              >
                {t(`nav.${tab}`)}
              </button>
            ))}
          </nav>

          {onOpenAccount && (
            <HeaderButton
              variant="account"
              icon={UserCircle}
              label={t("account.open")}
              onClick={onOpenAccount}
            />
          )}

          <HeaderButton
            variant="lang"
            icon={Languages}
            label={t("app.change_language")}
            onClick={onToggleLanguage}
          >
            {/* Normalised: the browser detector returns "es-ES", which would render as
                "ES-ES" instead of the two-letter code the pill is designed around. */}
            <span className="text-xs font-bold">
              {normalizeUiLocale(i18n.language).toUpperCase()}
            </span>
          </HeaderButton>

          <HeaderButton
            variant="logout"
            icon={LogOut}
            label={t("auth.logout")}
            onClick={onLogout}
          />
        </div>
      </header>

      {/* No hardcoded top-[60px]: the header height is content-derived, so the magic
          number left a sliver of scrolling content showing through the seam and broke
          outright at larger font sizes. */}
      <div className="sm:hidden px-4 py-2 bg-white border-b border-slate-200 sticky top-0 z-10">
        <nav
          aria-label={t("nav.sections")}
          className="flex gap-1 bg-slate-100 p-1 rounded-lg justify-between"
        >
          {["dashboard", "schedule", "history"].map((tab) => (
            <button
              key={tab}
              type="button"
              aria-current={activeTab === tab ? "page" : undefined}
              onClick={() => onChangeTab(tab)}
              className={`flex-1 px-2 py-1.5 rounded-md text-xs font-medium transition-all ${
                activeTab === tab
                  ? "bg-white text-blue-600 shadow-sm"
                  : "text-slate-600 hover:text-slate-800"
              }`}
            >
              {t(`nav.${tab}`)}
            </button>
          ))}
        </nav>
      </div>
    </>
  );
}
