/**
 * The most logic-heavy component in the app and the one no test ever rendered.
 *
 * Its labels are the reason: not one of the seven was associated with its control, so a
 * screen reader announced a row of unnamed comboboxes. Querying by label here is both the
 * assertion and the regression guard — these tests cannot pass without the association.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import i18n from "../i18n";
import ScheduleView from "./ScheduleView";

const t = i18n.getFixedT("es");

function renderView(props = {}) {
  const defaults = {
    t,
    selectedFreq: "daily",
    onSelectedFreqChange: vi.fn(),
    onCreateSchedule: vi.fn((event) => event.preventDefault()),
    projects: [{ name: "plex" }, { name: "pihole" }],
    schedules: [],
    onDeleteSchedule: vi.fn(),
    formatExpression: (expression) => `expr:${expression}`,
  };
  const merged = { ...defaults, ...props };
  return { ...render(<ScheduleView {...merged} />), props: merged };
}

describe("the schedule form", () => {
  it("gives every control an accessible name", () => {
    renderView();

    expect(screen.getByLabelText(t("schedule.task_type"))).toBeInTheDocument();
    expect(screen.getByLabelText(t("schedule.target"))).toBeInTheDocument();
    expect(screen.getByLabelText(t("schedule.frequency"))).toBeInTheDocument();
    // Two number inputs shared one visual label that reached neither of them.
    expect(screen.getByLabelText(t("schedule.hour"))).toBeInTheDocument();
    expect(screen.getByLabelText(t("schedule.minute"))).toBeInTheDocument();
  });

  it("lists every project plus the global target", () => {
    renderView();

    const target = screen.getByLabelText(t("schedule.target"));
    expect(within(target).getAllByRole("option").map((o) => o.value)).toEqual([
      "GLOBAL",
      "plex",
      "pihole",
    ]);
  });

  it("swaps the cron fields for a datetime when the task is one-shot", () => {
    renderView();

    fireEvent.change(screen.getByLabelText(t("schedule.task_type")), {
      target: { value: "date" },
    });

    expect(screen.getByLabelText(t("schedule.datetime_once"))).toBeInTheDocument();
    expect(screen.queryByLabelText(t("schedule.hour"))).not.toBeInTheDocument();
    expect(screen.queryByLabelText(t("schedule.frequency"))).not.toBeInTheDocument();
  });

  it("only asks for a weekday on a weekly schedule", () => {
    const { unmount } = renderView({ selectedFreq: "daily" });
    expect(screen.queryByLabelText(t("schedule.day_week"))).not.toBeInTheDocument();
    unmount();

    renderView({ selectedFreq: "weekly" });
    expect(screen.getByLabelText(t("schedule.day_week"))).toBeInTheDocument();
  });

  it("says which clock each kind of schedule runs on", () => {
    renderView();

    // Cron uses the container TZ, one-shot carries the browser offset. Both say so now.
    expect(screen.getByText(t("schedule.time_hint"))).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(t("schedule.task_type")), {
      target: { value: "date" },
    });
    expect(screen.getByText(t("schedule.date_hint"))).toBeInTheDocument();
  });
});

describe("the active tasks table", () => {
  it("shows the empty state when there is nothing scheduled", () => {
    renderView({ schedules: [] });

    expect(screen.getByText(t("schedule.no_tasks"))).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("uses the singular form for a single task", () => {
    renderView({
      schedules: [{ id: 1, target: "plex", task_type: "cron", expression: "0 4 * * *" }],
    });

    expect(screen.getByText(t("schedule.tasks_count", { count: 1 }))).toBeInTheDocument();
  });

  it("labels its columns", () => {
    renderView({
      schedules: [{ id: 1, target: "plex", task_type: "cron", expression: "0 4 * * *" }],
    });

    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual([
      t("schedule.table_target"),
      t("schedule.table_when"),
      t("schedule.table_actions"),
    ]);
  });

  it("names the delete button after the task it deletes", () => {
    const onDeleteSchedule = vi.fn();
    renderView({
      schedules: [{ id: 7, target: "plex", task_type: "cron", expression: "0 4 * * *" }],
      onDeleteSchedule,
    });

    fireEvent.click(
      screen.getByRole("button", { name: t("schedule.delete_task_named", { target: "plex" }) })
    );

    expect(onDeleteSchedule).toHaveBeenCalledWith(7);
  });
});
