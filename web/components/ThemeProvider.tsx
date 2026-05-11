"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode
} from "react";

export type ThemeMode = "day" | "night" | "auto";

const THEME_STORAGE_KEY = "rpgforge.themeMode";

type ThemeContextValue = {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  cycleMode: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function parseThemeMode(value: string | null): ThemeMode {
  if (value === "night" || value === "auto" || value === "day") {
    return value;
  }

  return "day";
}

function resolveTheme(mode: ThemeMode, systemPrefersDark: boolean): "day" | "night" {
  return mode === "night" || (mode === "auto" && systemPrefersDark) ? "night" : "day";
}

function applyThemeMode(mode: ThemeMode) {
  const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const theme = resolveTheme(mode, mediaQuery.matches);

  document.documentElement.dataset.themeMode = mode;
  document.documentElement.dataset.theme = theme;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>("day");
  const [hasHydrated, setHasHydrated] = useState(false);
  const hasManualModeRef = useRef(false);

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      if (hasManualModeRef.current) {
        return;
      }

      const savedMode = parseThemeMode(
        document.documentElement.dataset.themeMode ??
          window.localStorage.getItem(THEME_STORAGE_KEY)
      );

      setModeState(savedMode);
      setHasHydrated(true);
      applyThemeMode(savedMode);
    });

    return () => window.cancelAnimationFrame(frameId);
  }, []);

  useEffect(() => {
    if (!hasHydrated) {
      return;
    }

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleSystemChange = () => applyThemeMode(mode);

    window.localStorage.setItem(THEME_STORAGE_KEY, mode);
    applyThemeMode(mode);

    mediaQuery.addEventListener("change", handleSystemChange);

    return () => mediaQuery.removeEventListener("change", handleSystemChange);
  }, [hasHydrated, mode]);

  const setMode = useCallback((nextMode: ThemeMode) => {
    hasManualModeRef.current = true;
    setModeState(nextMode);
    setHasHydrated(true);
  }, []);

  const cycleMode = useCallback(() => {
    hasManualModeRef.current = true;
    setModeState((currentMode) => {
      if (currentMode === "day") {
        return "night";
      }

      if (currentMode === "night") {
        return "auto";
      }

      return "day";
    });
    setHasHydrated(true);
  }, []);

  const contextValue = useMemo(
    () => ({
      mode,
      setMode,
      cycleMode
    }),
    [cycleMode, mode, setMode]
  );

  return <ThemeContext.Provider value={contextValue}>{children}</ThemeContext.Provider>;
}

export function useThemeMode() {
  const context = useContext(ThemeContext);

  if (!context) {
    throw new Error("useThemeMode must be used inside ThemeProvider");
  }

  return context;
}
