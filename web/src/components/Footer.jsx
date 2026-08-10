import { useCallback, useState } from "react";
import { Coffee } from "lucide-react";

import SupportModal from "./SupportModal";

/**
 * Support CTA uses the same blue pill family as the header actions. Opens the official
 * Ko-fi embed in a modal instead of navigating away.
 */
export default function Footer({ t }) {
  const [supportOpen, setSupportOpen] = useState(false);
  // Stable for useFocusTrap: an inline arrow would re-run the trap effect every render.
  const closeSupport = useCallback(() => setSupportOpen(false), []);

  return (
    <footer className="bg-white border-t border-slate-200 mt-auto">
      <div className="max-w-7xl mx-auto px-6 py-[22px] flex flex-wrap justify-between items-center gap-[14px]">
        <p className="text-[13px] font-medium text-slate-600">
          &copy; {new Date().getFullYear()}{" "}
          <a
            href="https://github.com/KN990x"
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
          className="inline-flex items-center gap-[7px] px-[15px] py-2 rounded-[10px] border border-blue-600/30 bg-blue-600/[0.08] text-blue-600 text-[13px] font-semibold transition-colors hover:bg-blue-600 hover:border-blue-600 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
        >
          <Coffee size={15} aria-hidden="true" />
          {t("footer.tip_me")}
        </button>
      </div>

      <SupportModal t={t} open={supportOpen} onClose={closeSupport} />
    </footer>
  );
}
