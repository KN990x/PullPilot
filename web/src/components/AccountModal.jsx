import { CheckCircle2, Loader2, Save, X } from "lucide-react";

import { useFocusTrap } from "../hooks/useFocusTrap";
import {
  PASSWORD_MAX_LEN,
  PASSWORD_MIN_LEN,
  USERNAME_MAX_LEN,
  USERNAME_MIN_LEN,
} from "../lib/authPolicy";


const INPUT_CLASS =
  "w-full appearance-none bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all text-slate-700";
const LABEL_CLASS = "text-xs font-bold text-slate-500 uppercase tracking-wide";

export default function AccountModal({
  t,
  open,
  username,
  onClose,
  onSubmit,
  submitting,
  error,
  success,
}) {
  const { dialogRef, initialFocusRef } = useFocusTrap({ open, onClose });

  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center z-50 p-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))]"
      role="presentation"
      onClick={(event) => {
        // Only a click on the backdrop itself, so no stopPropagation handler is needed on
        // the dialog. Escape closes it too; the focus trap owns that.
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-modal-title"
        className="bg-white rounded-xl shadow-2xl w-full max-w-md max-h-[min(90dvh,90vh)] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200"
      >
        <div className="p-5 border-b border-slate-200 flex justify-between items-center gap-3 bg-slate-50">
          <h3
            id="account-modal-title"
            className="font-bold text-lg text-slate-800 min-w-0 truncate"
          >
            {t("account.title")}
          </h3>
          <button
            ref={initialFocusRef}
            type="button"
            onClick={onClose}
            aria-label={t("account.close")}
            className="shrink-0 min-h-11 min-w-11 inline-flex items-center justify-center text-slate-500 hover:text-slate-700 transition-colors"
          >
            <X size={24} aria-hidden="true" />
          </button>
        </div>

        <form onSubmit={onSubmit} className="p-6 overflow-y-auto flex flex-col gap-4">
          <p className="text-sm text-slate-600">{t("account.hint_optional")}</p>
          {/* Said up front, not only in the success banner: signing every other device
              out is not something to find out about after the fact. */}
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
            {t("account.warning_signs_out")}
          </p>

          {error && (
            <div
              role="alert"
              className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm"
            >
              {error}
            </div>
          )}

          {success && (
            <div
              role="status"
              className="bg-green-50 border border-green-200 text-green-700 rounded-lg p-3 text-sm flex items-start gap-2"
            >
              <CheckCircle2 size={16} className="shrink-0 mt-0.5" aria-hidden="true" />
              <span>{t("account.success")}</span>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label htmlFor="account-current-password" className={LABEL_CLASS}>
              {t("account.current_password")}
            </label>
            <input
              id="account-current-password"
              name="current_password"
              type="password"
              autoComplete="current-password"
              required
              className={INPUT_CLASS}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="account-username" className={LABEL_CLASS}>
              {t("account.new_username")}
            </label>
            <input
              id="account-username"
              name="username"
              type="text"
              autoComplete="username"
              defaultValue={username ?? ""}
              minLength={USERNAME_MIN_LEN}
              maxLength={USERNAME_MAX_LEN}
              className={INPUT_CLASS}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="account-new-password" className={LABEL_CLASS}>
              {t("account.new_password")}
            </label>
            <input
              id="account-new-password"
              name="new_password"
              type="password"
              autoComplete="new-password"
              minLength={PASSWORD_MIN_LEN}
              maxLength={PASSWORD_MAX_LEN}
              className={INPUT_CLASS}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="account-new-password-confirm" className={LABEL_CLASS}>
              {t("account.new_password_confirm")}
            </label>
            <input
              id="account-new-password-confirm"
              name="new_password_confirm"
              type="password"
              autoComplete="new-password"
              minLength={PASSWORD_MIN_LEN}
              maxLength={PASSWORD_MAX_LEN}
              className={INPUT_CLASS}
            />
          </div>

          <div className="flex flex-col-reverse sm:flex-row gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 min-h-11 px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg font-medium transition-colors"
            >
              {t("account.cancel")}
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 min-h-11 bg-blue-600 hover:bg-blue-700 active:scale-95 disabled:opacity-60 disabled:active:scale-100 text-white p-3 rounded-lg font-medium flex items-center justify-center gap-2 transition-all shadow-sm hover:shadow-md"
            >
              {submitting ? (
                <>
                  <Loader2 size={20} className="animate-spin" aria-hidden="true" />
                  {t("account.submitting")}
                </>
              ) : (
                <>
                  <Save size={20} aria-hidden="true" />
                  {t("account.submit")}
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
