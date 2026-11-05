import React, { useEffect, useMemo, useState } from "react";
import { defaultRace } from "./lib/format";
import type { Office } from "./api/types";
import {
  isWaitingForResults,
  useHealth,
  useMap,
  usePipeline,
  useRaceHistory,
  useAllRaces,
  useRaces,
  useSummary,
} from "./api/client";
import { REPLAY_ENABLED, useReplayClock } from "./lib/replay";
import { ReplayBar } from "./components/ReplayBar";
import { TopBar } from "./components/TopBar";
import { GovernorsCard } from "./components/GovernorsCard";
import { ExpectedVoteRing } from "./components/ExpectedVoteRing";
import { CountyMap } from "./components/CountyMap";
import { KeyRaces } from "./components/KeyRaces";
import { MarginChart } from "./components/MarginChart";
import { RaceSpotlight } from "./components/RaceSpotlight";
import { Hero } from "./components/Hero";
import { HowItWorks } from "./components/HowItWorks";
import { ChamberBalance } from "./components/ChamberBalance";
import { KeyRaceCards } from "./components/KeyRaceCards";
import { VoteTimeline } from "./components/VoteTimeline";
import { ClosestRaces } from "./components/ClosestRaces";
import { PollClosings } from "./components/PollClosings";
import { LatestUpdates } from "./components/LatestUpdates";
import { PipelineHealth } from "./components/PipelineHealth";
import { Footer } from "./components/Footer";

