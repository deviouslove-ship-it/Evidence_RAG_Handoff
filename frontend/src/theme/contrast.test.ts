import { readFileSync } from "node:fs";

import { expect, it } from "vitest";

// Vitest runs with `frontend/` as the working directory; `import.meta.url` is not
// necessarily a file: URL in this setup, so resolve from the package root instead.
const tokensCss = readFileSync(`${process.cwd()}/src/theme/tokens.css`, { encoding: "utf8" });
const stylesCss = readFileSync(`${process.cwd()}/src/styles.css`, { encoding: "utf8" });

interface Rgba {
  r: number;
  g: number;
  b: number;
  a: number;
}

const TOKENS = new Map<string, string>();
for (const match of tokensCss.matchAll(/--([A-Za-z0-9-]+)\s*:\s*([^;]+);/g)) {
  TOKENS.set(`--${match[1]}`, match[2].trim());
}

/** Every token the badge and mark colours below are declared with. */
const REQUIRED_TOKENS = [
  "--color-text-primary",
  "--color-text-secondary",
  "--color-evidence-bg",
  "--color-evidence-text",
  "--color-success",
  "--color-success-bg",
  "--color-warning",
  "--color-warning-bg",
  "--color-danger",
  "--color-danger-bg",
  "--color-surface",
  "--color-surface-muted",
  "--color-highlight-fill",
] as const;

const NORMAL_TEXT_MIN = 4.5;

function token(name: string): string {
  const value = TOKENS.get(name);
  if (!value) throw new Error(`Thiếu biến màu ${name} trong src/theme/tokens.css`);
  return value;
}

function parseColor(raw: string): Rgba {
  const value = raw.trim().toLowerCase();
  if (value.startsWith("#")) {
    let hex = value.slice(1);
    if (hex.length === 3) {
      hex = hex
        .split("")
        .map((character) => character + character)
        .join("");
    }
    if (!/^[0-9a-f]{6}$/.test(hex)) throw new Error(`Mã màu hex không hợp lệ: ${raw}`);
    return {
      r: Number.parseInt(hex.slice(0, 2), 16),
      g: Number.parseInt(hex.slice(2, 4), 16),
      b: Number.parseInt(hex.slice(4, 6), 16),
      a: 1,
    };
  }
  const functional = /^rgba?\(([^)]+)\)$/.exec(value);
  if (!functional) throw new Error(`Không đọc được màu: ${raw}`);
  const parts = functional[1].split(/[\s,/]+/).filter(Boolean);
  if (parts.length < 3) throw new Error(`Không đủ kênh màu: ${raw}`);
  const [r, g, b] = parts.slice(0, 3).map(Number);
  let alpha = 1;
  if (parts[3]) {
    alpha = parts[3].endsWith("%") ? Number.parseFloat(parts[3]) / 100 : Number.parseFloat(parts[3]);
  }
  if (![r, g, b, alpha].every(Number.isFinite)) throw new Error(`Kênh màu không hợp lệ: ${raw}`);
  return { r, g, b, a: alpha };
}

/** Alpha-composites a translucent fill (e.g. the highlight fill) over an opaque background. */
function composite(foreground: Rgba, background: Rgba): Rgba {
  const alpha = foreground.a;
  return {
    r: foreground.r * alpha + background.r * (1 - alpha),
    g: foreground.g * alpha + background.g * (1 - alpha),
    b: foreground.b * alpha + background.b * (1 - alpha),
    a: 1,
  };
}

function relativeLuminance(color: Rgba): number {
  const channel = (value: number) => {
    const normalized = value / 255;
    return normalized <= 0.04045
      ? normalized / 12.92
      : Math.pow((normalized + 0.055) / 1.055, 2.4);
  };
  return (
    0.2126 * channel(color.r) + 0.7152 * channel(color.g) + 0.0722 * channel(color.b)
  );
}

/** WCAG 2.x contrast ratio: (L1 + 0.05) / (L2 + 0.05). */
function contrastRatio(first: Rgba, second: Rgba): number {
  const firstLuminance = relativeLuminance(first);
  const secondLuminance = relativeLuminance(second);
  const lighter = Math.max(firstLuminance, secondLuminance);
  const darker = Math.min(firstLuminance, secondLuminance);
  return (lighter + 0.05) / (darker + 0.05);
}

