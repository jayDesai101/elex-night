import { describe, expect, it } from "vitest";
import {
  formatET,
  liveState,
  marginLabel,
  seatSegments,
} from "./format";

describe("lib/format", () => {
  describe("liveState", () => {
    it("returns green LIVE when age_seconds <= 180", () => {
      expect(liveState(0)).toEqual({ label: "LIVE", color: "green" });
      expect(liveState(180)).toEqual({ label: "LIVE", color: "green" });
    });

    it("returns amber DELAYED when 180 < age_seconds <= 600", () => {
      expect(liveState(181)).toEqual({ label: "DELAYED", color: "amber" });
      expect(liveState(600)).toEqual({ label: "DELAYED", color: "amber" });
    });

    it("returns red OFFLINE when age_seconds > 600, negative, or null", () => {
      expect(liveState(601)).toEqual({ label: "OFFLINE", color: "red" });
      expect(liveState(null)).toEqual({ label: "OFFLINE", color: "red" });
      expect(liveState(undefined)).toEqual({ label: "OFFLINE", color: "red" });
      expect(liveState(-5)).toEqual({ label: "OFFLINE", color: "red" });
    });
  });

  describe("formatET", () => {
    it("formats ISO strings in America/New_York with ET suffix", () => {
      expect(formatET("2026-11-04T02:42:00Z")).toBe("9:42 PM ET");
      expect(formatET("2026-11-03T20:28:11Z")).toBe("3:28 PM ET");
    });

    it("returns em-dash for null or invalid timestamps", () => {
      expect(formatET(null)).toBe("—");
      expect(formatET("")).toBe("—");
      expect(formatET("not-a-date")).toBe("—");
    });
  });

  describe("marginLabel", () => {
    it("formats positive D and negative R margins cleanly", () => {
      expect(marginLabel(14.2)).toBe("D +14.2");
      expect(marginLabel(-3.1)).toBe("R +3.1");
      expect(marginLabel(0)).toBe("Even 0.0");
      expect(marginLabel(null)).toBe("—");
    });
  });

  describe("seatSegments", () => {
    it("sums to exactly 100 for Senate", () => {
      const result = seatSegments({
        office: "senate",
        d_total: 32,
        r_total: 31,
        o_total: 2,
        uncalled: 35,
        majority_line: 51,
      });
      expect(result.total).toBe(100);
      const sum = result.segments.reduce((acc, s) => acc + s.count, 0);
      expect(sum).toBe(100);
      expect(result.segments.map((s) => s.key)).toEqual([
        "D",
        "O",
        "uncalled",
        "R",
      ]);
      expect(result.majorityPct).toBeCloseTo(51, 5);
    });

    it("sums to exactly 435 for House", () => {
      const result = seatSegments({
        office: "house",
        d_total: 105,
        r_total: 112,
        o_total: 0,
        uncalled: 218,
        majority_line: 218,
      });
      expect(result.total).toBe(435);
      const sum = result.segments.reduce((acc, s) => acc + s.count, 0);
      expect(sum).toBe(435);
      expect(result.majorityPct).toBeCloseTo((218 / 435) * 100, 5);
    });
  });
});

import { fullRaceLabel } from "./format";

describe("fullRaceLabel", () => {
  it("expands Senate and Governor labels", () => {
    expect(fullRaceLabel("AK-Sen")).toBe("Alaska Senate");
    expect(fullRaceLabel("NH-Gov")).toBe("New Hampshire Governor");
  });
  it("leaves other labels alone", () =>
    expect(fullRaceLabel("Arizona US House 6")).toBe("Arizona US House 6"));
});

import { ageSeconds } from "./format";

describe("badge age is measured against the clock", () => {
  const t = "2026-11-04T04:00:00Z";
  it("a page with old data turns DELAYED, then OFFLINE, as time passes", () => {
    const base = Date.parse(t);
    expect(liveState(ageSeconds(t, base + 60_000)).label).toBe("LIVE");
    expect(liveState(ageSeconds(t, base + 300_000)).label).toBe("DELAYED");
    expect(liveState(ageSeconds(t, base + 40 * 60_000)).label).toBe("OFFLINE");
  });
  it("no timestamp means no age", () => expect(ageSeconds(null, 0)).toBeNull());
});

import { defaultRace } from "./format";

it("spotlight starts on the closest race with votes", () => {
  const r = (id: number, votes: number, margin: number | null) => ({
    race_id: id, candidates: [{ votes }], margin_pp: margin,
  });
  expect(defaultRace([r(1, 0, null), r(2, 50, 12), r(3, 80, -3)]).race_id).toBe(3);
  expect(defaultRace([r(1, 0, null), r(2, 0, null)]).race_id).toBe(1);
});
