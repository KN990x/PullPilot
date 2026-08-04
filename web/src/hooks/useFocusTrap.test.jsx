/**
 * The two bugs this hook exists to fix.
 *
 * Both modals had their own copy of the trap. One selected focusable elements without
 * `:not([disabled])`, so while the account form was submitting the last node was a
 * disabled submit button and Tab walked straight out of the dialog. The other keyed its
 * effect on an `onClose` that was a fresh arrow every render, so during a global update
 * — one re-render per second — focus jumped back to the close button mid-keystroke.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { useCallback, useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { useFocusTrap } from "./useFocusTrap";

function Dialog({ open, onClose, submitting = false }) {
  const { dialogRef, initialFocusRef } = useFocusTrap({ open, onClose });
  if (!open) {
    return null;
  }
  return (
    <div ref={dialogRef} role="dialog">
      <button ref={initialFocusRef} type="button">
        close
      </button>
      <input aria-label="field" />
      <button type="button">cancel</button>
      <button type="submit" disabled={submitting}>
        save
      </button>
    </div>
  );
}

describe("useFocusTrap", () => {
  it("moves focus into the dialog when it opens", () => {
    render(<Dialog open onClose={vi.fn()} />);

    expect(screen.getByRole("button", { name: "close" })).toHaveFocus();
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<Dialog open onClose={onClose} />);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("wraps Tab from the last focusable element back to the first", () => {
    render(<Dialog open onClose={vi.fn()} />);
    const save = screen.getByRole("button", { name: "save" });
    save.focus();

    fireEvent.keyDown(document, { key: "Tab" });

    expect(screen.getByRole("button", { name: "close" })).toHaveFocus();
  });

  it("wraps Shift+Tab from the first element to the last", () => {
    render(<Dialog open onClose={vi.fn()} />);
    screen.getByRole("button", { name: "close" }).focus();

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    expect(screen.getByRole("button", { name: "save" })).toHaveFocus();
  });

  it("keeps the trap closed when the last element is disabled", () => {
    // The regression: with `save` disabled, the old selector still treated it as the last
    // focusable node, so "focus is on the last element" never matched and Tab escaped.
    render(<Dialog open onClose={vi.fn()} submitting />);
    const cancel = screen.getByRole("button", { name: "cancel" });
    cancel.focus();

    fireEvent.keyDown(document, { key: "Tab" });

    expect(screen.getByRole("button", { name: "close" })).toHaveFocus();
  });

  it("restores focus to whatever was focused before", () => {
    function Host() {
      const [open, setOpen] = useState(false);
      const onClose = useCallback(() => setOpen(false), []);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            open
          </button>
          <Dialog open={open} onClose={onClose} />
        </>
      );
    }
    render(<Host />);
    const opener = screen.getByRole("button", { name: "open" });
    opener.focus();

    fireEvent.click(opener);
    expect(screen.getByRole("button", { name: "close" })).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(opener).toHaveFocus();
  });

  it("does not re-grab focus when the parent re-renders", () => {
    // The polling cycle re-renders App once a second while an update runs.
    function Host() {
      const [, setTick] = useState(0);
      const onClose = useCallback(() => {}, []);
      return (
        <>
          <button type="button" onClick={() => setTick((n) => n + 1)}>
            rerender
          </button>
          <Dialog open onClose={onClose} />
        </>
      );
    }
    render(<Host />);
    const field = screen.getByLabelText("field");
    field.focus();

    fireEvent.click(screen.getByRole("button", { name: "rerender" }));

    expect(field).toHaveFocus();
  });
});
