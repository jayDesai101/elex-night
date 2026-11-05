/** SVG viewBox math for zooming the county map to one state. */

export const MAP_WIDTH = 960;
export const MAP_HEIGHT = 600;

/** viewBox around [[x0,y0],[x1,y1]] with 8% padding, widened to the map's aspect ratio
 * so a tall state (e.g. Florida) is not stretched. */
export function boundsToView(
  [[x0, y0], [x1, y1]]: [[number, number], [number, number]],
  width = MAP_WIDTH,
  height = MAP_HEIGHT
): string {
  const pad = 0.08;
  let w = (x1 - x0) * (1 + 2 * pad);
  let h = (y1 - y0) * (1 + 2 * pad);
  const aspect = width / height;
  if (w / h < aspect) w = h * aspect;
  else h = w / aspect;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  return `${cx - w / 2} ${cy - h / 2} ${w} ${h}`;
}

/** A viewBox in map units. */
export interface View {
  x: number;
  y: number;
  w: number;
  h: number;
}

export const FULL: View = { x: 0, y: 0, w: MAP_WIDTH, h: MAP_HEIGHT };
const MIN_W = MAP_WIDTH / 40; // ~40x zoom: a single small county fills the view

export function parseView(v: string): View {
  const [x, y, w, h] = v.split(" ").map(Number);
  return { x, y, w, h };
}

export function viewString(v: View): string {
  return `${v.x} ${v.y} ${v.w} ${v.h}`;
}

/** Map units per screen pixel for an SVG drawn with preserveAspectRatio="xMidYMid meet". */
export function unitsPerPx(v: View, cw: number, ch: number): number {
  return Math.max(v.w / Math.max(cw, 1), v.h / Math.max(ch, 1));
}

/** Keep the view inside the map: no zooming out past the whole country, no panning off it. */
export function clampView(v: View): View {
  const w = Math.min(MAP_WIDTH, Math.max(MIN_W, v.w));
  const h = (w * v.h) / v.w;
  const x = Math.min(Math.max(v.x, 0), MAP_WIDTH - w);
  const y = Math.min(Math.max(v.y, 0), Math.max(0, MAP_HEIGHT - h));
  return { x, y, w, h };
}

/** Move the view by a screen-pixel drag (content follows the finger). */
export function panBy(v: View, dxPx: number, dyPx: number, cw: number, ch: number): View {
  const k = unitsPerPx(v, cw, ch);
  return clampView({ ...v, x: v.x - dxPx * k, y: v.y - dyPx * k });
}

/** Zoom by `factor` (>1 = in) keeping the map point under screen point (px, py) fixed. */
export function zoomAt(v: View, factor: number, px: number, py: number, cw: number, ch: number): View {
  const k = unitsPerPx(v, cw, ch);
  // offsets of the drawn map inside the element ("meet" letterboxing)
  const ox = (cw - v.w / k) / 2;
  const oy = (ch - v.h / k) / 2;
  const mx = v.x + (px - ox) * k;
  const my = v.y + (py - oy) * k;
  const w = Math.min(MAP_WIDTH, Math.max(MIN_W, v.w / factor));
  const s = w / v.w;
  return clampView({ x: mx - (mx - v.x) * s, y: my - (my - v.y) * s, w, h: v.h * s });
}

/** Widen a view to the right so its content fills only the left (1 - frac) of the map,
 * leaving room for a side panel; height grows by the same ratio, centered. */
export function withRightInset(v: View, frac: number): View {
  const k = 1 / (1 - Math.min(Math.max(frac, 0), 0.6));
  const h = v.h * k;
  return { x: v.x, y: v.y - (h - v.h) / 2, w: v.w * k, h };
}
