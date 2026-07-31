import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePolling } from "./usePolling";

describe("usePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("calls the callback on every tick until stopped", () => {
    const { result } = renderHook(() => usePolling());
    const tick = vi.fn();

    act(() => result.current.startPolling(tick, 1000));
    act(() => vi.advanceTimersByTime(3000));
    expect(tick).toHaveBeenCalledTimes(3);

    act(() => result.current.stopPolling());
    act(() => vi.advanceTimersByTime(3000));
    expect(tick).toHaveBeenCalledTimes(3);
  });

  it("swaps the callback without restarting the interval", () => {
    // The progress cycle re-registers itself on every tick; restarting the timer each
    // time would keep pushing the next call one full interval away.
    const { result } = renderHook(() => usePolling());
    const first = vi.fn();
    const second = vi.fn();

    act(() => result.current.startPolling(first, 1000));
    act(() => vi.advanceTimersByTime(1000));
    act(() => result.current.startPolling(second, 1000));
    act(() => vi.advanceTimersByTime(1000));

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("restarts when the interval itself changes", () => {
    const { result } = renderHook(() => usePolling());
    const tick = vi.fn();

    act(() => result.current.startPolling(tick, 1000));
    act(() => result.current.startPolling(tick, 5000));
    act(() => vi.advanceTimersByTime(1000));
    expect(tick).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(4000));
    expect(tick).toHaveBeenCalledTimes(1);
  });

  it("stops on unmount so a closed tab does not keep firing", () => {
    const { result, unmount } = renderHook(() => usePolling());
    const tick = vi.fn();

    act(() => result.current.startPolling(tick, 1000));
    unmount();
    act(() => vi.advanceTimersByTime(5000));

    expect(tick).not.toHaveBeenCalled();
  });
});
