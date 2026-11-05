export const MAX_GAUGE_MARGIN = 20;
export const MAX_GAUGE_ANGLE = 90;

export function clamp(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) {
    return 0;
  }
  return Math.min(Math.max(value, min), max);
}

/**
 * Converts a margin in percentage points (D positive, R negative)
 * into a needle angle in degrees within [-90, 90].
 * 0 -> 0°, +20 -> 90°, -20 -> -90°, +35 -> 90°.
 */
export function marginToAngle(margin: number): number {
  const clamped = clamp(margin, -MAX_GAUGE_MARGIN, MAX_GAUGE_MARGIN);
  const angle = (clamped / MAX_GAUGE_MARGIN) * MAX_GAUGE_ANGLE;
  return Object.is(angle, -0) ? 0 : angle;
}

/**
 * Converts a semicircle gauge angle in degrees (where -90° is 9 o'clock left,
 * 0° is 12 o'clock top, and +90° is 3 o'clock right) to SVG cartesian coordinates.
 */
export function angleToPoint(
  cx: number,
  cy: number,
  radius: number,
  angleDeg: number
): { x: number; y: number } {
  const radians = ((angleDeg - 90) * Math.PI) / 180;
  return {
    x: cx + radius * Math.cos(radians),
    y: cy + radius * Math.sin(radians),
  };
}

/**
 * Builds an SVG arc path string on the upper semicircle between two margins.
 */
export function describeGaugeArc(
  cx: number,
  cy: number,
  radius: number,
  startMargin: number,
  endMargin: number
): string {
  const minMargin = Math.min(startMargin, endMargin);
  const maxMargin = Math.max(startMargin, endMargin);
  const startAngle = marginToAngle(minMargin);
  const endAngle = marginToAngle(maxMargin);

  const start = angleToPoint(cx, cy, radius, startAngle);
  const end = angleToPoint(cx, cy, radius, endAngle);

  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius} ${radius} 0 0 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}
