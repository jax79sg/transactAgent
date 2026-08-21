import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider, useTheme } from "../src/context/ThemeContext";

const THEME_STORAGE_KEY = "transactagent_theme";

let mediaQueryListeners: Array<(event: MediaQueryListEvent) => void> = [];

function mockMatchMedia(prefersDark: boolean) {
  mediaQueryListeners = [];
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === "(prefers-color-scheme: dark)" ? prefersDark : false,
    media: query,
    addEventListener: (_event: string, listener: (event: MediaQueryListEvent) => void) => {
      mediaQueryListeners.push(listener);
    },
    removeEventListener: (_event: string, listener: (event: MediaQueryListEvent) => void) => {
      mediaQueryListeners = mediaQueryListeners.filter((l) => l !== listener);
    },
  })) as unknown as typeof window.matchMedia;
}

function fireOsPreferenceChange(matches: boolean) {
  act(() => {
    mediaQueryListeners.forEach((listener) => listener({ matches } as MediaQueryListEvent));
  });
}

// `document.documentElement`'s class is asserted directly in each test, not read back
// through a rendered span: ThemeContext applies it as a direct DOM mutation (not React
// state), so a span reading it during render would just capture a stale snapshot from
// before the mutating effect ran, rather than reflecting the real, current DOM.
function Probe() {
  const { theme, toggleTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme-value">{theme}</span>
      <button data-testid="toggle" onClick={toggleTheme}>
        toggle
      </button>
    </div>
  );
}

function renderProbe() {
  return render(
    <ThemeProvider>
      <Probe />
    </ThemeProvider>,
  );
}

describe("ThemeContext", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("defaults to the OS preference (dark) when nothing is stored", () => {
    mockMatchMedia(true);
    renderProbe();

    expect(screen.getByTestId("theme-value")).toHaveTextContent("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("defaults to the OS preference (light) when nothing is stored", () => {
    mockMatchMedia(false);
    renderProbe();

    expect(screen.getByTestId("theme-value")).toHaveTextContent("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("a manual toggle overrides the OS preference and persists to localStorage", async () => {
    mockMatchMedia(false);
    const user = userEvent.setup();
    renderProbe();

    await user.click(screen.getByTestId("toggle"));

    expect(screen.getByTestId("theme-value")).toHaveTextContent("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("an explicit stored choice wins over the OS preference on the next mount", () => {
    mockMatchMedia(true); // OS says dark
    localStorage.setItem(THEME_STORAGE_KEY, "light"); // but the user previously chose light

    renderProbe();

    expect(screen.getByTestId("theme-value")).toHaveTextContent("light");
  });

  it("stops following OS preference changes once an explicit choice is stored", async () => {
    mockMatchMedia(false);
    const user = userEvent.setup();
    renderProbe();

    await user.click(screen.getByTestId("toggle")); // explicit choice: dark
    expect(screen.getByTestId("theme-value")).toHaveTextContent("dark");

    fireOsPreferenceChange(false); // OS flips back to light -- should be ignored now

    expect(screen.getByTestId("theme-value")).toHaveTextContent("dark");
  });

  it("keeps following live OS preference changes when no explicit choice has been made", () => {
    mockMatchMedia(false);
    renderProbe();
    expect(screen.getByTestId("theme-value")).toHaveTextContent("light");

    fireOsPreferenceChange(true);

    expect(screen.getByTestId("theme-value")).toHaveTextContent("dark");
  });

  it("syncs across tabs via the storage event", () => {
    mockMatchMedia(false);
    renderProbe();
    expect(screen.getByTestId("theme-value")).toHaveTextContent("light");

    act(() => {
      localStorage.setItem(THEME_STORAGE_KEY, "dark");
      window.dispatchEvent(
        new StorageEvent("storage", { key: THEME_STORAGE_KEY, newValue: "dark", oldValue: "light" }),
      );
    });

    expect(screen.getByTestId("theme-value")).toHaveTextContent("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("ignores unrelated storage events", () => {
    mockMatchMedia(false);
    renderProbe();

    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "some_other_key", newValue: "dark" }));
    });

    expect(screen.getByTestId("theme-value")).toHaveTextContent("light");
  });
});
