import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import i18n from "../i18n";
import Footer from "./Footer";
import { KOFI_EMBED_SRC } from "./SupportModal";

describe("Footer support modal", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("es");
  });

  it("opens the Ko-fi embed and closes it from the header", async () => {
    const t = i18n.getFixedT("es");
    render(<Footer t={t} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: t("footer.tip_me") }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByTitle(t("footer.support_iframe_title"))).toHaveAttribute(
      "src",
      KOFI_EMBED_SRC,
    );

    fireEvent.click(screen.getByRole("button", { name: t("footer.support_close") }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
