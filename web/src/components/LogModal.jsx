import { Copy, X } from "lucide-react";

import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { useFocusTrap } from "../hooks/useFocusTrap";

function safeStringifyDetails(details) {
  try {
    return JSON.stringify(JSON.parse(details), null, 2);
  } catch {
    return String(details ?? "");
  }
}

export default function LogModal({ t, selectedLog, onClose, onCopied }) {
  const { dialogRef, initialFocusRef } = useFocusTrap({
    open: Boolean(selectedLog),
    onClose,
  });
  useBodyScrollLock(Boolean(selectedLog));

  if (!selectedLog) {
    return null;
  }

  const body = safeStringifyDetails(selectedLog.details);

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(body);
      onCopied?.(t("modal.copied"));
    } catch {
      onCopied?.(t("modal.copy_failed"), "error");
    }
  };

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
        aria-labelledby="log-modal-title"
        className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[min(80dvh,80vh)] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200"
      >
        <div className="p-5 border-b border-slate-200 flex justify-between items-center gap-3 bg-slate-50">
          <h3
            id="log-modal-title"
            className="font-bold text-lg text-slate-800 min-w-0 truncate"
          >
            {t("modal.title", { id: selectedLog.id })}
          </h3>
          <button
            ref={initialFocusRef}
            type="button"
            onClick={onClose}
            aria-label={t("modal.close")}
            className="shrink-0 min-h-11 min-w-11 inline-flex items-center justify-center text-slate-500 hover:text-slate-700 transition-colors"
          >
            <X size={24} aria-hidden="true" />
          </button>
        </div>
        <div className="p-4 md:p-6 overflow-y-auto font-mono text-xs bg-slate-900 text-slate-300 min-h-0 flex-1">
          <pre className="whitespace-pre-wrap break-words">{body}</pre>
        </div>
        <div className="p-4 border-t border-slate-200 bg-slate-50 flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
          <button
            type="button"
            onClick={copyToClipboard}
            className="w-full sm:w-auto min-h-11 inline-flex items-center justify-center gap-2 px-4 py-2 bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 rounded-lg font-medium transition-colors"
          >
            <Copy size={16} aria-hidden="true" /> {t("modal.copy")}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="w-full sm:w-auto min-h-11 px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg font-medium transition-colors"
          >
            {t("modal.close")}
          </button>
        </div>
      </div>
    </div>
  );
}
