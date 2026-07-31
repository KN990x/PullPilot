/**
 * The auth state machine and the load cycle around it.
 *
 * App.jsx decides what to draw from /api/auth/status and never redirects, so the mapping
 * from status to view is the contract. The second case here is the one that used to cost
 * real work: the mount loaded projects and history, then the first progress check loaded
 * both again — two full project scans, each up to eight `compose ps` subprocesses.
 */
import { render, screen, waitFor } from "@testing-library/react";
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
  };
});

import App from "./App";
import "./i18n";
import {
  fetchAuthStatus,
  fetchHistory,
  fetchProjects,
  fetchSchedules,
  fetchUpdateStatus,
} from "./lib/api";

const AUTHENTICATED = { setup_complete: true, authenticated: true, username: "admin" };

beforeEach(() => {
  fetchProjects.mockResolvedValue([]);
  fetchHistory.mockResolvedValue([]);
  fetchSchedules.mockResolvedValue([]);
  fetchUpdateStatus.mockResolvedValue({ is_running: false, current: 0, total: 0 });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("what the SPA draws for each auth status", () => {
  it("shows the wizard when setup is pending", async () => {
    fetchAuthStatus.mockResolvedValue({ setup_complete: false, authenticated: false });

    render(<App />);

    expect(await screen.findByRole("button", { name: /crear cuenta|create account/i }))
      .toBeInTheDocument();
    expect(fetchProjects).not.toHaveBeenCalled();
  });

  it("shows login when configured but unauthenticated", async () => {
    fetchAuthStatus.mockResolvedValue({ setup_complete: true, authenticated: false });

    render(<App />);

    expect(await screen.findByLabelText(/usuario|username/i)).toBeInTheDocument();
    // No session, no data: these four calls used to fire regardless and 401 four times.
    expect(fetchProjects).not.toHaveBeenCalled();
    expect(fetchHistory).not.toHaveBeenCalled();
    expect(fetchSchedules).not.toHaveBeenCalled();
  });

  it("loads the dashboard once a session is present", async () => {
    fetchAuthStatus.mockResolvedValue(AUTHENTICATED);

    render(<App />);

    await waitFor(() => expect(fetchProjects).toHaveBeenCalled());
    expect(fetchSchedules).toHaveBeenCalled();
  });
});

describe("the load cycle", () => {
  it("does not load projects and history twice on entry", async () => {
    fetchAuthStatus.mockResolvedValue(AUTHENTICATED);

    render(<App />);

    await waitFor(() => expect(fetchUpdateStatus).toHaveBeenCalled());
    // Give the progress check every chance to trigger the redundant reload it used to.
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(fetchProjects).toHaveBeenCalledTimes(1);
    expect(fetchHistory).toHaveBeenCalledTimes(1);
  });

  it("refreshes once a global update has finished", async () => {
    fetchAuthStatus.mockResolvedValue(AUTHENTICATED);
    // Running on the first check, finished on the next: the edge that means new data.
    fetchUpdateStatus
      .mockResolvedValueOnce({ is_running: true, current: 1, total: 2, current_project: "a" })
      .mockResolvedValue({ is_running: false, current: 0, total: 0 });

    render(<App />);

    await waitFor(() => expect(fetchProjects).toHaveBeenCalledTimes(2), { timeout: 3000 });
  });
});
