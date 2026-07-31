/**
 * The offline card, which only exists when demo mode is compiled out.
 *
 * Demo mode is a development tool: it used to be live in the published build and fired on
 * any network error, so while PullPilot recreated its own container the user saw a panel
 * full of invented projects. Vite drops it from the production bundle via
 * `import.meta.env.DEV`, but vitest reports DEV as true no matter the mode, so this file
 * stubs it and re-imports the module graph to exercise what users actually get.
 *
 * Its own file because `vi.resetModules()` would hand the other suite a different set of
 * mock functions from the ones it holds references to.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./i18n";

vi.mock("./lib/api", async () => {
  const actual = await vi.importActual("./lib/api");
  return {
    ...actual,
    fetchAuthStatus: vi.fn(),
    fetchProjects: vi.fn(),
    fetchHistory: vi.fn(),
    fetchSchedules: vi.fn(),
    fetchUpdateStatus: vi.fn(),
  };
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

async function renderWithoutDemoMode(configure) {
  vi.stubEnv("DEV", false);
  vi.resetModules();
  // Imported after the reset so App and the mocks come from the same fresh graph.
  const api = await import("./lib/api");
  configure(api);
  const { default: App } = await import("./App");
  render(<App />);
  return api;
}

describe("with demo mode compiled out", () => {
  it("offers a retry instead of inventing projects", async () => {
    await renderWithoutDemoMode((api) => {
      api.fetchAuthStatus.mockRejectedValue(new TypeError("Failed to fetch"));
    });

    expect(
      await screen.findByRole("button", { name: /reintentar|retry/i })
    ).toBeInTheDocument();
  });

  it("never shows the demo badge", async () => {
    await renderWithoutDemoMode((api) => {
      api.fetchAuthStatus.mockRejectedValue(new TypeError("Failed to fetch"));
    });

    await screen.findByRole("button", { name: /reintentar|retry/i });
    expect(screen.queryByText("DEMO")).not.toBeInTheDocument();
  });

  it("shows the same card when the session is fine but projects cannot load", async () => {
    const api = await renderWithoutDemoMode((mocked) => {
      mocked.fetchAuthStatus.mockResolvedValue({
        setup_complete: true,
        authenticated: true,
        username: "admin",
      });
      mocked.fetchProjects.mockRejectedValue(new TypeError("Failed to fetch"));
      mocked.fetchHistory.mockResolvedValue([]);
      mocked.fetchSchedules.mockResolvedValue([]);
      mocked.fetchUpdateStatus.mockResolvedValue({ is_running: false, current: 0, total: 0 });
    });

    expect(
      await screen.findByRole("button", { name: /reintentar|retry/i })
    ).toBeInTheDocument();
    expect(api.fetchProjects).toHaveBeenCalled();
  });
});
