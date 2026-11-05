# Dashboard UI — where is what

Source: the supplied design (`election-night-dashboard-v2.zip`, full project) installed as `web/`,
plus the changes listed under "Added after the design". Built with Vite + React 18 + TS +
Tailwind 3; TanStack Query polls every 30 s. In production the API serves `web/dist` at `/`
(`:8000`); `npm run dev` proxies `/api` to `:8000`; Vercel uses `web/vercel.json` rewrites.

## Files

```text
web/
├── index.html, package.json, vite.config.ts (/api proxy), tsconfig.json,
│   tailwind.config.js, postcss.config.js, vercel.json (added: /api rewrite to the tunnel)
└── src/
    ├── main.tsx                 React root + QueryClientProvider
    ├── App.tsx                  12-col grid, office tab + selected-race state, all queries
    ├── index.css                Tailwind + dark base styles
    ├── api/types.ts             Response types (mirror src/elex/serve/schemas.py)
    ├── api/client.ts            fetchers, ApiError, isWaitingForResults (503), use* hooks
    ├── lib/scales.ts            party colors (single source) + county RdBu scale
    ├── lib/gauge.ts             needle angle / arc math
    ├── lib/format.ts            formatET, liveState, marginLabel, seatSegments, fullRaceLabel*
    ├── lib/photos.ts*           Wikipedia photo lookup (usePhoto), initials, STATES
    ├── lib/mapview.ts*          viewBox math: zoom to a state, pan, pinch/wheel zoom, clamping
    ├── lib/*.test.ts            vitest (scales, gauge, format, photos*)
    └── components/
        ├── TopBar.tsx           LIVE badge, last updated (ET), office tabs
        ├── SeatCard.tsx         Senate (100) / House (435) bar, gray uncalled, majority marker
        ├── GovernorsCard.tsx    Called N / M
        ├── ExpectedVoteRing.tsx est. % counted (Sen/Gov) or avg % reporting (House)
        ├── CountyMap.tsx        Albers USA counties, state mesh, expand*, click-to-zoom state*,
        │                        tooltip: county, state, margin, reporting, votes*
        ├── KeyRaces.tsx         tracked races, avatars*, civicAPI ✓, NeedleGauge / "Counts only"
        ├── NeedleGauge.tsx      semicircle, p10–p90 arc, median needle
        ├── RaceSpotlight.tsx*   selected race: big photos, votes, share bars
        ├── CandidateAvatar.tsx* photo with party ring, or party-colored initials
        ├── MarginChart.tsx      projection history (shown only when history exists*)
        ├── PipelineHealth.tsx   last ingest, rows processed, DQ check dots, latency sparkline
        └── Footer.tsx           data attribution, disclaimer, photo credit*
```
`*` = added or changed after the design.

## Page layout (App.tsx)

| Row | Left | Right |
| --- | --- | --- |
| 0 | Hero: title, ET clock, How it works, light/dark toggle (full width) | |
| 1 | TopBar (full width) | |
| 2 | ChamberBalance Senate · ChamberBalance House · GovernorsCard · ExpectedVoteRing | |
| 3 | CountyMap (8): expand, state zoom + StateDrawer, flipped-vs-2024 outlines | LatestUpdates + PollClosings (4) |
| 4 | KeyRaceCards (full width): state, % reported, county mini map, top 4 candidates | |
| 5 | RaceSpotlight, VoteTimeline + ClosestRaces, MarginChart when it has data (8) | KeyRaces (4) |
| 6 | PipelineHealth (full width, last): summary chips, issues only, "Show all" | |
| 7 | Footer | |

New files: `Hero.tsx`, `HowItWorks.tsx`, `ChamberBalance.tsx` (replaces SeatCard on the page),
`KeyRaceCards.tsx` (replaced Battleground.tsx), `lib/geo.ts` (per-state county shapes), `StateDrawer.tsx`, `lib/useCountUp.ts` (count-up + leaderOf), `lib/theme.ts`
(light/dark, remembered per browser), `public/og.png` + `favicon.svg`. Light mode remaps the 26
slate classes in `index.css`. Share card URL: `VITE_SITE_URL` (default
https://elex-night.vercel.app) is written into `og:image` at build time.

Below 900 px the grid is one column.

## Data each component uses

| Component | Endpoint | Notes |
| --- | --- | --- |
| TopBar | `/api/health` | LIVE ≤ 180 s, DELAYED ≤ 600 s, else OFFLINE; age uses the per-cycle heartbeat |
| SeatCard, GovernorsCard, ExpectedVoteRing | `/api/summary` | segments sum to 100 / 435; M from discovery |
| CountyMap | `/api/map?office=` | ±40 pt clamp, gray = no data; CT/AK note |
| KeyRaces, RaceSpotlight | `/api/races?office=&tracked=true` | needle only when `projection.status === "ok"` (model is off: ADR-005) |
| MarginChart | `/api/races/{id}/history` | empty while the model is disabled, so it is hidden |
| PipelineHealth | `/api/pipeline` | checks from `ops.dq_results` + source_freshness |
| Avatars | Wikipedia REST summary | accepted only if the page describes a politician |

## Added after the design

- `client.ts`: `shouldRetry(error: Error)` (tsc rejected `unknown`).
- `package.json`: `typecheck`, `types` (openapi-typescript) scripts.
- Race spotlight in row 4, chart only with data; candidate photos; full race names.
- `vercel.json` rewrite for tonight's tunnel (the URL changes if `elex-tunnel` restarts).

## Commands

```bash
cd web && npm run dev          # http://localhost:5173, proxies /api to :8000
npm run typecheck && npx vitest run && npm run build
make types                     # regenerate types from the running API (schema.ts)
make up                        # rebuild the image; the API serves web/dist at :8000
```

## Replay and live: one site

The archiver writes a replay step every 10 minutes after a publish (`static_export.
append_live_step`) into `data/serving/replay/<step>/`, and the API serves that folder at
`/replay/`. The page opens in replay at the night's first step (`lib/replay.ts`, `ReplayBar.
tsx` under the hero); every query is keyed on the step and reads the static files. When the
slider reaches the last step the page hands over to live: queries hit `/api/` and poll
every 30 s, the bar turns green, and "⟲ Watch the night" restarts the replay. A page left
on live follows new steps as they arrive (index re-read every minute). `VITE_REPLAY=0`
at build time removes replay entirely. The in-page "Recap the night" map replay was
removed; `/api/recap` and `lib/recap.ts` remain.

## Touch and mobile

- Map on the page: one finger scrolls the page; two fingers pinch-zoom and pan. Expanded map:
  one finger drags, pinch zooms. Mouse: drag pans; wheel zooms when expanded or with Ctrl/Cmd.
  `+ / − / ⟲` buttons on every device. A drag never counts as a tap.
- Tap targets are 44 px on phones (map corner, zoom buttons, drawer close); `← United States`
  and "Show all" are at least 36-40 px.
- State drawer: below the map on phones, over the bottom of the full-screen map when expanded,
  a side panel from 640 px up. Legend wraps. Closest-races labels shorten under 640 px.
  "How it works" scrolls on short screens.
