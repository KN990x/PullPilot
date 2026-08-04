/**
 * Regressions in the dashboard's live behaviour.
 *
 * Separate from App.test.jsx, which owns the auth state machine, and from
 * App.offline.test.jsx, which has to stub `import.meta.env.DEV` and therefore needs its
 * own module instances (pitfall 12 in AGENTS.md).
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./lib/api", async () => {
  const actual = await vi.importActual("./lib/api");
  return {
    ...actual,
    fetchAuthStatus: vi.fn(),
    fetchProjects: vi.fn(),
    fetchHistory: vi.fn(),
    fetchSchedules: vi.fn(),
    fetchUpdateStatus: vi.fn(),
    toggleProjectSetting: vi.fn(),
    triggerUpdateAll: vi.fn(),
  };
});

import App from "./App";
import i18n from "./i18n";
import {
  fetchAuthStatus,
  fetchHistory,
  fetchProjects,
  fetchSchedules,
  fetchUpdateStatus,
  toggleProjectSetting,
} from "./lib/api";

const t = i18n.getFixedT("es");
const AUTHENTICATED = { setup_complete: true, authenticated: true, username: "admin" };
const PLEX = {
  name: "plex",
  status: "running",
  containers: 2,
  excluded: false,
  full_stop: false,
};

beforeEach(async () => {
  // jsdom's navigator.language is en-US, so the detector would otherwise decide per run.
  // These assertions compare against exact strings, so the language has to be pinned.
  await i18n.changeLanguage("es");
  fetchAuthStatus.mockResolvedValue(AUTHENTICATED);
  fetchProjects.mockResolvedValue([PLEX]);
  fetchHistory.mockResolvedValue([]);
  fetchSchedules.mockResolvedValue([]);
  fetchUpdateStatus.mockResolvedValue({ is_running: false, current: 0, total: 0 });
  toggleProjectSetting.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("a progress poll that fails", () => {
  it("goes offline instead of leaving the UI stuck mid-update", async () => {
    // The exact scenario PullPilot creates for itself: Update All recreates its own
    // container, /api/update-status stops answering. The catch used to swallow the error
    // without stopping the interval, so the progress bar never cleared, every card stayed
    // pointer-events-none and Update All stayed disabled until a manual reload.
    fetchUpdateStatus
      .mockResolvedValueOnce({
        is_running: true,
        current: 1,
        total: 2,
        current_project: "plex",
      })
      .mockRejectedValue(new TypeError("Failed to fetch"));

    render(<App />);

    expect(
      await screen.findByRole("button", { name: t("offline.retry") }, { timeout: 3000 })
    ).toBeInTheDocument();
  });

  it("reports a server-side failure without dropping into offline", async () => {
    const boom = new Error("Request failed (500)");
    boom.status = 500;
    fetchUpdateStatus
      .mockResolvedValueOnce({
        is_running: true,
        current: 1,
        total: 2,
        current_project: "plex",
      })
      .mockRejectedValue(boom);

    render(<App />);

    expect(
      await screen.findByText(t("alerts.progress_error"), {}, { timeout: 3000 })
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: t("offline.retry") })).not.toBeInTheDocument();
  });
});

describe("the optimistic toggles", () => {
  it("restores the previous value when the request fails", async () => {
    toggleProjectSetting.mockRejectedValue(new Error("Request failed (500)"));
    render(<App />);

    const exclude = await screen.findByRole("checkbox", { name: t("card.exclude") });
    expect(exclude).not.toBeChecked();

    fireEvent.click(exclude);

    await waitFor(() => expect(exclude).not.toBeChecked());
    expect(await screen.findByText(t("alerts.config_error"))).toBeInTheDocument();
  });

  it("ignores a second click while the first is still in flight", async () => {
    // Two overlapping requests plus a "flip back" rollback used to invert whatever the
    // second click had just set, leaving the UI disagreeing with the server.
    let release;
    toggleProjectSetting.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve;
        })
    );
    render(<App />);

    const exclude = await screen.findByRole("checkbox", { name: t("card.exclude") });
    fireEvent.click(exclude);
    fireEvent.click(exclude);

    expect(toggleProjectSetting).toHaveBeenCalledTimes(1);
    expect(exclude).toBeChecked();
    release?.();
  });
});

describe("the dashboard's first paint", () => {
  it("does not accuse the user of a broken STACKS_PATH while the scan runs", async () => {
    let resolveProjects;
    fetchProjects.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveProjects = resolve;
        })
    );

    render(<App />);

    await waitFor(() => expect(fetchProjects).toHaveBeenCalled());
    expect(screen.queryByText(t("status.empty_projects_title"))).not.toBeInTheDocument();

    resolveProjects([]);
    expect(await screen.findByText(t("status.empty_projects_title"))).toBeInTheDocument();
  });
});

describe("language switching", () => {
  it("does not re-run the project scan", async () => {
    // Every loader used to depend on `requestContext` and `t`, both of which change
    // identity on a language switch: one click cost a full scan, up to eight `compose ps`
    // subprocesses, plus /history and /schedules.
    render(<App />);

    await waitFor(() => expect(fetchProjects).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: t("app.change_language") }));

    await waitFor(() => expect(document.documentElement.lang).toBe("en"));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(fetchProjects).toHaveBeenCalledTimes(1);
    expect(fetchHistory).toHaveBeenCalledTimes(1);
  });
});
