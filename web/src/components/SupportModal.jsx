import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";

import { useFocusTrap } from "../hooks/useFocusTrap";

export const KOFI_EMBED_SRC =
  "https://ko-fi.com/kn990x/?hidefeed=true&widget=true&embed=true&preview=true";

/**
 * Embeds the official Ko-fi widget. The iframe is only mounted while open so we do not
 * hit ko-fi.com in the background.
 */
export default function SupportModal({ t, open, onClose }) {
  const { dialogRef, initialFocusRef } = useFocusTrap({ open, onClose });
  const [iframeLoaded, setIframeLoaded] = useState(false);

  useEffect(() => {
    if (open) {
      setIframeLoaded(false);
    }
  }, [open]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="support-modal-title"
        className="bg-white rounded-xl shadow-2xl w-full max-w-md max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200"
      >
        <div className="p-5 border-b border-slate-200 flex justify-between items-center bg-slate-50 shrink-0">
          <h3 id="support-modal-title" className="font-bold text-lg text-slate-800">
            {t("footer.support_title")}
          </h3>
          <button
            ref={initialFocusRef}
            type="button"
            onClick={onClose}
            aria-label={t("footer.support_close")}
            className="text-slate-500 hover:text-slate-700 transition-colors"
          >
            <X size={24} aria-hidden="true" />
          </button>
        </div>

        <div className="relative overflow-y-auto flex-1 min-h-0">
          {!iframeLoaded && (
            <div
              className="absolute inset-0 flex items-center justify-center bg-slate-50"
              aria-hidden="true"
            >
              <Loader2 className="animate-spin text-slate-400" size={28} />
            </div>
          )}
          <iframe
            id="kofiframe"
            src={KOFI_EMBED_SRC}
            title={t("footer.support_iframe_title")}
            style={{
              border: "none",
              width: "100%",
              padding: "4px",
              background: "#f9f9f9",
              display: "block",
            }}
            height="712"
            onLoad={() => setIframeLoaded(true)}
          />
        </div>
      </div>
    </div>
  );
}
