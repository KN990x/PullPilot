import { Loader2, LogIn } from "lucide-react";

import AuthLayout from "./AuthLayout";
import { PASSWORD_MAX_LEN, USERNAME_MAX_LEN } from "../lib/authPolicy";

const INPUT_CLASS =
  "w-full appearance-none bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all text-slate-700";
const LABEL_CLASS = "text-xs font-bold text-slate-500 uppercase tracking-wide";

export default function LoginView({
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
      title={t("auth.login_title")}
      subtitle={t("auth.login_subtitle")}
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {error && (
          <div
            role="alert"
            className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm"
          >
            {error}
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <label htmlFor="login-username" className={LABEL_CLASS}>
            {t("auth.username")}
          </label>
          <input
            id="login-username"
            name="username"
            type="text"
            autoComplete="username"
            // eslint-disable-next-line jsx-a11y/no-autofocus -- single-purpose full-screen form, this field is the only thing on it
            autoFocus
            required
            maxLength={USERNAME_MAX_LEN}
            className={INPUT_CLASS}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="login-password" className={LABEL_CLASS}>
            {t("auth.password")}
          </label>
          <input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={PASSWORD_MAX_LEN}
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
              {t("auth.submitting")}
            </>
          ) : (
            <>
              <LogIn size={20} />
              {t("auth.submit")}
            </>
          )}
        </button>
      </form>
    </AuthLayout>
  );
}
