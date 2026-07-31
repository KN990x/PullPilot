import { AlertTriangle, Languages, LogOut, UserCircle } from "lucide-react";

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
            alt="PullPilot Logo"
            className="w-8 h-8 md:w-10 md:h-10 object-contain"
          />

          <div>
            <h1 className="text-xl font-bold text-slate-800 tracking-tight">{t("app.title")}</h1>
            <p className="text-xs text-slate-500 font-medium hidden md:block">{t("app.subtitle")}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 md:gap-4">
          {isMockMode && (
            <span className="hidden lg:inline-flex items-center gap-1 text-xs font-mono bg-yellow-100 text-yellow-800 px-2 py-1 rounded border border-yellow-200">
              <AlertTriangle size={12} /> {t("app.demo_mode")}
            </span>
          )}

          {onOpenAccount && (
            <button
              onClick={onOpenAccount}
              className="p-2 text-slate-500 hover:text-blue-600 hover:bg-slate-100 rounded-lg transition-colors flex items-center gap-1"
              title={t("account.open")}
              aria-label={t("account.open")}
            >
              <UserCircle size={20} />
            </button>
          )}

          <button
            onClick={onToggleLanguage}
            className="p-2 text-slate-500 hover:text-blue-600 hover:bg-slate-100 rounded-lg transition-colors flex items-center gap-1"
            title={t("app.change_language")}
            aria-label={t("app.change_language")}
          >
            <Languages size={20} />
            <span className="text-xs font-bold">{i18n.language.toUpperCase()}</span>
          </button>

          <button
            onClick={onLogout}
            className="p-2 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors flex items-center gap-1"
            title={t("auth.logout")}
            aria-label={t("auth.logout")}
          >
            <LogOut size={20} />
          </button>

          <nav className="hidden sm:flex gap-1 bg-slate-100 p-1 rounded-lg">
            {["dashboard", "schedule", "history"].map((tab) => (
              <button
                key={tab}
                onClick={() => onChangeTab(tab)}
                className={`px-3 py-1.5 md:px-4 md:py-2 rounded-md text-xs md:text-sm font-medium transition-all ${
                  activeTab === tab
                    ? "bg-white text-blue-600 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {t(`nav.${tab}`)}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <div className="sm:hidden px-4 py-2 bg-white border-b border-slate-200 sticky top-[60px] z-10">
        <nav className="flex gap-1 bg-slate-100 p-1 rounded-lg justify-between">
          {["dashboard", "schedule", "history"].map((tab) => (
            <button
              key={tab}
              onClick={() => onChangeTab(tab)}
              className={`flex-1 px-2 py-1.5 rounded-md text-xs font-medium transition-all ${
                activeTab === tab
                  ? "bg-white text-blue-600 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
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
