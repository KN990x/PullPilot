import { useEffect, useRef } from "react";
import { CheckCircle2, Loader2, Save, X } from "lucide-react";

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
  const dialogRef = useRef(null);
  const closeButtonRef = useRef(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const previousFocused = document.activeElement;
    closeButtonRef.current?.focus();

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key !== "Tab" || !dialogRef.current) {
        return;
      }

      const focusableElements = dialogRef.current.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusableElements.length) {
        return;
      }

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      const currentElement = document.activeElement;

      if (event.shiftKey && currentElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && currentElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (previousFocused instanceof HTMLElement) {
        previousFocused.focus();
      }
    };
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-modal-title"
        className="bg-white rounded-xl shadow-2xl w-full max-w-md max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200"
      >
        <div className="p-5 border-b border-slate-200 flex justify-between items-center bg-slate-50">
          <h3 id="account-modal-title" className="font-bold text-lg text-slate-800">
            {t("account.title")}
          </h3>
          <button
            ref={closeButtonRef}
            onClick={onClose}
            aria-label={t("account.cancel")}
            className="text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        <form onSubmit={onSubmit} className="p-6 overflow-y-auto flex flex-col gap-4">
          <p className="text-xs text-slate-500">{t("account.hint_optional")}</p>

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
              <CheckCircle2 size={16} className="shrink-0 mt-0.5" />
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
              minLength={3}
              maxLength={64}
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
              minLength={8}
              maxLength={128}
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
              minLength={8}
              maxLength={128}
              className={INPUT_CLASS}
            />
          </div>

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg font-medium transition-colors h-[46px]"
            >
              {t("account.cancel")}
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 bg-blue-600 hover:bg-blue-700 active:scale-95 disabled:opacity-60 disabled:active:scale-100 text-white p-3 rounded-lg font-medium flex items-center justify-center gap-2 transition-all shadow-sm hover:shadow-md h-[46px]"
            >
              {submitting ? (
                <>
                  <Loader2 size={20} className="animate-spin" />
                  {t("account.submitting")}
                </>
              ) : (
                <>
                  <Save size={20} />
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
