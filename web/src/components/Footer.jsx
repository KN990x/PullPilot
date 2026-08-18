import { useCallback, useState } from "react";

import KofiModal from "./KofiModal";

export const SITE_URL = "https://kn990x.dev";

/**
 * Ko-fi cup mark, in brand colours so the CTA still reads as Ko-fi now that the button
 * itself is a plain secondary button rather than a cyan pill.
 */
function KofiCupMark() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" className="shrink-0">
      <path
        fill="#FF5E5B"
        d="M12 2.1c-.42 0-.8.22-1.02.56-.22-.34-.6-.56-1.02-.56-.84 0-1.46.78-1.32 1.62.14.92 1.08 1.5 2.08 2.1L12 6.7l1.28-.88c1-.6 1.94-1.18 2.08-2.1.14-.84-.48-1.62-1.32-1.62-.42 0-.8.22-1.02.56C12.8 2.32 12.42 2.1 12 2.1Z"
      />
      <path
        fill="#13C3FF"
        d="M5.4 9.1c0-.6.5-1.1 1.1-1.1h9.2c.6 0 1.1.5 1.1 1.1v6.2A4.2 4.2 0 0 1 12.6 19.6H9.7A4.2 4.2 0 0 1 5.4 15.3V9.1Z"
      />
      <path
        fill="#13C3FF"
        d="M16.8 10.35h.85a2.5 2.5 0 1 1 0 5h-.5v-1.35h.5a1.15 1.15 0 1 0 0-2.3h-.85v-1.35Z"
      />
    </svg>
  );
}

export default function Footer({ t }) {
  const [supportOpen, setSupportOpen] = useState(false);
  // Stable by contract, not by taste: App re-renders once a second during a global update
  // and drags the footer with it, which would re-run the dialog's focus trap effect.
  const closeSupport = useCallback(() => setSupportOpen(false), []);

  return (
    <footer className="bg-white border-t border-slate-200 mt-auto pb-[env(safe-area-inset-bottom)]">
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-[22px] flex flex-wrap justify-between items-center gap-[14px]">
        <p className="text-[13px] font-medium text-slate-600">
          &copy; {new Date().getFullYear()}{" "}
          <a
            href={SITE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
          >
            KN990x
          </a>
        </p>

        <button
          type="button"
          onClick={() => setSupportOpen(true)}
          aria-haspopup="dialog"
          className="inline-flex items-center gap-2 min-h-11 px-4 rounded-lg bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 text-[13px] font-bold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
        >
          <KofiCupMark />
          {t("footer.support")}
        </button>
      </div>

      <KofiModal t={t} open={supportOpen} onClose={closeSupport} />
    </footer>
  );
}
