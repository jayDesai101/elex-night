import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

// One pipeline cycle (Pipeline.run_once in src/elex/pipeline/cycle.py) plus the serving path.
// A token walks two cycles: a normal one, then one where civicAPI's health check fails and a
// data-quality error blocks the publish.

const W = 130;
const H = 40;
const cx = (c: number) => 75 + c * 200;
const cy = (r: number) => 60 + r * 100;

type NodeId =
  | "clock" | "health" | "discover" | "fetch" | "archive"
  | "search" | "dbt" | "dq" | "model" | "export"
  | "blocked" | "parquet" | "api" | "web";

const NODES: Record<NodeId, { label: string; c: number; r: number }> = {
  clock: { label: "EVERY 60 S", c: 0, r: 0 },
  health: { label: "HEALTH", c: 1, r: 0 },
  discover: { label: "DISCOVER", c: 2, r: 0 },
  fetch: { label: "FETCH", c: 3, r: 0 },
  archive: { label: "ARCHIVE", c: 4, r: 0 },
  search: { label: "SEARCH", c: 0, r: 1 },
  dbt: { label: "DBT BUILD", c: 1, r: 1 },
  dq: { label: "DQ TESTS", c: 2, r: 1 },
  model: { label: "MODEL", c: 3, r: 1 },
  export: { label: "EXPORT", c: 4, r: 1 },
  blocked: { label: "BLOCKED", c: 2, r: 2 },
  parquet: { label: "PARQUET", c: 4, r: 2 },
  api: { label: "FASTAPI", c: 3, r: 3 },
  web: { label: "DASHBOARD", c: 2, r: 3 },
};

type Pt = [number, number];
// `at` puts the label on the line (with a background); otherwise it sits above the midpoint.
type Edge = { id: string; pts: Pt[]; label?: string; at?: Pt };

const right = (n: NodeId): Pt => [cx(NODES[n].c) + W / 2, cy(NODES[n].r)];
const left = (n: NodeId): Pt => [cx(NODES[n].c) - W / 2, cy(NODES[n].r)];
const top = (n: NodeId, dx = 0): Pt => [cx(NODES[n].c) + dx, cy(NODES[n].r) - H / 2];
const bottom = (n: NodeId, dx = 0): Pt => [cx(NODES[n].c) + dx, cy(NODES[n].r) + H / 2];

const EDGES: Edge[] = [
  { id: "clock-health", pts: [right("clock"), left("health")] },
  { id: "health-discover", pts: [right("health"), left("discover")], label: "ok" },
  { id: "discover-fetch", pts: [right("discover"), left("fetch")], label: "due races" },
  { id: "fetch-archive", pts: [right("fetch"), left("archive")], label: "changes" },
  {
    id: "archive-dbt",
    pts: [bottom("archive"), [cx(4), 110], [cx(1) + 25, 110], top("dbt", 25)],
    label: "raw .json.gz",
    at: [cx(2) + 100, 110],
  },
  {
    id: "health-search",
    pts: [bottom("health", -25), [cx(1) - 25, 125], [cx(0), 125], top("search")],
    label: "down",
    at: [cx(0) + 88, 125],
  },
  { id: "search-dbt", pts: [right("search"), left("dbt")], label: "totals" },
  { id: "dbt-dq", pts: [right("dbt"), left("dq")] },
  { id: "dq-model", pts: [right("dq"), left("model")], label: "pass" },
  { id: "model-export", pts: [right("model"), left("export")] },
  { id: "dq-blocked", pts: [bottom("dq"), top("blocked")], label: "error", at: [cx(2) + 32, 210] },
  { id: "export-parquet", pts: [bottom("export"), top("parquet")], label: "swap CURRENT", at: [cx(4) - 58, 210] },
  { id: "parquet-api", pts: [bottom("parquet"), [cx(4), 310], [cx(3), 310], top("api")] },
  { id: "api-web", pts: [left("api"), right("web")], label: "30 s" },
  {
    id: "loop",
    pts: [right("parquet"), [950, cy(2)], [950, 18], [cx(0), 18], top("clock")],
    label: "next cycle",
    at: [cx(2) + 100, 18],
  },
];

type Step = { node: NodeId; via?: string; note: string };

