import React, { useEffect, useMemo, useRef, useState } from "react";
import { geoAlbersUsa, geoPath, GeoPermissibleObjects } from "d3-geo";
import { feature, mesh } from "topojson-client";
import usCountiesTopo from "us-atlas/counties-10m.json";
import type { MapCounty, Office } from "../api/types";
import { getCountyFill, countyColorScale, MAP_THEME } from "../lib/scales";
import { useTheme } from "../lib/theme";
import { marginLabel } from "../lib/format";
import { STATES } from "../lib/photos";
import {
  FULL,
  boundsToView,
  panBy,
  parseView,
  viewString,
  withRightInset,
  zoomAt,
  type View,
} from "../lib/mapview";
import { StateDrawer } from "./StateDrawer";

export interface CountyMapProps {
  office: Office;
  counties: MapCounty[] | undefined;
  isLoading: boolean;
  isWaiting: boolean;
  error: Error | null;
}

interface ComputedCountyPath {
  fips: string;
  d: string;
  fallbackName: string | null;
}

interface TopoFeature {
  type: "Feature";
  id?: string | number;
  properties?: { name?: string };
  geometry: GeoPermissibleObjects;
}

interface TopoFeatureCollection {
  type: "FeatureCollection";
  features: TopoFeature[];
}

const MAP_WIDTH = 960;
const MAP_HEIGHT = 600;
const fmtVotes = new Intl.NumberFormat("en-US");

interface StateShape {
  name: string;
  po: string | null;
  view: string; // padded, aspect-matched SVG viewBox around the state
  d: string; // outline path, drawn on hover
  c: [number, number]; // projected centroid, for labels
}

const PO_BY_NAME: Record<string, string> = Object.fromEntries(
  Object.entries(STATES).map(([po, name]) => [name, po])
);

