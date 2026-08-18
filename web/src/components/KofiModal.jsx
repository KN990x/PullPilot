import { CloudOff, ExternalLink, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { useFocusTrap } from "../hooks/useFocusTrap";

// Lives here rather than in Footer, which imports this module: the fallback link is the
// only thing left that still points at the Ko-fi page.
export const KOFI_URL = "https://ko-fi.com/kn990x";

// Ko-fi's own embed URL, parameters included. Do not tidy it up: `widget`/`embed` are what
// make the page frameable at all, and `hidefeed` is what keeps it down to the donation form.
export const KOFI_EMBED_URL =
  "https://ko-fi.com/kn990x/?hidefeed=true&widget=true&embed=true&preview=true";

// Matches the `duration-200` on the exit animation. A timer rather than `animationend`
// because jsdom never fires that event, which would leave the modal stuck open in tests.
export const EXIT_MS = 250;

// How long the skeleton waits before giving up. Generous: Ko-fi behind a slow homelab
// uplink is not the same thing as Ko-fi being blocked, and crying wolf is worse than a
// few extra seconds of skeleton.
export const LOAD_TIMEOUT_MS = 8000;

/**
 * A cross-origin iframe never reports its own failure: `error` does not fire, and an ad
 * blocker cancels the request quietly, leaving the frame parked on the about:blank it was
 * born with. That blank document is same-origin, so being *able* to read it is the tell
 * that the real page never arrived.
 *
 * Only the positive verdict is trusted here. A same-origin document also means "still on
 * about:blank", which is a normal intermediate state, so it is ignored and the timeout is
 * left to make the call.
 */
function hasCrossOriginDocument(frame) {
  try {
    return frame.contentDocument === null;
  } catch {
    // A SecurityError is the browser refusing to hand over a foreign document, which is
    // exactly the success case.
    return true;
  }
}

/** Stand-in for the Ko-fi form, shaped like it so the panel does not jump when it lands. */
function KofiSkeleton({ t }) {
  return (
    <div className="p-6" role="status">
      <span className="sr-only">{t("footer.support_loading")}</span>
      <div className="animate-pulse motion-reduce:animate-none space-y-4" aria-hidden="true">
        <div className="h-16 w-16 rounded-full bg-slate-200 mx-auto" />
        <div className="h-4 w-48 bg-slate-200 rounded mx-auto" />
        <div className="h-11 bg-slate-200 rounded-full" />
        <div className="h-11 bg-slate-200 rounded-lg" />
        <div className="h-11 bg-slate-200 rounded-lg" />
        <div className="h-24 bg-slate-200 rounded-lg" />
        <div className="h-12 bg-slate-300 rounded-full" />
      </div>
    </div>
  );
}

/** The emergency exit: what the user sees when the widget is never going to show up. */
function KofiUnavailable({ t, onRetry }) {
  return (
    <div className="p-6 flex flex-col items-center text-center gap-3">
      <CloudOff size={28} className="text-slate-400" aria-hidden="true" />
      <h4 className="font-bold text-slate-800">{t("footer.support_blocked_title")}</h4>
      <p className="text-sm text-slate-600 max-w-sm">{t("footer.support_blocked_hint")}</p>
      <div className="flex flex-col-reverse sm:flex-row gap-2 pt-1 w-full sm:w-auto">
        <button
          type="button"
          onClick={onRetry}
          className="w-full sm:w-auto min-h-11 px-4 py-2 bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 rounded-lg font-medium transition-colors"
        >
          {t("offline.retry")}
        </button>
        <a
          href={KOFI_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="w-full sm:w-auto min-h-11 inline-flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
        >
          {t("footer.support_open")}
          <ExternalLink size={16} aria-hidden="true" />
        </a>
      </div>
    </div>
  );
}

/**
 * The Ko-fi donation widget, in a dialog instead of a new tab.
 *
 * Two bits of state that are not one: `mounted` is latched on the first open and never
 * released, so the iframe is created once — no request to ko-fi.com on page load, and no
 * reload of the widget every time the dialog is reopened. `visible` covers the exit
 * animation, during which the panel is still on screen but `open` is already false.
 */
export default function KofiModal({ t, open, onClose }) {
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  const [status, setStatus] = useState("loading");
  // Bumped by the retry button to remount the iframe. The URL never changes; a fresh
  // element is what makes the browser ask again.
  const [attempt, setAttempt] = useState(0);
  // The trap and the lock key on `open`, not `visible`: focus goes back to the footer
  // button as soon as the user asks to close, without waiting out the animation.
  const { dialogRef, initialFocusRef } = useFocusTrap({ open, onClose });
  useBodyScrollLock(open);

  useEffect(() => {
    if (open) {
      setMounted(true);
      setVisible(true);
      return undefined;
    }

    if (!visible) {
      return undefined;
    }

    const timer = setTimeout(() => setVisible(false), EXIT_MS);
    return () => clearTimeout(timer);
  }, [open, visible]);

  useEffect(() => {
    if (!mounted || status !== "loading") {
      return undefined;
    }

    // Only catches a browser that already knows it is offline; a homelab with LAN but no
    // uplink still reports `true`, which is what the timeout is for.
    if (!navigator.onLine) {
      setStatus("failed");
      return undefined;
    }

    const timer = setTimeout(() => setStatus("failed"), LOAD_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [attempt, mounted, status]);

  if (!mounted) {
    return null;
  }

  return (
    <div
      // `hidden` is both the attribute and the class on purpose: the attribute is what
      // takes the dialog out of the accessibility tree, the class is what beats the
      // `flex` that would otherwise still apply.
      hidden={!visible}
      className={`fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm items-end sm:items-center justify-center p-0 sm:p-4 sm:pt-[max(1rem,env(safe-area-inset-top))] sm:pb-[max(1rem,env(safe-area-inset-bottom))] motion-reduce:animate-none ${
        visible ? "flex" : "hidden"
      } ${open ? "animate-in fade-in duration-300" : "animate-out fade-out duration-200"}`}
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
        aria-labelledby="kofi-modal-title"
        className={`bg-white shadow-2xl w-full sm:max-w-lg rounded-t-2xl sm:rounded-xl flex flex-col overflow-hidden max-h-[92dvh] sm:max-h-[min(90dvh,90vh)] motion-reduce:animate-none ${
          open
            ? "animate-in slide-in-from-bottom-4 sm:zoom-in-95 duration-300"
            : "animate-out slide-out-to-bottom-4 sm:zoom-out-95 duration-200"
        }`}
      >
        <div className="p-5 border-b border-slate-200 flex justify-between items-center gap-3 bg-slate-50">
          <h3 id="kofi-modal-title" className="font-bold text-lg text-slate-800 min-w-0 truncate">
            {t("footer.support")}
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
        <div className="relative overflow-y-auto min-h-0 flex-1 bg-slate-50">
          {status !== "failed" && (
            <iframe
              key={attempt}
              id="kofiframe"
              src={KOFI_EMBED_URL}
              title={t("footer.support")}
              height="712"
              onLoad={(event) => {
                if (hasCrossOriginDocument(event.currentTarget)) {
                  setStatus("ready");
                }
              }}
              // While loading it is taken out of the flow rather than hidden: a
              // `display: none` frame would still fetch, but the skeleton needs the space.
              className={`w-full border-0 p-1 bg-slate-50 ${
                status === "ready" ? "block" : "absolute inset-0 opacity-0 pointer-events-none"
              }`}
            />
          )}
          {status === "loading" && <KofiSkeleton t={t} />}
          {status === "failed" && (
            <KofiUnavailable
              t={t}
              onRetry={() => {
                setAttempt((n) => n + 1);
                setStatus("loading");
              }}
            />
          )}
        </div>
        {/* Second exit for the case nothing detects: a widget that lands, renders, and is
            still useless. Dropped once the panel is already showing the failure block,
            which offers the same link with more prominence. */}
        <div
          hidden={status === "failed"}
          className="p-4 border-t border-slate-200 bg-slate-50 pb-[max(1rem,env(safe-area-inset-bottom))] sm:pb-4"
        >
          <a
            href={KOFI_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 transition-colors"
          >
            {t("footer.support_fallback")}
            <ExternalLink size={14} aria-hidden="true" />
          </a>
        </div>
      </div>
    </div>
  );
}