const STEPS: Step[] = [
  { node: "clock", note: "A cycle starts every 60 seconds." },
  { node: "health", via: "clock-health", note: "Check civicAPI's /status first." },
  { node: "discover", via: "health-discover", note: "Load the catalog: 509 races in tiers A, B and C." },
  { node: "fetch", via: "discover-fetch", note: "Poll the races that are due, inside the cycle's time budget." },
  { node: "archive", via: "fetch-archive", note: "Write every new response to disk as gzip JSON, deduplicated by hash." },
  { node: "dbt", via: "archive-dbt", note: "dbt builds silver and gold tables in DuckDB from the archive." },
  { node: "dq", via: "dbt-dq", note: "26 data-quality tests run with the build." },
  { node: "model", via: "dq-model", note: "The projection model runs (off tonight: counts only)." },
  { node: "export", via: "model-export", note: "Export a new versioned Parquet snapshot." },
  { node: "parquet", via: "export-parquet", note: "Swap the CURRENT pointer atomically, so any version can be rolled back to." },
  { node: "api", via: "parquet-api", note: "FastAPI reads only Parquet, never the live database." },
  { node: "web", via: "api-web", note: "This dashboard polls the API every 30 seconds." },
  { node: "clock", via: "loop", note: "Next cycle." },
  { node: "health", via: "clock-health", note: "This time civicAPI's health check fails." },
  { node: "search", via: "health-search", note: "Fall back to search: every race's totals in two requests." },
  { node: "dbt", via: "search-dbt", note: "The archived totals still get built." },
  { node: "dq", via: "dbt-dq", note: "A data-quality test fails with error severity." },
  { node: "blocked", via: "dq-blocked", note: "Publishing is blocked: the page keeps the last good version." },
];

// Travel time scales with edge length, so the token moves at an even speed.
const MS_PER_UNIT = 1.1;
const DWELL_MS = 900;
const FADE_MS = 160;

const lengthOf = (pts: Pt[]) =>
  pts.slice(1).reduce((a, p, k) => a + Math.hypot(p[0] - pts[k][0], p[1] - pts[k][1]), 0);
const EDGE_BY_ID: Record<string, Edge> = Object.fromEntries(EDGES.map((e) => [e.id, e]));
const EDGE_LEN: Record<string, number> = Object.fromEntries(EDGES.map((e) => [e.id, lengthOf(e.pts)]));
const MOVE_MS = STEPS.map((s) =>
  s.via ? Math.min(Math.max(EDGE_LEN[s.via] * MS_PER_UNIT, 450), 1300) : 0
);

const ease = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);

function pathD(pts: Pt[]): string {
  return pts.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
}

function pointAt(pts: Pt[], t: number): Pt {
  const segs = pts.slice(1).map((p, i) => Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]));
  let d = t * segs.reduce((a, b) => a + b, 0);
  for (let i = 0; i < segs.length; i++) {
    if (d <= segs[i] || i === segs.length - 1) {
      const k = segs[i] ? Math.min(d / segs[i], 1) : 1;
      return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k];
    }
    d -= segs[i];
  }
  return pts[pts.length - 1];
}

