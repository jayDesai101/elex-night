import { describe, expect, it } from "vitest";
import type { Recap } from "../api/types";
import { mapAt, rowsUpTo } from "./recap";

// Two races share county 00001 (a split House county); 00002 reports later and updates once.
const rc: Recap = {
  t: [100, 100, 200, 300],
  race_id: [1, 2, 1, 1],
  fips: ["00001", "00001", "00002", "00002"],
  d: [10, 5, 30, 60],
  r: [20, 5, 10, 20],
  total: [30, 10, 40, 80],
  pct: [10, 20, 50, 100],
};

describe("lib/recap", () => {
  it("rowsUpTo counts rows at or before t", () => {
    expect(rowsUpTo(rc.t, 99)).toBe(0);
    expect(rowsUpTo(rc.t, 100)).toBe(2);
    expect(rowsUpTo(rc.t, 250)).toBe(3);
    expect(rowsUpTo(rc.t, 999)).toBe(4);
  });

  it("before the first result the map is empty", () => {
    expect(mapAt(rc, 50, [])).toEqual([]);
  });

  it("sums races per county and keeps each race's latest update", () => {
    const live = [{ fips: "00002", county_name: "B", state_po: "XX", margin_pp: 0,
      pct_reporting: 0, total_votes: 0, baseline_margin_pp: -5 }];
    const at250 = new Map(mapAt(rc, 250, live).map((c) => [c.fips, c]));
    expect(at250.get("00001")).toMatchObject({ total_votes: 40, pct_reporting: 15 });
    expect(at250.get("00001")!.margin_pp).toBeCloseTo((100 * (15 - 25)) / 40);
    expect(at250.get("00002")).toMatchObject({ total_votes: 40, county_name: "B",
      baseline_margin_pp: -5, margin_pp: 50 });
    const end = new Map(mapAt(rc, 300, live).map((c) => [c.fips, c]));
    expect(end.get("00002")).toMatchObject({ total_votes: 80, pct_reporting: 100, margin_pp: 50 });
  });
});
