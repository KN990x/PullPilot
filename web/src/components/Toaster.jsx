import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";

const TONES = {
  error: {
    icon: AlertTriangle,
    className: "border-red-200 bg-red-50 text-red-800",
    iconClass: "text-red-500",
  },
  success: {
    icon: CheckCircle2,
    className: "border-green-200 bg-green-50 text-green-800",
    iconClass: "text-green-600",
  },
  info: {
    icon: Info,
    className: "border-blue-200 bg-blue-50 text-blue-800",
    iconClass: "text-blue-600",
  },
};

export default function Toaster({ t, toasts, onDismiss }) {
  return (
    // Always mounted, never conditionally rendered: a live region has to exist before
    // the message lands in it or screen readers do not announce it.
    <div
      role="status"
      aria-live="polite"
      aria-atomic="false"
      className="fixed z-50 bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 -translate-x-1/2 w-[calc(100%-2rem)] max-w-sm flex flex-col gap-2 pointer-events-none"
    >
      {toasts.map((toast) => {
        const tone = TONES[toast.tone] ?? TONES.error;
        const Icon = tone.icon;
        return (
          <div
            key={toast.id}
            className={`pointer-events-auto flex items-start gap-3 rounded-lg border px-4 py-3 shadow-md animate-in fade-in slide-in-from-bottom-2 duration-200 ${tone.className}`}
          >
            <Icon size={18} className={`shrink-0 mt-0.5 ${tone.iconClass}`} aria-hidden="true" />
            <p className="text-sm flex-1 leading-snug">
              {t(toast.messageKey, toast.options)}
            </p>
            <button
              type="button"
              onClick={() => onDismiss(toast.id)}
              aria-label={t("common.dismiss")}
              title={t("common.dismiss")}
              className="shrink-0 -mr-1 -mt-0.5 p-1 rounded hover:bg-black/5 transition-colors"
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
