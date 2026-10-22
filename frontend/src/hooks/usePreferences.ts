import { useCallback, useEffect, useState } from "react";

function read(key: string, fallback: boolean): boolean {
  try {
    const v = window.localStorage.getItem(key);
    return v === null ? fallback : v === "1";
  } catch {
    return fallback;
  }
}

function write(key: string, value: boolean): void {
  try {
    window.localStorage.setItem(key, value ? "1" : "0");
  } catch {
    /* storage unavailable (private mode) — keep in-memory state only */
  }
}

/** Boolean preference persisted in localStorage (best effort). */
export function useStoredFlag(key: string, fallback: boolean) {
  const [value, setValue] = useState(() => read(key, fallback));
  useEffect(() => write(key, value), [key, value]);
  const toggle = useCallback(() => setValue((v) => !v), []);
  return [value, setValue, toggle] as const;
}

export function usePresentationMode() {
  const [on, setOn, toggle] = useStoredFlag("rcp.presentation", false);
  useEffect(() => {
    document.documentElement.classList.toggle("presenting", on);
  }, [on]);
  return { presenting: on, setPresenting: setOn, togglePresenting: toggle };
}

export function useTheme() {
  const [light, setLight, toggle] = useStoredFlag("rcp.light", false);
  useEffect(() => {
    document.documentElement.classList.toggle("light", light);
    document.documentElement.classList.toggle("dark", !light);
  }, [light]);
  return { light, setLight, toggleTheme: toggle };
}
