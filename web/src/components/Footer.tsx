import React from "react";

export const Footer: React.FC = () => {
  return (
    <footer className="mt-4 flex flex-col items-center justify-between gap-2 rounded-xl border border-slate-800 bg-slate-900/80 px-4 py-3 text-xs text-slate-400 min-[900px]:flex-row">
      <div>
        Data:{" "}
        <a
          href="https://www.civicapi.org/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-slate-200 underline decoration-slate-600 underline-offset-2 hover:text-blue-400"
        >
          civicAPI
        </a>{" "}
        ·{" "}
        <a
          href="https://electionlab.mit.edu/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-slate-200 underline decoration-slate-600 underline-offset-2 hover:text-blue-400"
        >
          MIT Election Lab
        </a>{" "}
        ·{" "}
        <a
          href="https://www.census.gov/programs-surveys/acs"
          target="_blank"
          rel="noopener noreferrer"
          className="text-slate-200 underline decoration-slate-600 underline-offset-2 hover:text-blue-400"
        >
          US Census ACS
        </a>
      </div>
      <div className="font-medium text-slate-300">
        Projections are estimates, not race calls.
      </div>
      <div className="text-xs text-slate-500">
        Candidate photos:{" "}
        <a
          href="https://www.wikipedia.org/"
          target="_blank"
          rel="noopener noreferrer"
          className="underline decoration-slate-600 underline-offset-2 hover:text-blue-400"
        >
          Wikipedia / Wikimedia Commons
        </a>{" "}
        (party-colored initials where no photo is found)
      </div>
    </footer>
  );
};
