import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { resolveTheme } from "./theme";

// Reads the colour tokens straight from index.css, so this fails if a token is changed
// to something that breaks WCAG AA (4.5:1 for body text) in either theme.
const css = readFileSync(new URL("../index.css", import.meta.url), "utf8");

function tokens(selector: string): Record<string, string> {
  const block = css.match(new RegExp(`^${selector.replace(".", "\\.")} \\{([^}]*)\\}`, "m"))![1];
  return Object.fromEntries([...block.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]));
}

function luminance(hex: string) {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [text token, background tokens it is drawn on]
const PAIRS: [string, string[]][] = [
  ["fg", ["bg", "surface", "subtle", "highlight", "accent-soft"]],
  ["fg-muted", ["bg", "surface", "subtle", "highlight"]],
  ["fg-subtle", ["bg", "surface", "subtle"]],
  ["accent-fg", ["bg", "surface", "accent-soft", "highlight"]],
  ["on-accent", ["accent", "accent-hover"]],
  ["ok-fg", ["bg", "surface", "ok-soft", "highlight"]],
  ["warn-fg", ["bg", "warn-soft"]],
  ["danger-fg", ["bg", "danger-soft"]],
];

describe.each([":root", ".dark"])("colour tokens in %s", (selector) => {
  const t = tokens(selector);
  it.each(PAIRS.flatMap(([fg, bgs]) => bgs.map((bg) => [fg, bg])))("%s on %s meets AA", (fg, bg) => {
    expect(t[fg], `missing --${fg}`).toBeDefined();
    expect(t[bg], `missing --${bg}`).toBeDefined();
    expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5);
  });

  it("defines the same tokens as the other theme", () => {
    expect(Object.keys(t).sort()).toEqual(Object.keys(tokens(selector === ":root" ? ".dark" : ":root")).sort());
  });
});

describe("resolveTheme", () => {
  it("system follows the OS; explicit choices win", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
});
