import { useEffect, useRef, useState } from "react";

/** Animates a number toward `value` (ease-out, ~0.8 s). Instant if the user prefers
 * reduced motion or on the first render. */
export function useCountUp(value: number, durationMs = 800): number {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || from.current === value) {
      from.current = value;
      setShown(value);
      return;
    }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / durationMs);
      const eased = 1 - Math.pow(1 - k, 3);
      setShown(a + (value - a) * eased);
      if (k < 1) raf = requestAnimationFrame(step);
      else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, durationMs]);
  return shown;
}

/** Leader of a race by votes (null when nobody has votes). */
export function leaderOf(candidates: { name: string; votes: number; party_code: string }[]) {
  const top = [...candidates].sort((x, y) => y.votes - x.votes)[0];
  return top && top.votes > 0 ? top : null;
}
