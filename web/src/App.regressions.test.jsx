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
    updateProject: vi.fn(),
    createSchedule: vi.fn(),
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
  createSchedule,
  triggerUpdateAll,
  updateProject,
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
  updateProject.mockResolvedValue({ status: "accepted", name: "plex" });
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

describe("Update All when one is already running", () => {
  it("says so instead of drawing a progress bar for a run it never started", async () => {
    // The endpoint used to answer 200 for a job that returned after one log line, so the
    // SPA faked `is_running` with a total of 1 and the first poll undid it.
    const conflict = Object.assign(new Error("Request failed (409)"), { status: 409 });
    triggerUpdateAll.mockRejectedValue(conflict);

    render(<App />);
    await waitFor(() => expect(fetchProjects).toHaveBeenCalled());

    fireEvent.click(await screen.findByRole("button", { name: t("status.update_all") }));
    fireEvent.click(await screen.findByRole("button", { name: t("confirm.update_all_action") }));

    expect(await screen.findByText(t("alerts.update_all_in_progress"))).toBeInTheDocument();
    // No progress bar: the run is somebody else's.
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});

describe("a single-project update", () => {
  it("does not wait for the deploy and reports the outcome from the poll", async () => {
    // It used to await the whole thing: one HTTP request held open for minutes, which any
    // proxy with a 60 s read timeout turned into a reported failure for a working deploy.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      fetchUpdateStatus
        .mockResolvedValueOnce({ is_running: false, current: 0, total: 0, projects: {} })
        .mockResolvedValue({
          is_running: false,
          current: 0,
          total: 0,
          projects: { plex: "success" },
        });

      render(<App />);
      await waitFor(() => expect(fetchProjects).toHaveBeenCalled());

      fireEvent.click(
        await screen.findByRole("button", { name: t("card.update_project_named", { name: "plex" }) })
      );

      // The request is acknowledged immediately; nothing awaits the deploy.
      await waitFor(() => expect(updateProject).toHaveBeenCalledWith("plex", expect.anything()));

      await vi.advanceTimersByTimeAsync(1200);

      expect(await screen.findByText(t("alerts.update_ok", { name: "plex" }))).toBeInTheDocument();
      // The history row is written by the same background task, so it has to be reloaded:
      // a per-project update used to write one and never show it.
      await waitFor(() => expect(fetchHistory).toHaveBeenCalledTimes(2));
    } finally {
      vi.useRealTimers();
    }
  });

  it("says the stack is busy when the backend refuses with 409", async () => {
    updateProject.mockRejectedValue(
      Object.assign(new Error("Request failed (409)"), { status: 409 })
    );

    render(<App />);
    await waitFor(() => expect(fetchProjects).toHaveBeenCalled());

    fireEvent.click(
      await screen.findByRole("button", { name: t("card.update_project_named", { name: "plex" }) })
    );

    expect(await screen.findByText(t("alerts.update_in_progress"))).toBeInTheDocument();
  });
});

describe("the history's second page", () => {
  it("appends instead of replacing, and asks for the right offset", async () => {
    // HISTORY_RETENTION keeps 200 rows and the endpoint has always paged; only the newest
    // 20 were ever reachable because nothing sent limit/offset.
    const page = (from) =>
      Array.from({ length: 20 }, (_, i) => ({
        id: from + i,
        timestamp: "2026-08-05T10:00:00Z",
        status: "SUCCESS",
        summary: `run ${from + i}`,
        details: "{}",
      }));
    fetchHistory.mockResolvedValueOnce(page(100)).mockResolvedValueOnce(page(80));

    render(<App />);
    await waitFor(() => expect(fetchProjects).toHaveBeenCalled());

    // Two nav bars are rendered, one for desktop and one for phones; either opens the tab.
    fireEvent.click(screen.getAllByRole("button", { name: t("nav.history") })[0]);
    expect(await screen.findByText("run 100")).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: t("history.load_more") }));

    await waitFor(() =>
      expect(fetchHistory).toHaveBeenLastCalledWith(expect.anything(), {
        limit: 20,
        offset: 20,
      })
    );
    // Both pages on screen: the first must not be thrown away.
    expect(await screen.findByText("run 80")).toBeInTheDocument();
    expect(screen.getByText("run 100")).toBeInTheDocument();
  });
});

describe("the dashboard's own controls", () => {
  it("can refresh the project list without reloading the page", async () => {
    // Projects were loaded on mount and after an update and nowhere else, so a stack that
    // died outside PullPilot stayed green until the tab was reloaded.
    render(<App />);
    await waitFor(() => expect(fetchProjects).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: t("status.refresh_projects") }));

    await waitFor(() => expect(fetchProjects).toHaveBeenCalledTimes(2));
  });

  it("does not offer Update All when every project is excluded", async () => {
    // It was disabled only on an empty list, so the dialog asked to confirm 0 projects.
    fetchProjects.mockResolvedValue([{ ...PLEX, excluded: true }]);

    render(<App />);
    await waitFor(() => expect(fetchProjects).toHaveBeenCalled());

    expect(await screen.findByRole("button", { name: t("status.update_all") })).toBeDisabled();
  });
});

describe("a schedule the backend refuses", () => {
  it.each([
    [409, "Ese proyecto está excluido: quita el interruptor 'Excluir' antes de programarlo."],
    [404, "Ese proyecto no existe. Actualiza la lista de proyectos y vuelve a intentarlo."],
  ])("shows the reason the server gave (%i)", async (status, detail) => {
    // These used to be accepted and then skipped at fire time. Now they are refused, and
    // the detail is already localised by the backend, so it is passed straight through
    // rather than restated in i18n.js.
    createSchedule.mockRejectedValue(Object.assign(new Error(detail), { status }));

    render(<App />);
    await waitFor(() => expect(fetchProjects).toHaveBeenCalled());

    fireEvent.click(screen.getAllByRole("button", { name: t("nav.schedule") })[0]);
    // Submit the form, not the button: the handler reads FormData off event.target.
    const submit = await screen.findByRole("button", { name: t("schedule.create_btn") });
    fireEvent.submit(submit.closest("form"));

    expect(await screen.findByText(detail)).toBeInTheDocument();
    // The picker and the table warnings have to agree with the server again.
    await waitFor(() => expect(fetchProjects).toHaveBeenCalledTimes(2));
  });
});
