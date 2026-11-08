import { expect, it } from "vitest";
import { localDateISO } from "./localDate";

it("uses the local calendar date rather than the previous UTC day", () => {
  const instant = new Date("2026-10-26T18:00:00Z");
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(instant);
  const part = (name: string) => parts.find((item) => item.type === name)?.value;
  expect(localDateISO(instant)).toBe(`${part("year")}-${part("month")}-${part("day")}`);
});
