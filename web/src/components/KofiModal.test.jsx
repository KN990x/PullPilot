/**
 * Mounted through Footer rather than on its own: the lazy load, the focus restore and the
 * "reopening does not reload Ko-fi" guarantee are all properties of the button and the
 * dialog together, and testing the dialog in isolation would prove none of them.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "../i18n";
import Footer from "./Footer";
import { EXIT_MS, KOFI_URL, KOFI_EMBED_URL, LOAD_TIMEOUT_MS } from "./KofiModal";

function renderFooter() {
  const t = i18n.getFixedT("es");
  const utils = render(<Footer t={t} />);
  return { ...utils, t, button: screen.getByRole("button", { name: t("footer.support") }) };
}

// Closing keeps the panel on screen for the exit animation; the tests have to sit through
// it or the next assertion runs against a dialog that is still mounted.
function finishExitAnimation() {
  act(() => {
    vi.advanceTimersByTime(EXIT_MS);
  });
}

// The frame only counts as loaded when its document is out of reach; see
// `hasCrossOriginDocument`. jsdom hands over a perfectly readable about:blank, which is
// what a blocked frame looks like, so the success case has to be staged.
function fireCrossOriginLoad(iframe) {
  Object.defineProperty(iframe, "contentDocument", { configurable: true, get: () => null });
  fireEvent.load(iframe);
}

function giveUpWaitingForKofi() {
  act(() => {
    vi.advanceTimersByTime(LOAD_TIMEOUT_MS);
  });
}

describe("KofiModal", () => {
  beforeEach(async () => {
    vi.useFakeTimers();
    await i18n.changeLanguage("es");
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not touch ko-fi.com until the button is pressed", () => {
    const { container } = renderFooter();

    expect(container.querySelector("iframe")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens the embedded widget with the untouched embed URL", () => {
    const { container, button, t } = renderFooter();

    fireEvent.click(button);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName(t("footer.support"));

    const iframe = container.querySelector("iframe");
    expect(iframe).toHaveAttribute("src", KOFI_EMBED_URL);
    expect(iframe).toHaveAttribute("height", "712");
  });

  it("closes on Escape and hands focus back to the footer button", () => {
    const { button } = renderFooter();
    button.focus();

    fireEvent.click(button);
    fireEvent.keyDown(document, { key: "Escape" });
    finishExitAnimation();

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(button).toHaveFocus();
  });

  it("closes on a backdrop click but not on a click inside the panel", () => {
    const { button, t } = renderFooter();
    fireEvent.click(button);

    fireEvent.click(screen.getByRole("dialog"));
    finishExitAnimation();
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("dialog").parentElement);
    finishExitAnimation();
    expect(screen.queryByRole("dialog")).toBeNull();

    // And the X, which is where focus lands on open.
    fireEvent.click(button);
    fireEvent.click(screen.getByRole("button", { name: t("modal.close") }));
    finishExitAnimation();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("locks the page behind it and restores what was there before", () => {
    document.body.style.overflow = "auto";
    const { button } = renderFooter();

    fireEvent.click(button);
    expect(document.body.style.overflow).toBe("hidden");

    fireEvent.keyDown(document, { key: "Escape" });
    finishExitAnimation();
    expect(document.body.style.overflow).toBe("auto");
    document.body.style.overflow = "";
  });

  it("keeps the same iframe across reopens so Ko-fi is fetched once", () => {
    const { container, button } = renderFooter();

    fireEvent.click(button);
    const first = container.querySelector("iframe");

    fireEvent.keyDown(document, { key: "Escape" });
    finishExitAnimation();
    fireEvent.click(button);

    expect(container.querySelectorAll("iframe")).toHaveLength(1);
    expect(container.querySelector("iframe")).toBe(first);
  });

  it("shows a skeleton until the widget actually arrives", () => {
    const { container, button, t } = renderFooter();

    fireEvent.click(button);
    expect(screen.getByRole("status")).toHaveTextContent(t("footer.support_loading"));

    fireCrossOriginLoad(container.querySelector("iframe"));

    expect(screen.queryByRole("status")).toBeNull();
  });

  it("falls back to a link when the frame never loads", () => {
    // No connection: the request hangs and nothing ever fires.
    const { button, t } = renderFooter();
    fireEvent.click(button);

    giveUpWaitingForKofi();

    expect(screen.getByText(t("footer.support_blocked_title"))).toBeInTheDocument();
    // Exact, not a regex: the permanent link at the bottom of the panel reads
    // "¿No carga? Abrir en Ko-fi" and would match a loose one.
    expect(screen.getByRole("link", { name: t("footer.support_open") })).toHaveAttribute(
      "href",
      KOFI_URL,
    );
  });

  it("does not mistake the blank document an ad blocker leaves behind for the widget", () => {
    // uBlock cancels the request and the frame stays on its readable about:blank, but it
    // still fires `load`. Taking that at face value would show an empty white box forever.
    const { container, button, t } = renderFooter();
    fireEvent.click(button);

    fireEvent.load(container.querySelector("iframe"));
    expect(screen.getByRole("status")).toBeInTheDocument();

    giveUpWaitingForKofi();
    expect(screen.getByText(t("footer.support_blocked_title"))).toBeInTheDocument();
  });

  it("asks Ko-fi again when the user retries", () => {
    const { container, button, t } = renderFooter();
    fireEvent.click(button);
    giveUpWaitingForKofi();
    expect(container.querySelector("iframe")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: t("offline.retry") }));

    const retried = container.querySelector("iframe");
    expect(retried).toHaveAttribute("src", KOFI_EMBED_URL);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("gives up immediately when the browser already knows it is offline", () => {
    const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const { button, t } = renderFooter();

    fireEvent.click(button);

    expect(screen.getByText(t("footer.support_blocked_title"))).toBeInTheDocument();
    online.mockRestore();
  });
});
