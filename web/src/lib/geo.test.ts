import { describe, expect, it } from "vitest";
import { lastName } from "../components/KeyRaceCards";
import { stateCountyShapes } from "./geo";

describe("stateCountyShapes", () => {
  it("draws every county of a state inside the card", () => {
    const ga = stateCountyShapes("GA", 220, 150);
    expect(ga).toHaveLength(159);
    expect(ga.every((s) => s.fips.startsWith("13"))).toBe(true);
    const nums = ga.flatMap((s) => (s.d.match(/-?\d+(\.\d+)?/g) ?? []).map(Number));
    expect(Math.min(...nums)).toBeGreaterThanOrEqual(-0.5);
    expect(Math.max(...nums)).toBeLessThanOrEqual(220.5);
  });
  it("returns nothing for an unknown state and caches per size", () => {
    expect(stateCountyShapes("ZZ", 220, 150)).toEqual([]);
    expect(stateCountyShapes("OH", 220, 150)).toBe(stateCountyShapes("OH", 220, 150));
  });
});

it("uses last names", () => {
  expect(lastName("Jon Ossoff")).toBe("Ossoff");
  expect(lastName("Daniel J. Jr. Sullivan")).toBe("Sullivan");
  expect(lastName("Cher")).toBe("Cher");
});
