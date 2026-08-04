import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePolling } from "./usePolling";

/**
 * Advance one interval and let the in-flight promise settle.
 *
 * The tick marks itself busy and clears that in a `.finally()`, i.e. a microtask. A real
 * browser drains those between two interval firings; `advanceTimersByTime(3000)` runs all
 * three in one synchronous task, so without an await in between only the first would run.
 */
async function tickOnce(ms = 1000) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
  });
}

describe("usePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("calls the callback on every tick until stopped", async () => {
    const { result } = renderHook(() => usePolling());
    const tick = vi.fn();

    act(() => result.current.startPolling(tick, 1000));
    await tickOnce();
    await tickOnce();
    await tickOnce();
    expect(tick).toHaveBeenCalledTimes(3);

    act(() => result.current.stopPolling());
    await tickOnce(3000);
    expect(tick).toHaveBeenCalledTimes(3);
  });

  it("swaps the callback without restarting the interval", async () => {
    // The progress cycle re-registers itself on every tick; restarting the timer each
    // time would keep pushing the next call one full interval away.
    const { result } = renderHook(() => usePolling());
    const first = vi.fn();
    const second = vi.fn();

    act(() => result.current.startPolling(first, 1000));
    await tickOnce();
    act(() => result.current.startPolling(second, 1000));
    await tickOnce();

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("restarts when the interval itself changes", async () => {
    const { result } = renderHook(() => usePolling());
    const tick = vi.fn();

    act(() => result.current.startPolling(tick, 1000));
    act(() => result.current.startPolling(tick, 5000));
    await tickOnce();
    expect(tick).not.toHaveBeenCalled();

    await tickOnce(4000);
    expect(tick).toHaveBeenCalledTimes(1);
  });

  it("stops on unmount so a closed tab does not keep firing", async () => {
    const { result, unmount } = renderHook(() => usePolling());
    const tick = vi.fn();

    act(() => result.current.startPolling(tick, 1000));
    unmount();
    await tickOnce(5000);

    expect(tick).not.toHaveBeenCalled();
  });

  it("skips a tick while the previous call is still in flight", async () => {
    // A backend slower than the interval used to stack requests without bound: the tick
    // fired on a fixed cadence and threw the returned promise away.
    const { result } = renderHook(() => usePolling());
    let release;
    const slow = vi.fn(
      () =>
        new Promise((resolve) => {
          release = resolve;
        })
    );

    act(() => result.current.startPolling(slow, 1000));
    await tickOnce();
    await tickOnce();
    await tickOnce();
    expect(slow).toHaveBeenCalledTimes(1);

    await act(async () => release());
    await tickOnce();
    expect(slow).toHaveBeenCalledTimes(2);
  });
});