function midpoint(e: Edge): Pt {
  const [a, b] = [e.pts[0], e.pts[e.pts.length - 1]];
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
}

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export const PipelineGraph: React.FC = () => {
  const [i, setI] = useState(0);
  const [arrived, setArrived] = useState(true);
  const [playing, setPlaying] = useState(() => !reducedMotion());
  // Position on the timeline: step index and ms into that step (travel, then dwell).
  // Frames write the token and trail straight to the DOM; React re-renders only per step.
  const pos = useRef({ i: 0, t: 0 });
  const arrivedRef = useRef(true);
  const tokenRef = useRef<SVGGElement>(null);
  const trailRef = useRef<SVGPathElement>(null);

  const draw = useCallback(() => {
    const { i, t } = pos.current;
    const step = STEPS[i];
    const move = MOVE_MS[i];
    const edge = step.via ? EDGE_BY_ID[step.via] : undefined;
    const done = !edge || t >= move;
    if (edge) {
      const k = done ? 1 : ease(t / move);
      const [x, y] = pointAt(edge.pts, k);
      // fade in leaving the source box, fade out into the target box
      const opacity = done ? 1 - Math.min((t - move) / (FADE_MS * 2), 1) : Math.min(t / FADE_MS, 1);
      tokenRef.current?.setAttribute("transform", `translate(${x} ${y})`);
      tokenRef.current?.setAttribute("opacity", String(opacity));
      if (trailRef.current) trailRef.current.style.strokeDashoffset = String(EDGE_LEN[edge.id] * (1 - k));
    } else {
      tokenRef.current?.setAttribute("opacity", "0");
    }
    if (done !== arrivedRef.current) {
      arrivedRef.current = done;
      setArrived(done);
    }
  }, []);

  useLayoutEffect(draw, [i, draw]);

  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    let id = 0;
    const frame = (now: number) => {
      const s = pos.current;
      s.t += Math.min(now - last, 100); // a background tab resumes where it left off
      last = now;
      if (s.t >= MOVE_MS[s.i] + DWELL_MS) {
        s.t -= MOVE_MS[s.i] + DWELL_MS;
        s.i = (s.i + 1) % STEPS.length;
        setI(s.i);
      }
      draw();
      id = requestAnimationFrame(frame);
    };
    id = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(id);
  }, [playing, draw]);

  const next = () => {
    const n = (pos.current.i + 1) % STEPS.length;
    pos.current = { i: n, t: MOVE_MS[n] };
    setPlaying(false);
    setI(n);
  };

  const step = STEPS[i];
  const edge = step.via ? EDGE_BY_ID[step.via] : undefined;
  const lit = arrived ? step.node : STEPS[(i + STEPS.length - 1) % STEPS.length].node;

  return (
    <div>
      <div className="pg-canvas overflow-x-auto rounded-xl border border-slate-800 bg-slate-950 p-2">
        <svg
          viewBox="0 0 965 400"
          className="min-w-[640px] font-mono text-slate-500"
          role="img"
          aria-label="Pipeline graph: archive, validate, model, export and serve, every 60 seconds"
        >
          <defs>
            <marker id="pg-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0 0 L8 4 L0 8 z" fill="currentColor" />
            </marker>
          </defs>

          {EDGES.map((e) => {
            const [lx, ly] = e.at ?? midpoint(e);
            return (
              <g key={e.id} className="text-slate-500">
                <path d={pathD(e.pts)} fill="none" stroke="currentColor" markerEnd="url(#pg-arrow)" />
                {e.label && e.at && (
                  <rect
                    x={lx - e.label.length * 3.6 - 6}
                    y={ly - 9}
                    width={e.label.length * 7.2 + 12}
                    height={18}
                    style={{ fill: "var(--pg-bg)" }}
                  />
                )}
                {e.label && (
                  <text x={lx} y={e.at ? ly + 4 : ly - 7} textAnchor="middle" fontSize={e.at ? 12 : 11} fill="currentColor">
                    {e.label}
                  </text>
                )}
              </g>
            );
          })}

          {edge && (
            <path
              key={`trail-${i}`}
              ref={trailRef}
              d={pathD(edge.pts)}
              fill="none"
              stroke="currentColor"
              strokeWidth={1.8}
              strokeDasharray={EDGE_LEN[edge.id]}
              className="text-slate-100"
              style={{ strokeDashoffset: arrived ? 0 : EDGE_LEN[edge.id] }}
            />
          )}

          {(Object.keys(NODES) as NodeId[]).map((id) => {
            const n = NODES[id];
            const active = id === lit;
            const box = { x: cx(n.c) - W / 2, y: cy(n.r) - H / 2, width: W, height: H, rx: 3 };
            return (
              <g key={id} className={`transition-colors duration-300 ${active ? "text-slate-100" : "text-slate-400"}`}>
                <rect
                  {...box}
                  stroke="currentColor"
                  strokeWidth={active ? 2 : 1}
                  style={{ fill: "var(--pg-bg)", transition: "stroke-width 300ms" }}
                />
                <rect
                  {...box}
                  fill="currentColor"
                  fillOpacity={active ? 0.08 : 0}
                  style={{ transition: "fill-opacity 300ms" }}
                />
                {active && arrived && (
                  <rect key={`pulse-${i}`} {...box} className="pg-pulse" fill="none" stroke="currentColor" />
                )}
                <text
                  x={cx(n.c)}
                  y={cy(n.r) + 5}
                  textAnchor="middle"
                  fontSize={14}
                  fontWeight={active ? 700 : 400}
                  fill="currentColor"
                  letterSpacing={0.5}
                >
                  {n.label}
                </text>
              </g>
            );
          })}

          <g ref={tokenRef} opacity={0}>
            <circle r={11} fill="#3b82f6" opacity={0.25} />
            <circle r={5} fill="#3b82f6" stroke="#ef4444" strokeWidth={2} />
          </g>
        </svg>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? "Pause animation" : "Play animation"}
          className="rounded-lg border border-slate-700 px-2.5 py-1 font-mono text-xs text-slate-300 hover:bg-slate-800"
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <button
          type="button"
          onClick={next}
          aria-label="Next step"
          className="rounded-lg border border-slate-700 px-2.5 py-1 font-mono text-xs text-slate-300 hover:bg-slate-800"
        >
          ▶|
        </button>
        <p className="text-sm text-slate-300" aria-live="polite">
          <span className="mr-2 font-mono text-xs text-slate-500">
            {String(i + 1).padStart(2, "0")}/{STEPS.length}
          </span>
          {step.note}
        </p>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Source: Pipeline.run_once in src/elex/pipeline/cycle.py, then src/elex/serve.
      </p>
    </div>
  );
};
