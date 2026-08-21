import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

const THEME_STORAGE_KEY = "transactagent_theme";

export type Theme = "light" | "dark";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function prefersDarkOS(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function getStoredTheme(): Theme | null {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : null;
}

function resolveInitialTheme(): Theme {
  return getStoredTheme() ?? (prefersDarkOS() ? "dark" : "light");
}

function applyThemeToDocument(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Matches the inline script in index.html (NFR-DM-3), which already applied this
  // same resolution to <html> before first paint in the real app -- this just brings
  // React's state in sync with what's already on screen, no flash.
  const [theme, setThemeState] = useState<Theme>(resolveInitialTheme);

  // Defensive: applies the same resolution again on mount, idempotently, in case this
  // provider is ever mounted somewhere index.html's script didn't run first (e.g. tests).
  useEffect(() => {
    applyThemeToDocument(theme);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setTheme = useCallback((next: Theme) => {
    localStorage.setItem(THEME_STORAGE_KEY, next);
    applyThemeToDocument(next);
    setThemeState(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === "dark" ? "light" : "dark");
  }, [theme, setTheme]);

  // Keep following the live OS preference (FR-DM-2), but only until the user makes an
  // explicit choice (FR-DM-4) -- once a value is stored, this stops overriding it.
  useEffect(() => {
    if (getStoredTheme()) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent) => {
      if (getStoredTheme()) return; // an explicit choice landed in the meantime
      const next: Theme = event.matches ? "dark" : "light";
      applyThemeToDocument(next);
      setThemeState(next);
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  // Cross-tab sync (FR-DM-8): a toggle made in another tab updates this tab too.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY) return;
      if (event.newValue !== "light" && event.newValue !== "dark") return;
      applyThemeToDocument(event.newValue);
      setThemeState(event.newValue);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
