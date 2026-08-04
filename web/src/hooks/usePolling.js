import { useCallback, useEffect, useRef } from "react";

export function usePolling() {
  const pollingRef = useRef(null);
  const intervalRef = useRef(null);
  const callbackRef = useRef(null);
  // The tick fires on a fixed cadence and does not await the callback, so a backend
  // slower than the interval used to stack requests without bound.
  const inFlightRef = useRef(false);

  const startPolling = useCallback((callback, intervalMs = 1000) => {
    callbackRef.current = callback;
    if (pollingRef.current && intervalRef.current === intervalMs) {
      return;
    }
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    intervalRef.current = intervalMs;
    pollingRef.current = setInterval(() => {
      if (typeof callbackRef.current !== "function" || inFlightRef.current) {
        return;
      }
      inFlightRef.current = true;
      Promise.resolve(callbackRef.current()).finally(() => {
        inFlightRef.current = false;
      });
    }, intervalMs);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    intervalRef.current = null;
    callbackRef.current = null;
    inFlightRef.current = false;
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  return { startPolling, stopPolling };
}
