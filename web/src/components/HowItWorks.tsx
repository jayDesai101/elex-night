import React, { useEffect } from "react";

import { PipelineGraph } from "./PipelineGraph";

export const HowItWorks: React.FC<{ open: boolean; onClose: () => void }> = ({ open, onClose }) => {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="How this dashboard works"
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-5xl overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900/95 p-5 shadow-2xl sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-100">How it works</h2>
            <p className="text-sm text-slate-400">From a public results API to this page, every minute.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg border border-slate-700 px-2.5 py-1 text-slate-300 hover:bg-slate-800"
          >
            ✕
          </button>
        </div>
        <PipelineGraph />
        <p className="mt-5 text-sm text-slate-400">
          Projections stay off tonight: the model beat the raw count in a 45-state backtest but its
          uncertainty bands failed calibration, so the page shows counts only.{" "}
          <a
            href="https://github.com/jayDesai101/elex-night"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 underline underline-offset-2"
          >
            Code on GitHub
          </a>
        </p>
      </div>
    </div>
  );
};