function cssBlock(selector: string): string {
  const start = stylesCss.indexOf(selector);
  if (start < 0) throw new Error(`Thiếu selector ${selector} trong src/styles.css`);
  const open = stylesCss.indexOf("{", start);
  const close = stylesCss.indexOf("}", open);
  if (open < 0 || close < 0) throw new Error(`Khối CSS ${selector} không đóng đúng`);
  return stylesCss.slice(open + 1, close);
}

function declarationValue(block: string, property: string): string {
  const match = new RegExp(`(?:^|[;{\\s])${property}\\s*:\\s*([^;]+);`).exec(block);
  if (!match) throw new Error(`Thiếu thuộc tính ${property} trong khối CSS`);
  return match[1].trim();
}

function varToken(value: string): string {
  const match = /var\((--[A-Za-z0-9-]+)\)/.exec(value);
  if (!match) throw new Error(`Giá trị không tham chiếu token: ${value}`);
  return match[1];
}

function assertContrast(label: string, foreground: Rgba, background: Rgba): void {
  const ratio = contrastRatio(foreground, background);
  expect(
    ratio,
    `${label} = ${ratio.toFixed(2)}:1, yêu cầu ≥ ${NORMAL_TEXT_MIN}:1`,
  ).toBeGreaterThanOrEqual(NORMAL_TEXT_MIN);
}

/** Reads the actual text/background token pair declared for a CSS selector. */
function assertCssPair(label: string, selector: string, textProperty: string): void {
  const block = cssBlock(selector);
  const textToken = varToken(declarationValue(block, textProperty));
  const backgroundToken = varToken(declarationValue(block, "background"));
  assertContrast(label, parseColor(token(textToken)), parseColor(token(backgroundToken)));
}

it("declares every colour token used by the search badges and the mark fill", () => {
  for (const name of REQUIRED_TOKENS) {
    expect(TOKENS.has(name), `Thiếu biến ${name} trong tokens.css`).toBe(true);
    expect(() => parseColor(token(name))).not.toThrow();
  }
  expect(TOKENS.size).toBeGreaterThan(20);
});

it("keeps the match labels readable for every match type", () => {
  assertCssPair("match tag exact_phrase", '.match-tag[data-match="exact_phrase"]', "color");
  assertCssPair("match tag phrase_folded", '.match-tag[data-match="phrase_folded"]', "color");
  assertCssPair("match tag all_terms", '.match-tag[data-match="all_terms"]', "color");
  assertCssPair("match tag any_term", '.match-tag[data-match="any_term"]', "color");
});

it("keeps the per-clause effectivity labels readable for every state", () => {
  assertCssPair("effectivity active", '.effectivity-tag[data-state="active"]', "color");
  assertCssPair("effectivity modified", '.effectivity-tag[data-state="modified"]', "color");
  assertCssPair("effectivity repealed", '.effectivity-tag[data-state="repealed"]', "color");
  assertCssPair("effectivity suspended", '.effectivity-tag[data-state="suspended"]', "color");
  assertCssPair(
    "effectivity not_yet_effective",
    '.effectivity-tag[data-state="not_yet_effective"]',
    "color",
  );
  assertCssPair("effectivity unknown", '.effectivity-tag[data-state="unknown"]', "color");
});

it("keeps the highlighted snippet readable over the translucent mark fill", () => {
  const block = cssBlock(".search-clause-snippet mark");
  const textToken = varToken(declarationValue(block, "color"));
  const fillToken = varToken(declarationValue(block, "background"));
  const fill = parseColor(token(fillToken));
  const surface = parseColor(token("--color-surface"));
  // The mark fill is translucent: composite it over the surface before measuring.
  const background = fill.a < 1 ? composite(fill, surface) : fill;
  assertContrast("mark", parseColor(token(textToken)), background);
});

it("parses the colour declarations directly from tokens.css", () => {
  // Guard against a silently empty parse: the raw import must contain declarations.
  expect(tokensCss).toContain("--color-text-primary");
  expect(tokensCss).toContain("--color-highlight-fill");
  expect(TOKENS.size).toBeGreaterThan(0);
});
