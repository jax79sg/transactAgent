# Issue #57 "Balance cannot be set again": plan

Branch `57-change-balance`. Frontend SPA unit only (the API already replaces a balance). Test first, then code; tick each step as it is done.

## What the owner needs
1. A balance that was set wrongly can be changed, and the way to do it is where the balance is shown.
2. A balance can be set again (a different amount, or the same account re-anchored on a different date) without retyping what has not changed.

## Decisions (made by me, as the owner asked for the issue to be resolved; each is easy to reverse in review)
- A row of the balances table that has a balance gets a **Change balance** button (`change-balance-<id>`) in its Account cell (first column, so it is visible on a phone without scrolling the table sideways). Same one-write-at-a-time rule as every other account action.
- The balance dialog, when an account already has a balance, **starts with that balance and that date filled in**, with the amount selected so typing overwrites it. The carried-over date applies only to a first balance. This removes the trap where leaving the date alone silently moves the balance to today.
- Wording follows the owner's word: the Accounts section's **Replace balance** becomes **Change balance**; the dialog reads "Change the balance of <name>" and its button "Save change". "Currently X on D. Saving replaces it." stays.
- Not added: deleting a balance (not asked for); allowing more than one balance per account (the model is one anchor per account; changing it is how an account is re-anchored).

## Steps
- [x] 1. Tests first: BalancesTable (button on rows with a balance, none on "Anchor required" rows, calls `onSetBalance`, disabled while a write is in flight); BalanceDialog (replace mode starts with the current amount and date, amount selected, "Change the balance of", "Save change"; a first balance still starts empty on the given date); AccountsSection label; BalancesTab (the table's button opens the dialog with the current values and a changed amount is sent). Run: the new cases fail.
- [x] 2. `BalancesTable.tsx`: the button.
- [x] 3. `BalanceDialog.tsx`: prefill, select on focus, wording.
- [x] 4. `AccountsSection.tsx`: label.
- [x] 5. e2e (`frontend/e2e/balances.spec.ts`): change a balance from the table; the dialog starts with the current figure and date; the new figure shows. Fix the one regex that names the old label.
- [x] 6. Amend the approved design documents in place (frontend-components.md, business-logic-model.md) and the code summary.
- [x] 7. Full frontend suite, `tsc`, `eslint`, `vite build`; confirm the new tests fail without the change (stash the source files, run, restore).
- [x] 8. Dispatch the nightly e2e on the branch and read the result.
- [x] 9. PR with "Closes #57"; bind it, turn on auto-fix; update audit and state.
