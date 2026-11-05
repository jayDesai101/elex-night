import { describe, expect, it } from "vitest";
import {
  angleToPoint,
  clamp,
  describeGaugeArc,
  marginToAngle,
} from "./gauge";

describe("lib/gauge", () => {
  it("clamps numbers to [min, max]", () => {
    expect(clamp(5, -20, 20)).toBe(5);
    expect(clamp(-35, -20, 20)).toBe(-20);
    expect(clamp(35, -20, 20)).toBe(20);
    expect(clamp(Number.NaN, -20, 20)).toBe(0);
  });

  it("maps margins to semicircle angles exactly as required", () => {
    expect(marginToAngle(0)).toBe(0);
    expect(marginToAngle(20)).toBe(90);
    expect(marginToAngle(-20)).toBe(-90);
    expect(marginToAngle(35)).toBe(90);
    expect(marginToAngle(-35)).toBe(-90);
    expect(marginToAngle(10)).toBe(45);
    expect(marginToAngle(-10)).toBe(-45);
  });

  it("computes cartesian points on the semicircle", () => {
    const left = angleToPoint(50, 44, 34, -90);
    expect(left.x).toBeCloseTo(16, 4);
    expect(left.y).toBeCloseTo(44, 4);

    const top = angleToPoint(50, 44, 34, 0);
    expect(top.x).toBeCloseTo(50, 4);
    expect(top.y).toBeCloseTo(10, 4);

    const right = angleToPoint(50, 44, 34, 90);
    expect(right.x).toBeCloseTo(84, 4);
    expect(right.y).toBeCloseTo(44, 4);
  });

  it("describes an SVG arc path for p10 to p90", () => {
    const path = describeGaugeArc(50, 44, 34, -5, 10);
    expect(path).toMatch(/^M \d+\.\d{2} \d+\.\d{2} A 34 34 0 0 1 \d+\.\d{2} \d+\.\d{2}$/);
  });
});
