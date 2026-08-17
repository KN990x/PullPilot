/**
 * AuthLayout owns the language pill for login, setup, offline and loading. The pill used
 * to sit under the white card; it must stay inside the card's top-right corner.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import i18n from "../i18n";
import AuthLayout from "./AuthLayout";

const t = i18n.getFixedT("es");

describe("AuthLayout language control", () => {
  it("keeps the language button inside the login card", () => {
    render(
      <AuthLayout
        t={t}
        i18n={i18n}
        onToggleLanguage={vi.fn()}
        title={t("auth.login_title")}
        subtitle={t("auth.login_subtitle")}
      >
        <p>form</p>
      </AuthLayout>
    );

    const lang = screen.getByRole("button", { name: t("app.change_language") });
    const card = lang.closest(".relative");

    expect(card).not.toBeNull();
    expect(card).toContainElement(lang);
    expect(card.className).toMatch(/bg-white/);
    // Still a sibling of the form content, not a wrapper below the card.
    expect(card).toContainElement(screen.getByText("form"));
  });
});
