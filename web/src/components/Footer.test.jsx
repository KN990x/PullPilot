import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import i18n from "../i18n";
import Footer, { KOFI_URL, SITE_URL } from "./Footer";

describe("Footer", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("es");
  });

  it("credits KN990x with the current year and links to the site", () => {
    const t = i18n.getFixedT("es");
    render(<Footer t={t} />);

    const year = new Date().getFullYear();
    const link = screen.getByRole("link", { name: "KN990x" });
    expect(link).toHaveAttribute("href", SITE_URL);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringMatching(/noopener/));
    expect(link.parentElement).toHaveTextContent(`© ${year} KN990x`);
  });

  it("points to the Ko-fi page in a new tab", () => {
    const t = i18n.getFixedT("es");
    render(<Footer t={t} />);

    const link = screen.getByRole("link", { name: t("footer.tip_me") });
    expect(link).toHaveAttribute("href", KOFI_URL);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringMatching(/noopener/));
  });
});