export const CountyMap: React.FC<CountyMapProps> = ({
  office,
  counties,
  isLoading,
  isWaiting,
  error,
}) => {
  const [hoveredFips, setHoveredFips] = useState<string | null>(null);
  const mt = MAP_THEME[useTheme()];
  const [expanded, setExpanded] = useState(false);
  const [zoomState, setZoomState] = useState<string | null>(null); // 2-digit state FIPS
  const boxRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [view, setView] = useState<View>(FULL);
  // Active pointers (mouse or fingers) for drag / pinch, and whether this gesture moved
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const dragged = useRef(false);
  const coarse =
    typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setExpanded(false);
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [expanded]);
  const [pointerPos, setPointerPos] = useState<{ x: number; y: number }>({
    x: 0,
    y: 0,
  });

  // Compute county paths and state border mesh strictly once
  const { countyPaths, stateMeshPath, statesByFips } = useMemo(() => {
    const topology = usCountiesTopo as unknown as Parameters<typeof feature>[0] & {
      objects: {
        counties: Parameters<typeof feature>[1];
        states: Parameters<typeof mesh>[1];
      };
    };

    const countiesGeo = feature(
      topology,
      topology.objects.counties
    ) as unknown as TopoFeatureCollection;

    const projection = geoAlbersUsa().fitSize(
      [MAP_WIDTH, MAP_HEIGHT],
      countiesGeo as unknown as GeoPermissibleObjects
    );
    const pathGenerator = geoPath(projection);

    const computed: ComputedCountyPath[] = [];
    for (const feat of countiesGeo.features) {
      const d = pathGenerator(feat as unknown as GeoPermissibleObjects);
      if (d) {
        const rawId = feat.id !== undefined ? String(feat.id) : "";
        const fips = rawId.padStart(5, "0");
        computed.push({
          fips,
          d,
          fallbackName: feat.properties?.name ?? null,
        });
      }
    }

    const statesMesh = mesh(
      topology as unknown as Parameters<typeof mesh>[0],
      topology.objects.states,
      (a, b) => a !== b
    );
    const stateMeshD =
      pathGenerator(statesMesh as unknown as GeoPermissibleObjects) ?? "";

    const statesGeo = feature(
      topology,
      topology.objects.states as unknown as Parameters<typeof feature>[1]
    ) as unknown as TopoFeatureCollection;
    const states = new Map<string, StateShape>();
    for (const st of statesGeo.features) {
      const id = String(st.id ?? "").padStart(2, "0");
      const name = st.properties?.name ?? id;
      const b = pathGenerator.bounds(st as unknown as GeoPermissibleObjects);
      if (Number.isFinite(b[0][0])) {
        states.set(id, {
          name,
          po: PO_BY_NAME[name] ?? null,
          view: boundsToView(b),
          d: pathGenerator(st as unknown as GeoPermissibleObjects) ?? "",
          c: pathGenerator.centroid(st as unknown as GeoPermissibleObjects) as [number, number],
        });
      }
    }

    return {
      countyPaths: computed,
      stateMeshPath: stateMeshD,
      statesByFips: states,
    };
  }, []);

  // Join map data on 5-character zero-padded FIPS per poll
  const countyDataByFips = useMemo(() => {
    const lookup = new Map<string, MapCounty>();
    if (!counties) {
      return lookup;
    }
    for (const row of counties) {
      const fips = String(row.fips).padStart(5, "0");
      lookup.set(fips, row);
    }
    return lookup;
  }, [counties]);

  const hoveredCounty = hoveredFips
    ? countyDataByFips.get(hoveredFips)
    : undefined;
  const hoveredState = hoveredFips ? statesByFips.get(hoveredFips.slice(0, 2)) : undefined;
  const zoomed = zoomState ? statesByFips.get(zoomState) : undefined;

  // Zoomed-state summary from the counties we have data for
  const zoomStats = useMemo(() => {
    if (!zoomState) return null;
    let n = 0;
    let reporting = 0;
    let votes = 0;
    for (const [fips, row] of countyDataByFips) {
      if (!fips.startsWith(zoomState)) continue;
      n += 1;
      votes += row.total_votes;
      if ((row.pct_reporting ?? 0) > 0) reporting += 1;
    }
    return { n, reporting, votes };
  }, [zoomState, countyDataByFips]);

  // Counties whose leader differs from the 2024 presidential winner (only once counting)
  const flipped = useMemo(
    () =>
      countyPaths.filter((c) => {
        const row = countyDataByFips.get(c.fips);
        return (
          row != null &&
          row.margin_pp != null &&
          row.baseline_margin_pp != null &&
          (row.pct_reporting ?? 0) > 0 &&
          Math.sign(row.margin_pp) !== Math.sign(row.baseline_margin_pp)
        );
      }),
    [countyPaths, countyDataByFips]
  );

  // Zoomed state view; with the side panel open (640 px and up) leave room on the right
  // so the state is not hidden under it. Panel: w-80 (320 px) at right-16 (64 px) + gap.
  const stateView = (): View => {
    if (!zoomed) return FULL;
    const v = parseView(zoomed.view);
    const width = svgRef.current?.getBoundingClientRect().width ?? 0;
    if (typeof window === "undefined" || window.innerWidth < 640 || width === 0) return v;
    return withRightInset(v, (320 + 64 + 16) / width);
  };
  useEffect(() => {
    setView(stateView());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoomed, expanded]);

  const svgSize = () => {
    const r = svgRef.current?.getBoundingClientRect();
    return { left: r?.left ?? 0, top: r?.top ?? 0, cw: r?.width ?? 960, ch: r?.height ?? 600 };
  };

  // Wheel zoom: when expanded, or anywhere with Ctrl/Cmd (so page scrolling is not hijacked).
  // A native listener, because React wheel handlers are passive and cannot preventDefault.
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!expanded && !e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const { left, top, cw, ch } = svgSize();
      const factor = Math.exp(-e.deltaY * 0.0015);
      setView((v) => zoomAt(v, factor, e.clientX - left, e.clientY - top, cw, ch));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 1) dragged.current = false;
  };
  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const prev = pointers.current.get(e.pointerId);
    if (!prev) return;
    const { left, top, cw, ch } = svgSize();
    const pts = pointers.current;
    if (pts.size >= 2) {
      // pinch: zoom by the change in finger distance around their midpoint, pan with it
      const [a, b] = [...pts.entries()].slice(0, 2);
      const other = a[0] === e.pointerId ? b[1] : a[1];
      const before = Math.hypot(prev.x - other.x, prev.y - other.y);
      const after = Math.hypot(e.clientX - other.x, e.clientY - other.y);
      const mid = { x: (e.clientX + other.x) / 2 - left, y: (e.clientY + other.y) / 2 - top };
      const dx = (e.clientX - prev.x) / 2;
      const dy = (e.clientY - prev.y) / 2;
      setView((v) => panBy(zoomAt(v, before > 0 ? after / before : 1, mid.x, mid.y, cw, ch), dx, dy, cw, ch));
      dragged.current = true;
      setHoveredFips(null);
    } else if (e.pointerType === "mouse" ? e.buttons === 1 : expanded) {
      // one pointer: mouse drag always; a single finger only in the expanded map,
      // so on the page one finger still scrolls normally
      const dx = e.clientX - prev.x;
      const dy = e.clientY - prev.y;
      if (dragged.current || Math.hypot(dx, dy) > 4) {
        dragged.current = true;
        setView((v) => panBy(v, dx, dy, cw, ch));
        setHoveredFips(null);
      }
    }
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
  };
  const onPointerEnd = (e: React.PointerEvent<SVGSVGElement>) => {
    pointers.current.delete(e.pointerId);
  };
  const zoomButton = (factor: number) => {
    const { cw, ch } = svgSize();
    setView((v) => zoomAt(v, factor, cw / 2, ch / 2, cw, ch));
  };
  const zoomedIn = view.w < FULL.w - 0.5;

  const boxWidth = boxRef.current?.clientWidth ?? 600;
  const boxHeight = boxRef.current?.clientHeight ?? 400;

  const legendStops = [-40, -20, -10, 0, 10, 20, 40];

  return (
    <section
      aria-label={`${office} county margin map`}
      className={
        expanded
          ? "fixed inset-0 z-50 flex flex-col overflow-auto bg-slate-950 p-3 sm:p-6"
          : "flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow"
      }
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">
            County Margin Map — {office.toUpperCase()}
            {zoomed ? ` · ${zoomed.name}` : ""}
          </h2>
          <p className="text-xs text-slate-400">
            {zoomed && zoomStats
              ? `${zoomStats.reporting} of ${zoomStats.n} counties reporting · ${fmtVotes.format(zoomStats.votes)} votes`
              : "Two-party margin by county · click a state to zoom"}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {zoomed && (
            <button
              type="button"
              onClick={() => setZoomState(null)}
              className="min-h-[40px] rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800"
            >
              ← United States
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs text-slate-400">
          <span className="font-mono font-semibold text-rose-400">R +40</span>
          <div className="flex h-2.5 overflow-hidden rounded ring-1 ring-slate-700">
            {legendStops.map((stop) => (
              <span
                key={stop}
                className="h-full w-4"
                style={{ backgroundColor: countyColorScale(stop) }}
                title={
                  stop === 0
                    ? "Even"
                    : stop > 0
                    ? `D +${stop}`
                    : `R +${Math.abs(stop)}`
                }
              />
            ))}
          </div>
          <span className="font-mono font-semibold text-blue-400">D +40</span>
          <span className="ml-2 inline-flex items-center gap-1">
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm ring-1 ring-slate-700"
              style={{ backgroundColor: mt.noData }}
            />
            No data
          </span>
          <span className="ml-2 inline-flex items-center gap-1">
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ boxShadow: `0 0 0 2px ${mt.flipped}` }}
            />
            Flipped vs 2024{flipped.length ? ` (${flipped.length})` : ""}
          </span>
        </div>
      </div>

      {isLoading ? (
        <div className="flex aspect-[16/10] w-full items-center justify-center rounded-lg bg-slate-950/60">
          <div className="h-4/5 w-4/5 animate-pulse rounded-lg bg-slate-800/70" />
        </div>
      ) : isWaiting ? (
        <div className="flex aspect-[16/10] w-full items-center justify-center rounded-lg border border-dashed border-slate-800 bg-slate-950/50">
          <p className="text-sm text-slate-400">Waiting for first results</p>
        </div>
      ) : error ? (
        <div className="flex aspect-[16/10] w-full items-center justify-center rounded-lg border border-slate-800 bg-slate-950/50">
          <p className="text-xs text-rose-400">{error.message}</p>
        </div>
      ) : (
        <div
          ref={boxRef}
          className={`relative w-full overflow-hidden rounded-lg bg-slate-950/70 p-2 ${
            expanded ? "flex-1" : ""
          }`}
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            setPointerPos({
              x: e.clientX - rect.left,
              y: e.clientY - rect.top,
            });
          }}
          onMouseLeave={() => setHoveredFips(null)}
          onPointerDown={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            setPointerPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
          }}
        >
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? "Minimize map" : "Expand map"}
            title={expanded ? "Minimize (Esc)" : "Expand"}
            className="absolute right-3 top-3 z-30 flex h-11 w-11 items-center justify-center rounded-lg border border-slate-700/80 bg-slate-900/80 text-lg text-slate-200 shadow-lg backdrop-blur transition hover:border-slate-500 hover:bg-slate-800 hover:text-white sm:h-9 sm:w-9"
          >
            {expanded ? "⤡" : "⤢"}
          </button>
          <div className="absolute bottom-3 right-3 z-30 flex flex-col overflow-hidden rounded-lg border border-slate-700/80 bg-slate-900/80 shadow-lg backdrop-blur">
            {[
              { label: "+", aria: "Zoom in", on: () => zoomButton(1.6) },
              { label: "−", aria: "Zoom out", on: () => zoomButton(1 / 1.6) },
              {
                label: "⟲",
                aria: "Reset view",
                on: () => setView(stateView()),
              },
            ].map((b) => (
              <button
                key={b.aria}
                type="button"
                aria-label={b.aria}
                title={b.aria}
                onClick={b.on}
                className="flex h-11 w-11 items-center justify-center text-lg text-slate-200 hover:bg-slate-800 sm:h-8 sm:w-8 sm:text-base"
              >
                {b.label}
              </button>
            ))}
          </div>
          <svg
            ref={svgRef}
            viewBox={viewString(view)}
            preserveAspectRatio="xMidYMid meet"
            className={`w-full select-none ${expanded ? "h-full" : "h-auto"} ${
              zoomedIn || expanded ? "cursor-grab active:cursor-grabbing" : ""
            }`}
            style={{ touchAction: expanded ? "none" : "pan-x pan-y" }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerEnd}
            onPointerCancel={onPointerEnd}
            onPointerLeave={onPointerEnd}
            role="img"
            aria-label="United States county election results map"
          >
            <g className="map-in" style={{ filter: mt.shadow }}>
              {countyPaths.map((county) => {
                const row = countyDataByFips.get(county.fips);
                const fill = getCountyFill(row?.margin_pp ?? null, mt.noData);
                return (
                  <path
                    key={county.fips}
                    d={county.d}
                    fill={fill}
                    stroke={mt.countyStroke}
                    strokeWidth={zoomed ? 0.8 : 0.35}
                    vectorEffect="non-scaling-stroke"
                    opacity={zoomState && !county.fips.startsWith(zoomState) ? 0.25 : 1}
                    className="county-anim cursor-pointer hover:brightness-125"
                    onMouseEnter={() =>
                      // while zoomed, the faded neighbouring states show no tooltip
                      setHoveredFips(
                        zoomState && !county.fips.startsWith(zoomState) ? null : county.fips
                      )
                    }
                    onClick={() => {
                      if (dragged.current) return; // the end of a drag or pinch is not a tap
                      setHoveredFips(county.fips); // tap shows the tooltip on touch screens
                      setZoomState(county.fips.slice(0, 2));
                    }}
                  />
                );
              })}
            </g>

            {flipped.map((c) => (
              <path
                key={`flip-${c.fips}`}
                d={c.d}
                fill="none"
                stroke={mt.flipped}
                strokeWidth={1.4}
                vectorEffect="non-scaling-stroke"
                className="pointer-events-none"
              />
            ))}

            {!zoomed &&
              (["02", "15"] as const).map((id) => {
                const st = statesByFips.get(id);
                return st ? (
                  <text
                    key={`label-${id}`}
                    x={st.c[0]}
                    y={st.c[1] + (id === "02" ? 55 : 28)}
                    textAnchor="middle"
                    className="pointer-events-none fill-slate-400 text-[11px] font-semibold uppercase tracking-wider"
                  >
                    {st.name}
                  </text>
                ) : null;
              })}

            {stateMeshPath && (
              <path
                d={stateMeshPath}
                fill="none"
                stroke={mt.stateStroke}
                strokeWidth={zoomed ? 1.6 : 0.9}
                vectorEffect="non-scaling-stroke"
                strokeLinejoin="round"
                className="pointer-events-none opacity-70"
              />
            )}
            {hoveredState && (
              <path
                d={hoveredState.d}
                fill="none"
                stroke={mt.hoverStroke}
                strokeWidth={2.2}
                vectorEffect="non-scaling-stroke"
                strokeLinejoin="round"
                className="pointer-events-none"
              />
            )}
          </svg>

          {zoomed && (
            <StateDrawer
              onPointerEnter={() => setHoveredFips(null)}
              po={zoomed.po}
              name={zoomed.name}
              onClose={() => setZoomState(null)}
              expanded={expanded}
            />
          )}

          {hoveredFips && (
            <div
              style={{
                left: Math.max(8, Math.min(pointerPos.x + 12, boxWidth - 220)),
                top: Math.max(8, Math.min(pointerPos.y - 96, boxHeight - 120)),
              }}
              className="pointer-events-none absolute z-20 rounded-lg border border-slate-700 bg-slate-900/95 px-3 py-2 text-xs shadow-xl backdrop-blur"
            >
              {!zoomed && (
                <div className="text-sm font-bold tracking-wide text-slate-100">
                  {hoveredState?.name ?? hoveredCounty?.state_po ?? ""}
                </div>
              )}
              <div className={zoomed ? "font-semibold text-slate-100" : "text-[11px] text-slate-400"}>
                {hoveredCounty?.county_name ??
                  countyPaths.find((c) => c.fips === hoveredFips)?.fallbackName ??
                  `FIPS ${hoveredFips}`}
              </div>
              {zoomed && (
                <div className="text-[11px] text-slate-400">{hoveredState?.name ?? ""}</div>
              )}
              <div className="mt-1 flex items-center justify-between gap-4 text-slate-300">
                <span>Margin:</span>
                <span className="font-mono font-bold text-slate-100">
                  {marginLabel(hoveredCounty?.margin_pp ?? null)}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4 text-slate-400">
                <span>Reporting:</span>
                <span className="font-mono text-slate-200">
                  {hoveredCounty?.pct_reporting !== null &&
                  hoveredCounty?.pct_reporting !== undefined
                    ? `${hoveredCounty.pct_reporting.toFixed(1)}%`
                    : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4 text-slate-400">
                <span>Votes:</span>
                <span className="font-mono text-slate-200">
                  {hoveredCounty ? fmtVotes.format(hoveredCounty.total_votes) : "—"}
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      <p className="mt-2.5 text-xs text-slate-400">
        Connecticut and Alaska shown without county results
        {coarse
          ? expanded
            ? " · drag to move, pinch to zoom"
            : " · pinch with two fingers to zoom · tap a state for its races"
          : " · drag to move · Ctrl + scroll to zoom"}
      </p>
    </section>
  );
};
