import { useEffect, useRef } from "react";

// `:not([disabled])` matters: the submit button is the last node in the account dialog and
// it is disabled while submitting. A disabled button can never hold focus, so the
// "focus is on the last element" test never matched and Tab walked out of the dialog.
const FOCUSABLE = [
  "button:not([disabled])",
  "[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

/**
 * Trap Tab inside a dialog, close it on Escape, and restore focus on the way out.
 *
 * `onClose` must be referentially stable — wrap it in useCallback. When it was an inline
 * arrow, every parent render re-ran this effect, and during a global update the dashboard
 * re-renders once a second: focus jumped back to the close button mid-keystroke, and the
 * "previously focused" element was re-captured as the close button, so restoring focus
 * afterwards stopped working too.
 */
export function useFocusTrap({ open, onClose }) {
  const dialogRef = useRef(null);
  const initialFocusRef = useRef(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const previousFocused = document.activeElement;
    initialFocusRef.current?.focus();

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key !== "Tab" || !dialogRef.current) {
        return;
      }

      // No visibility filtering: `offsetParent` is null for anything inside a `fixed`
      // container — which every one of these dialogs is — and always null under jsdom.
      // The selector already drops disabled controls, and the browser skips genuinely
      // hidden ones on its own; only the wrap-around at the two ends is ours to manage.
      const focusable = Array.from(dialogRef.current.querySelectorAll(FOCUSABLE));
      if (!focusable.length) {
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const current = document.activeElement;

      // `!focusable.includes(current)` covers focus having escaped already, e.g. because
      // the element holding it was disabled after it was focused.
      if (event.shiftKey && (current === first || !focusable.includes(current))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (current === last || !focusable.includes(current))) {
        event.preventDefault();
        first.focus();
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

  return { dialogRef, initialFocusRef };
}
