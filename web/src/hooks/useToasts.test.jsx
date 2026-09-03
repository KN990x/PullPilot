import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useToasts } from "./useToasts";

describe("useToasts", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps two toasts that share a key but not the same options", () => {
    const { result } = renderHook(() => useToasts());

    act(() => {
      result.current.pushToast("alerts.update_ok", "success", { name: "plex" });
      result.current.pushToast("alerts.update_ok", "success", { name: "pihole" });
    });

    expect(result.current.toasts).toHaveLength(2);
    expect(result.current.toasts.map((toast) => toast.options.name)).toEqual([
      "plex",
      "pihole",
    ]);
  });

  it("collapses the same key and options into one toast", () => {
    const { result } = renderHook(() => useToasts());

    act(() => {
      result.current.pushToast("alerts.projects_load_error");
      result.current.pushToast("alerts.projects_load_error");
    });

    expect(result.current.toasts).toHaveLength(1);
  });

  it("dismisses a toast when its timer fires", () => {
    const { result } = renderHook(() => useToasts());

    act(() => {
      result.current.pushToast("alerts.projects_load_error");
    });
    expect(result.current.toasts).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(6000);
    });
    expect(result.current.toasts).toHaveLength(0);
  });
});