export const App: React.FC = () => {
  const [activeOffice, setActiveOffice] = useState<Office>("senate");
  const [selectedRaceId, setSelectedRaceId] = useState<number | null>(null);
  const [howOpen, setHowOpen] = useState(false);

  const healthQuery = useHealth();
  const summaryQuery = useSummary();
  const mapQuery = useMap(activeOffice);
  const racesQuery = useRaces(activeOffice, true);
  const allRacesQuery = useAllRaces(true);
  const pipelineQuery = usePipeline();

  // Replay clock: the page opens on the night's first step and hands over to live at the
  // last one (lib/replay.ts); the archiver keeps appending steps
  const replay = useReplayClock();

  // Default selected race to the first row when races change
  useEffect(() => {
    const list = racesQuery.data;
    if (!list || list.length === 0) {
      setSelectedRaceId(null);
      return;
    }
    const stillExists =
      list.some((r) => r.race_id === selectedRaceId) ||
      (allRacesQuery.data ?? []).some(
        (r) => r.race_id === selectedRaceId && r.office === activeOffice
      );
    if (!stillExists) {
      setSelectedRaceId(defaultRace(list).race_id);
    }
  }, [racesQuery.data, allRacesQuery.data, activeOffice, selectedRaceId]);

  // Any race can be selected (closest races / latest updates include non-key races)
  const selectedRace = useMemo(
    () =>
      racesQuery.data?.find((r) => r.race_id === selectedRaceId) ??
      allRacesQuery.data?.find((r) => r.race_id === selectedRaceId) ??
      racesQuery.data?.[0],
    [racesQuery.data, allRacesQuery.data, selectedRaceId]
  );

  const historyQuery = useRaceHistory(selectedRace?.race_id ?? null);

  const summaryByOffice = useMemo(() => {
    const map = new Map<Office, NonNullable<typeof summaryQuery.data>[number]>();
    for (const row of summaryQuery.data ?? []) {
      map.set(row.office, row);
    }
    return map;
  }, [summaryQuery.data]);

  return (
    <div className="min-h-screen bg-slate-950 px-3 py-4 text-slate-100 min-[900px]:px-6">
      <div className="mx-auto max-w-[1440px]">
        <div className="grid grid-cols-1 gap-4 min-[900px]:grid-cols-12">
          <div className="reveal min-[900px]:col-span-12" style={{ animationDelay: "70ms" }}>
            <Hero onHowItWorks={() => setHowOpen(true)} />
          </div>

          {REPLAY_ENABLED && (
            <div className="min-[900px]:col-span-12">
              <ReplayBar clock={replay} />
            </div>
          )}

          {/* Row 1: TopBar across the full width */}
          <div className="reveal min-[900px]:col-span-12" style={{ animationDelay: "140ms" }}>
            <TopBar
              activeOffice={activeOffice}
              onSelectOffice={setActiveOffice}
              health={healthQuery.data}
              fallbackLastIngestAt={pipelineQuery.data?.last_ingest_at}
              isLoading={healthQuery.isLoading}
            />
          </div>

          {/* Row 2: Senate SeatCard | House SeatCard | GovernorsCard | ExpectedVoteRing */}
          <div className="reveal min-[900px]:col-span-3" style={{ animationDelay: "210ms" }}>
            <ChamberBalance
              title="Senate"
              summary={summaryByOffice.get("senate")}
              isLoading={summaryQuery.isLoading}
              isWaiting={isWaitingForResults(summaryQuery.error)}
              error={summaryQuery.error}
            />
          </div>

          <div className="reveal min-[900px]:col-span-3" style={{ animationDelay: "280ms" }}>
            <ChamberBalance
              title="House"
              summary={summaryByOffice.get("house")}
              isLoading={summaryQuery.isLoading}
              isWaiting={isWaitingForResults(summaryQuery.error)}
              error={summaryQuery.error}
            />
          </div>

          <div className="reveal min-[900px]:col-span-3" style={{ animationDelay: "350ms" }}>
            <GovernorsCard
              summary={summaryByOffice.get("governor")}
              isLoading={summaryQuery.isLoading}
              isWaiting={isWaitingForResults(summaryQuery.error)}
              error={summaryQuery.error}
            />
          </div>

          <div className="reveal min-[900px]:col-span-3" style={{ animationDelay: "420ms" }}>
            <ExpectedVoteRing
              office={activeOffice}
              summary={summaryByOffice.get(activeOffice)}
              isLoading={summaryQuery.isLoading}
              isWaiting={isWaitingForResults(summaryQuery.error)}
              error={summaryQuery.error}
            />
          </div>

          {/* Map (wide, left) | what is happening now: latest updates + poll closings (right) */}
          <div className="reveal min-[900px]:col-span-8" style={{ animationDelay: "490ms" }}>
            <CountyMap
              office={activeOffice}
              counties={mapQuery.data}
              isLoading={mapQuery.isLoading}
              isWaiting={isWaitingForResults(mapQuery.error)}
              error={mapQuery.error}
            />
          </div>

          <div className="reveal space-y-4 min-[900px]:col-span-4" style={{ animationDelay: "560ms" }}>
            <LatestUpdates onSelectRace={setSelectedRaceId} />
            <PollClosings />
          </div>

          {/* Key race cards: state, % reported, county map of the race, top candidates */}
          <div className="reveal min-[900px]:col-span-12" style={{ animationDelay: "630ms" }}>
            <KeyRaceCards
              title={`${activeOffice === "governor" ? "Governor" : activeOffice === "senate" ? "Senate" : "House"}: Key Races`}
              races={racesQuery.data}
              counties={mapQuery.data}
              selectedRaceId={selectedRace?.race_id ?? null}
              onSelectRace={setSelectedRaceId}
            />
          </div>

          {/* Selected race up close (wide, left) | key races list (right) */}
          <div className="reveal space-y-4 min-[900px]:col-span-8" style={{ animationDelay: "700ms" }}>
            <RaceSpotlight race={selectedRace ?? null} isLoading={racesQuery.isLoading} />
            <div className="grid gap-4 xl:grid-cols-2">
              <VoteTimeline race={selectedRace ?? null} />
              <ClosestRaces office={activeOffice} onSelectRace={setSelectedRaceId} />
            </div>
            {(historyQuery.data?.length ?? 0) > 0 && (
            <MarginChart
              race={selectedRace}
              history={historyQuery.data}
              isLoading={historyQuery.isLoading}
              isWaiting={isWaitingForResults(historyQuery.error)}
              error={historyQuery.error}
            />
            )}
          </div>

          <div className="reveal min-[900px]:col-span-4" style={{ animationDelay: "770ms" }}>
            <KeyRaces
              office={activeOffice}
              races={racesQuery.data}
              selectedRaceId={selectedRace?.race_id ?? null}
              onSelectRace={setSelectedRaceId}
              isLoading={racesQuery.isLoading}
              isWaiting={isWaitingForResults(racesQuery.error)}
              error={racesQuery.error}
            />
          </div>

          {/* Pipeline health last: useful for engineers, not for following the night */}
          <div className="reveal min-[900px]:col-span-12" style={{ animationDelay: "840ms" }}>
            <PipelineHealth
              pipeline={pipelineQuery.data}
              isLoading={pipelineQuery.isLoading}
              isWaiting={isWaitingForResults(pipelineQuery.error)}
              error={pipelineQuery.error}
            />
          </div>
        </div>

        <Footer />
      </div>
      <HowItWorks open={howOpen} onClose={() => setHowOpen(false)} />
    </div>
  );
};

export default App;
