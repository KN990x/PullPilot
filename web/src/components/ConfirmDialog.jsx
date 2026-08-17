import { AlertTriangle } from "lucide-react";

import { useFocusTrap } from "../hooks/useFocusTrap";

/**
 * Replaces the native `confirm()` on the two destructive actions.
 *
 * `confirm()` blocks the polling thread, cannot say *which* schedule or *how many*
 * projects, and looks nothing like the rest of the app. `details` is where that context
 * goes. Focus starts on Cancel so Enter never means "yes" by accident.
 */
export default function ConfirmDialog({
  t,
  open,
  title,
  message,
  details,
  confirmLabel,
  onConfirm,
  onCancel,
}) {
  const { dialogRef, initialFocusRef } = useFocusTrap({ open, onClose: onCancel });

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
          onCancel();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-message"
        className="bg-white rounded-xl shadow-2xl w-full max-w-md max-h-[min(90dvh,90vh)] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200"
      >
        <div className="p-6 flex gap-4 overflow-y-auto min-w-0">
          <AlertTriangle
            size={24}
            className="text-amber-500 shrink-0 mt-0.5"
            aria-hidden="true"
          />
          <div className="space-y-2 min-w-0">
            <h3 id="confirm-dialog-title" className="font-bold text-slate-800">
              {title}
            </h3>
            <p id="confirm-dialog-message" className="text-sm text-slate-600">
              {message}
            </p>
            {details && (
              <p className="text-sm font-mono bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-700 break-all">
                {details}
              </p>
            )}
          </div>
        </div>
        <div className="p-4 border-t border-slate-200 bg-slate-50 flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
          <button
            ref={initialFocusRef}
            type="button"
            onClick={onCancel}
            className="w-full sm:w-auto min-h-11 px-4 py-2 bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 rounded-lg font-medium transition-colors"
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="w-full sm:w-auto min-h-11 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors"
          >
            {confirmLabel ?? t("common.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
