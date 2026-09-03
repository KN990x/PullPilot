import { useCallback, useEffect, useRef, useState } from "react";

const DEFAULT_TTL_MS = 6000;

function sameToast(toast, messageKey, options) {
  return (
    toast.messageKey === messageKey &&
    JSON.stringify(toast.options) === JSON.stringify(options)
  );
}

/**
 * Non-blocking notifications, replacing the native `alert()` this app used everywhere.
 *
 * `alert()` blocks the thread while the dashboard is polling, is unstyled, unreadable on
 * a phone, and can stack two deep when two loads fail at once. It also cannot be read by
 * assistive tech as app content; the Toaster that renders these is an aria-live region.
 */
export function useToasts() {
  const [toasts, setToasts] = useState([]);
  const timers = useRef(new Map());
  const nextId = useRef(0);

  const dismissToast = useCallback((id) => {
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  /**
   * `messageKey` is an i18n key, not a translated string. Two reasons: the Toaster
   * translates at render time so open toasts follow a language switch, and it keeps `t`
   * out of the dependency arrays of the data loaders — `t` changes identity on every
   * language change, which used to re-run a full project scan.
   */
  const pushToast = useCallback(
    (messageKey, tone = "error", options = undefined, ttl = DEFAULT_TTL_MS) => {
      const id = nextId.current++;
      setToasts((prev) => {
        // The same message twice in a row is one event to the reader, not two.
        // Options are part of the identity: two `alerts.update_ok` for different stacks
        // are two events, and collapsing them on the key alone hid every name but the last.
        const withoutDuplicate = prev.filter((toast) => {
          if (!sameToast(toast, messageKey, options)) {
            return true;
          }
          const timer = timers.current.get(toast.id);
          if (timer) {
            clearTimeout(timer);
            timers.current.delete(toast.id);
          }
          return false;
        });
        return [...withoutDuplicate, { id, messageKey, tone, options }];
      });
      timers.current.set(
        id,
        setTimeout(() => dismissToast(id), ttl)
      );
      return id;
    },
    [dismissToast]
  );

  // Every pending timer, not just the visible ones: an unmount mid-countdown otherwise
  // sets state on a component that is gone.
  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach(clearTimeout);
      pending.clear();
    };
  }, []);

  return { toasts, pushToast, dismissToast };
}
