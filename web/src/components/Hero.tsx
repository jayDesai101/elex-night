import React, { useEffect, useState } from "react";
import { applyTheme, getTheme, type Theme } from "../lib/theme";

const clock = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
});

export const Hero: React.FC<{ onHowItWorks: () => void }> = ({ onHowItWorks }) => {
  const [now, setNow] = useState(() => new Date());
  const [theme, setTheme] = useState<Theme>(getTheme);
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => applyTheme(theme), [theme]);

  return (
    <header className="reveal relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80 px-5 py-6 shadow-lg sm:px-8">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,rgba(37,99,235,0.25),transparent_55%),radial-gradient(ellipse_at_bottom_right,rgba(220,38,38,0.22),transparent_55%)]" />
      <div className="relative flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
            Live · Tuesday, November 3, 2026
          </p>
          <h1 className="mt-1 text-3xl font-extrabold tracking-tight text-slate-100 sm:text-4xl">
            2026 Midterm Election Results
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Senate, House and Governor races, county by county, updated every minute.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-2 text-right">
            <div className="font-mono text-lg font-semibold tabular-nums text-slate-100">
              {clock.format(now)}
            </div>
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Eastern Time</div>
          </div>
          <button
            type="button"
            onClick={onHowItWorks}
            className="rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-3 text-sm font-medium text-slate-200 hover:bg-slate-800"
          >
            How it works
          </button>
          <button
            type="button"
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme === "dark" ? "Light mode" : "Dark mode"}
            className="rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-3 text-sm text-slate-200 hover:bg-slate-800"
          >
            {theme === "dark" ? "☀" : "☾"}
          </button>
        </div>
      </div>
      <div className="relative mt-5 h-1 w-full rounded-full bg-gradient-to-r from-blue-600 via-slate-500 to-red-600" />
    </header>
  );
};
