import { describe, expect, it } from "vitest";
import { boundsToView } from "./mapview";

const parse = (v: string) => v.split(" ").map(Number);

describe("boundsToView", () => {
  it("keeps the map aspect ratio and centers the state", () => {
    const [x, y, w, h] = parse(boundsToView([[100, 100], [200, 400]])); // tall state
    expect(w / h).toBeCloseTo(960 / 600);
    expect(x + w / 2).toBeCloseTo(150);
    expect(y + h / 2).toBeCloseTo(250);
    expect(h).toBeCloseTo(300 * 1.16); // 8% padding each side
  });
  it("widens height for a wide state", () => {
    const [, , w, h] = parse(boundsToView([[0, 0], [500, 50]]));
    expect(w).toBeCloseTo(500 * 1.16);
    expect(w / h).toBeCloseTo(960 / 600);
  });
});

import { FULL, clampView, panBy, zoomAt } from "./mapview";

describe("pan and zoom", () => {
  it("zooming in keeps the point under the cursor fixed", () => {
    const v = zoomAt(FULL, 2, 480, 300, 960, 600); // center of a 1:1 element
    expect(v.w).toBeCloseTo(480);
    expect(v.x + v.w / 2).toBeCloseTo(480);
    expect(v.y + v.h / 2).toBeCloseTo(300);
  });
  it("cannot zoom out past the whole map or pan off it", () => {
    expect(zoomAt(FULL, 0.5, 100, 100, 960, 600)).toEqual(FULL);
    expect(panBy(FULL, 500, 500, 960, 600)).toEqual(FULL);
    const zoomed = zoomAt(FULL, 4, 0, 0, 960, 600);
    expect(panBy(zoomed, 5000, 5000, 960, 600)).toMatchObject({ x: 0, y: 0 });
  });
  it("dragging right moves the view left by the same screen distance", () => {
    const v = clampView({ x: 400, y: 200, w: 240, h: 150 });
    const moved = panBy(v, 100, 0, 480, 300); // 0.5 map units per px
    expect(moved.x).toBeCloseTo(350);
  });
});

import { withRightInset } from "./mapview";

it("leaves room on the right for the state panel", () => {
  const v = withRightInset({ x: 100, y: 100, w: 200, h: 125 }, 0.4);
  expect(v.x).toBe(100);
  expect(v.w).toBeCloseTo(200 / 0.6); // original spans the left 60%
  expect(v.y + v.h / 2).toBeCloseTo(162.5); // still vertically centered
});

import { replayPath } from "./replay";

it("replay file names match the Python exporter", () => {
  expect(replayPath("/api/health", "K")).toMatch(/replay\/K\/health\.json$/);
  expect(replayPath("/api/map?office=senate", "K")).toMatch(/K\/map__office-senate\.json$/);
  expect(replayPath("/api/races?tracked=true&office=house", "K")).toMatch(
    /K\/races__office-house_tracked-true\.json$/
  );
  expect(replayPath("/api/races/87087/votes", "K")).toMatch(/K\/races_87087_votes\.json$/);
});
