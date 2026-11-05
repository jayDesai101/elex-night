export type Theme = "dark" | "light";
const KEY = "elex-theme";

import { useEffect, useState } from "react";

/** Current theme, kept in sync with the class on <html> (set by the Hero toggle). */
export function useTheme(): Theme {
  const read = (): Theme =>
    document.documentElement.classList.contains("light") ? "light" : "dark";
  const [theme, setTheme] = useState<Theme>(read);
  useEffect(() => {
    const obs = new MutationObserver(() => setTheme(read()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return theme;
}

export function getTheme(): Theme {
  try {
    return localStorage.getItem(KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle("light", theme === "light");
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* private mode: theme just isn't remembered */
  }
}
