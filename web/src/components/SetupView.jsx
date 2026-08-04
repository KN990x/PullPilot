import { Loader2, ShieldCheck } from "lucide-react";

import AuthLayout from "./AuthLayout";

const INPUT_CLASS =
  "w-full appearance-none bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all text-slate-700";
const LABEL_CLASS = "text-xs font-bold text-slate-500 uppercase tracking-wide";
// slate-600, not slate-400: hint text on white at slate-400 is ~2.6:1, well under the
// 4.5:1 WCAG AA needs, and these hints carry the password rules.
const HINT_CLASS = "text-xs text-slate-600";

export default function SetupView({
  t,
  i18n,
  onToggleLanguage,
  onSubmit,
  submitting,
  error,
}) {
  return (
    <AuthLayout
      t={t}
      i18n={i18n}
      onToggleLanguage={onToggleLanguage}
      title={t("setup.title")}
      subtitle={t("setup.subtitle")}
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <p className="text-sm text-slate-600 bg-blue-50 border border-blue-100 rounded-lg p-3">
          {t("setup.intro")}
        </p>

        {error && (
          <div
            role="alert"
            className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm"
          >
            {error}
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <label htmlFor="setup-username" className={LABEL_CLASS}>
            {t("setup.username")}
          </label>
          <input
            id="setup-username"
            name="username"
            type="text"
            autoComplete="username"
            // eslint-disable-next-line jsx-a11y/no-autofocus -- single-purpose full-screen form, this field is the only thing on it
            autoFocus
            required
            minLength={3}
            maxLength={64}
            className={INPUT_CLASS}
          />
          <span className={HINT_CLASS}>{t("setup.username_hint")}</span>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="setup-password" className={LABEL_CLASS}>
            {t("setup.password")}
          </label>
          <input
            id="setup-password"
            name="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            maxLength={128}
            className={INPUT_CLASS}
          />
          <span className={HINT_CLASS}>{t("setup.password_hint")}</span>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="setup-password-confirm" className={LABEL_CLASS}>
            {t("setup.password_confirm")}
          </label>
          <input
            id="setup-password-confirm"
            name="password_confirm"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            maxLength={128}
            className={INPUT_CLASS}
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="bg-blue-600 hover:bg-blue-700 active:scale-95 disabled:opacity-60 disabled:active:scale-100 text-white p-3 rounded-lg font-medium flex items-center justify-center gap-2 transition-all shadow-sm hover:shadow-md h-[46px]"
        >
          {submitting ? (
            <>
              <Loader2 size={20} className="animate-spin" />
              {t("setup.submitting")}
            </>
          ) : (
            <>
              <ShieldCheck size={20} />
              {t("setup.submit")}
            </>
          )}
        </button>
      </form>
    </AuthLayout>
  );
}
