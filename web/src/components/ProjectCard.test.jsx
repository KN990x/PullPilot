/**
 * The card's two visual promises: the status dot means something on its own, and a global
 * update greys the card without making it inert.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import i18n from "../i18n";
import ProjectCard from "./ProjectCard";

const t = i18n.getFixedT("es");

function renderCard(project = {}, props = {}) {
  const merged = {
    project: {
      name: "plex",
      status: "running",
      containers: 2,
      excluded: false,
      full_stop: false,
      ...project,
    },
    t,
    isUpdatingThis: false,
    isGlobalUpdate: false,
    currentProject: "",
    onUpdateProject: vi.fn(),
    onToggleSetting: vi.fn(),
    ...props,
  };
  const { container } = render(<ProjectCard {...merged} />);
  return { container, props: merged };
}

/** The colour class on the status dot, which is the aria-hidden span next to the label. */
function dotClass(container) {
  return container.querySelector("span[aria-hidden='true'].rounded-full")?.className ?? "";
}

describe("the status dot", () => {
  it.each([
    ["running", "bg-green-500"],
    ["partial", "bg-yellow-500"],
    ["stopped", "bg-slate-400"],
    ["error", "bg-red-500"],
  ])("draws %s in its own colour", (status, expected) => {
    const { container } = renderCard({ status });
    expect(dotClass(container)).toContain(expected);
  });

  it("does not paint a stack you stopped the same red as one it cannot read", () => {
    // Both used to be red. The text label distinguished them; the dot, which is what gets
    // scanned first, did not.
    const { container: stopped } = renderCard({ status: "stopped" });
    const { container: errored } = renderCard({ status: "error" });

    expect(dotClass(stopped)).not.toBe(dotClass(errored));
  });
});

describe("during a global update", () => {
  it("greys the card without making it unreadable", () => {
    // `pointer-events-none` also took away selecting the stack name and the tooltips, on
    // every card, for as long as any update ran. The controls are disabled individually.
    const { container } = renderCard({}, { isGlobalUpdate: true });
    const card = container.firstChild;

    expect(card.className).toContain("opacity-60");
    expect(card.className).not.toContain("pointer-events-none");

    expect(
      screen.getByRole("button", { name: t("card.update_project_named", { name: "plex" }) })
    ).toBeDisabled();
    expect(screen.getAllByRole("checkbox").every((box) => box.disabled)).toBe(true);
  });
});
