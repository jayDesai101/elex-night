import { useEffect, useRef, useState } from "react";

/** True for `ms` after `key` changes (not on first render): a card briefly glows when its
 * data updates. */
export function useFlash(key: unknown, ms = 1500): boolean {
  const prev = useRef(key);
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (Object.is(prev.current, key)) return;
    prev.current = key;
    setOn(true);
    const t = setTimeout(() => setOn(false), ms);
    return () => clearTimeout(t);
  }, [key, ms]);
  return on;
}

/** Class names for a flashing card. */
export const flashClass = (on: boolean) => (on ? "flash-update" : "");
