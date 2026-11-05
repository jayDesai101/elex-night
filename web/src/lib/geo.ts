import { geoAlbersUsa, geoPath, type GeoPermissibleObjects } from "d3-geo";
import { feature } from "topojson-client";
import usCountiesTopo from "us-atlas/counties-10m.json";
import { STATES } from "./photos";

interface Feat {
  type: "Feature";
  id?: string | number;
  properties?: { name?: string };
  geometry: GeoPermissibleObjects;
}

let cache: { counties: Feat[]; fipsByPo: Map<string, string> } | null = null;

/** County features and state-postal -> state-FIPS, parsed once and shared. */
function load() {
  if (cache) return cache;
  const topo = usCountiesTopo as unknown as Parameters<typeof feature>[0] & {
    objects: Record<string, Parameters<typeof feature>[1]>;
  };
  const counties = (feature(topo, topo.objects.counties) as unknown as { features: Feat[] })
    .features;
  const states = (feature(topo, topo.objects.states) as unknown as { features: Feat[] }).features;
  const poByName = new Map(Object.entries(STATES).map(([po, name]) => [name, po]));
  const fipsByPo = new Map<string, string>();
  for (const s of states) {
    const po = poByName.get(s.properties?.name ?? "");
    if (po) fipsByPo.set(po, String(s.id).padStart(2, "0"));
  }
  cache = { counties, fipsByPo };
  return cache;
}

export interface CountyShape {
  fips: string;
  d: string;
}

const shapeCache = new Map<string, CountyShape[]>();

/** One state's county paths fitted to width x height (cached per state and size). */
export function stateCountyShapes(po: string, width: number, height: number): CountyShape[] {
  const key = `${po}:${width}x${height}`;
  const hit = shapeCache.get(key);
  if (hit) return hit;
  const { counties, fipsByPo } = load();
  const sf = fipsByPo.get(po);
  if (!sf) return [];
  const mine = counties.filter((c) => String(c.id).padStart(5, "0").startsWith(sf));
  const fc = { type: "FeatureCollection", features: mine } as unknown as GeoPermissibleObjects;
  const path = geoPath(geoAlbersUsa().fitSize([width, height], fc));
  const shapes = mine
    .map((c) => ({ fips: String(c.id).padStart(5, "0"), d: path(c as unknown as GeoPermissibleObjects) ?? "" }))
    .filter((s) => s.d);
  shapeCache.set(key, shapes);
  return shapes;
}
