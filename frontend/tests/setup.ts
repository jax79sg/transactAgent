import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";

// vitest 4 changed vi.restoreAllMocks(): it now only restores spies made with vi.spyOn and no longer clears the call
// history of automocked modules (vi.mock("../src/api/...")), so calls made in one test leaked into the next ("expected
// to be called 1 times, but got 3"). vitest 3's restoreAllMocks did both; this puts the reset back, once, for every
// test. Test files' own afterEach hooks (restoreAllMocks) run first, then this one.
afterEach(() => {
  vi.resetAllMocks();
});

// jsdom doesn't implement scrollIntoView, which @radix-ui/react-select calls when
// its content actually opens (e.g. via defaultOpen) -- no test exercised that path
// until one actually opened the dropdown, so this went unnoticed until now.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom doesn't implement matchMedia, which ThemeContext calls on mount to read the OS
// color-scheme preference -- any test rendering a ThemeProvider (directly, or via NavBar/
// DashboardPage) needs this to exist. A no-op "always light, no listeners" default is
// fine here; tests that need to exercise OS-preference behavior override this locally
// (see ThemeContext.test.tsx).
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
