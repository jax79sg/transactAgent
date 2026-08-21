# Dark Mode — Clarifying Questions

Source: GitHub issue #1 ("Need a dark mode") — "The current theme is not pleasant for my group of users. Please create a dark mode."

Please answer each question by filling in the letter choice after the `[Answer]:` tag. If none of the options match, choose the last option (Other) and describe your preference. Let me know when you're done.

## Question 1
How should users switch between light and dark mode?

A) Manual toggle only (a button/switch in the UI; user's explicit choice always wins)

B) Follow the OS/browser preference automatically (`prefers-color-scheme`), no manual override

C) Both — default to OS preference, but let the user override with a manual toggle

D) Other (please describe after [Answer]: tag below)

[Answer]:C 

## Question 2
Where should the mode toggle live?

A) In the NavBar (always visible, next to the other nav controls/badges)

B) In the Settings page (`SettingsPage.tsx`), alongside other application settings

C) Both — a quick toggle in the NavBar, with the same preference also visible/settable on the Settings page

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 3
Should the chosen mode be remembered across sessions?

A) Yes, persist in the browser only (`localStorage`) — per-device, no backend involvement

B) Yes, persist per-user on the backend (survives switching devices/browsers)

C) No, always start from OS preference every session (only relevant if Q1=B/C)

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 4
What scope should dark mode cover?

A) The entire application — every page and component (NavBar, all 7 pages, all dialogs/tables/panels), including the Dashboard's Chart.js charts

B) Everything except charts — charts stay on their current light rendering for now

C) A specific subset of pages only (please name them under Other)

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 5
This app currently has zero dark-mode styling (plain Tailwind, no `dark:` variants anywhere, no theme config). How much visual refinement should this first version aim for?

A) Functional pass — swap light colors for a sensible dark palette using Tailwind's `dark:` variants everywhere color is hardcoded today (backgrounds, text, borders, table zebra striping, badges/status pills); no new design system

B) Polished pass — functional pass plus deliberate color/contrast design review (e.g. accessible contrast ratios, distinct dark-mode accent colors) before calling it done

C) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 6
Any existing color/contrast constraints or preferences for the dark palette (e.g. a specific dark background hex, must match a brand color, avoid pure black, etc.)?

A) No preference — use your judgment (common dark-UI conventions: near-black/dark-slate background, light-gray text, muted borders)

B) Yes (please describe after [Answer]: tag below)

[Answer]: A
