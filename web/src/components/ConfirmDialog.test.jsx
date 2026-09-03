import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import i18n from "../i18n";
import ConfirmDialog from "./ConfirmDialog";

const t = i18n.getFixedT("es");

describe("ConfirmDialog", () => {
  it("fires onConfirm only once even if Confirm is clicked twice", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();

    render(
      <ConfirmDialog
        t={t}
        open
        title="title"
        message="message"
        confirmLabel={t("confirm.update_all_action")}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    );

    const confirm = screen.getByRole("button", { name: t("confirm.update_all_action") });
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
