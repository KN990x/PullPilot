import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import i18n from "../i18n";
import Footer, { SITE_URL } from "./Footer";

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

  it("opens the support dialog in place instead of linking out", () => {
    // The whole point of the change: no href, so nothing navigates away from the app.
    const t = i18n.getFixedT("es");
    const { container } = render(<Footer t={t} />);

    const button = screen.getByRole("button", { name: t("footer.support") });
    expect(button).toHaveAttribute("type", "button");
    expect(button).not.toHaveAttribute("href");
    expect(container.querySelector("iframe")).toBeNull();
  });
});
