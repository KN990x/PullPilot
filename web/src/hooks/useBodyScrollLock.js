import { useEffect } from "react";

/**
 * Freeze the page behind a modal while it is open.
 *
 * The previous value is restored rather than cleared: the app never sets it today, but
 * clearing would silently undo whatever a future caller left there. iOS Safari still
 * rubber-bands past the lock; nothing short of `position: fixed` on the body stops that,
 * and that costs the scroll position.
 */
export function useBodyScrollLock(locked) {
  useEffect(() => {
    if (!locked) {
      return undefined;
    }

    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [locked]);
}
