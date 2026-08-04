/**
 * Bilingual strings are a hard convention in AGENTS.md, and the backend already guards
 * its own tables (tests/test_log_messages.py). The frontend had no equivalent: a key
 * added to one language only would have shipped silently.
 */
import { describe, expect, it } from "vitest";

import i18n from "./i18n";

function flatten(node, prefix = "") {
  return Object.entries(node).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === "object" && value !== null
      ? flatten(value, path)
      : [[path, value]];
  });
}

const es = Object.fromEntries(flatten(i18n.getResourceBundle("es", "translation")));
const en = Object.fromEntries(flatten(i18n.getResourceBundle("en", "translation")));

describe("i18n resources", () => {
  it("defines the same keys in both languages", () => {
    expect(Object.keys(es).sort()).toEqual(Object.keys(en).sort());
  });

  it("has no empty values", () => {
    const empty = [...Object.entries(es), ...Object.entries(en)]
      .filter(([, value]) => typeof value !== "string" || value.trim() === "")
      .map(([key]) => key);

    expect(empty).toEqual([]);
  });

  it("keeps the interpolation placeholders identical across languages", () => {
    const placeholders = (value) => (value.match(/\{\{\s*\w+\s*\}\}/g) ?? []).sort();
    const mismatched = Object.keys(es).filter(
      (key) =>
        JSON.stringify(placeholders(es[key])) !== JSON.stringify(placeholders(en[key]))
    );

    expect(mismatched).toEqual([]);
  });

  it("gives every {{count}} string both plural forms", () => {
    // i18next falls back to the base key, so a missing _one produced "1 proyectos".
    const countKeys = Object.keys(es).filter((key) => es[key].includes("{{count}}"));
    const missing = countKeys.filter((key) => {
      const stem = key.replace(/_(one|other)$/, "");
      return !(`${stem}_one` in es) || !(`${stem}_other` in es);
    });

    expect(countKeys.length).toBeGreaterThan(0);
    expect(missing).toEqual([]);
  });

  it("only accepts the two supported languages", () => {
    expect(i18n.options.supportedLngs).toContain("es");
    expect(i18n.options.supportedLngs).toContain("en");
  });
});
