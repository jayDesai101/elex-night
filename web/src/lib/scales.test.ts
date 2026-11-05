import { describe, expect, it } from "vitest";
import { PARTY_COLORS, countyColorScale, getCountyFill, getPartyColor, MAP_THEME } from "./scales";

describe("map theme", () => {
  it("uses a light no-data fill and dark borders in light mode", () => {
    expect(getCountyFill(null, MAP_THEME.light.noData)).toBe("#e2e8f0");
    expect(getCountyFill(null)).toBe(MAP_THEME.dark.noData);
    expect(getCountyFill(12, MAP_THEME.light.noData)).toBe(getCountyFill(12)); // margins unchanged
    expect(MAP_THEME.light.stateStroke).not.toBe(MAP_THEME.dark.stateStroke);
  });
});

describe("lib/scales", () => {
  it("returns single-source party colors", () => {
    expect(getPartyColor("D")).toBe(PARTY_COLORS.D);
    expect(getPartyColor("R")).toBe(PARTY_COLORS.R);
    expect(getPartyColor("I")).toBe(PARTY_COLORS.I);
    expect(getPartyColor("O")).toBe(PARTY_COLORS.O);
    expect(getPartyColor(null)).toBe(PARTY_COLORS.UNCALLED);
  });

  it("maps county margins with clamped RdBu diverging scale and gray fallback", () => {
    expect(getCountyFill(null)).toBe(PARTY_COLORS.NO_DATA);
    expect(getCountyFill(undefined)).toBe(PARTY_COLORS.NO_DATA);
    expect(getCountyFill(40)).toBe(countyColorScale(40));
    expect(getCountyFill(85)).toBe(countyColorScale(40));
    expect(getCountyFill(-85)).toBe(countyColorScale(-40));
    expect(getCountyFill(20)).not.toBe(getCountyFill(-20));
  });
});
