import { useEffect, useState } from "react";

export type ThemePref = "light" | "dark" | "system";

const KEY = "theme";
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

export function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";                     // storage blocked: follow the system
  }
}

export function resolveTheme(pref: ThemePref, systemDark: boolean): "light" | "dark" {
  return pref === "system" ? (systemDark ? "dark" : "light") : pref;
}

/** Keeps <html class="dark"> in sync with the saved choice and, for "system", the OS setting. */
export function useTheme() {
  const [pref, setPref] = useState<ThemePref>(readPref);

  useEffect(() => {
    try {
      if (pref === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, pref);
    } catch {
      // not saved; still applied for this session
    }
    const m = media();
    const apply = () => document.documentElement.classList.toggle("dark", resolveTheme(pref, m.matches) === "dark");
    apply();
    if (pref !== "system") return;
    m.addEventListener("change", apply);
    return () => m.removeEventListener("change", apply);
  }, [pref]);

  return [pref, setPref] as const;
}
