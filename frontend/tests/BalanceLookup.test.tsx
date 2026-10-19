import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as balancesApi from "../src/api/balances";
import { ApiError } from "../src/api/client";
import type { BalancesResponse } from "../src/api/types";
import { BalanceLookup } from "../src/components/balances/BalanceLookup";
import { renderWithQueryClient } from "./balanceTestUtils";
import { balancesDateFixture, balancesMonthFixture, FIXTURE_ACCOUNT_IDS } from "./balancesFixtures";

vi.mock("../src/api/balances");

const getBalances = () => vi.mocked(balancesApi.getBalances);
const futureRefusal = () => new ApiError(400, { error: "date_in_future", message: "x" });

function respond(overrides: Partial<BalancesResponse> = {}): BalancesResponse {
  return { ...balancesDateFixture(), ...overrides };
}

function setup(onSetBalance = vi.fn(), onToday = vi.fn()) {
  const view = renderWithQueryClient(<BalanceLookup onSetBalance={onSetBalance} onToday={onToday} />);
  return { ...view, onSetBalance, onToday };
}

describe("BalanceLookup", () => {
  beforeEach(() => {
    // Only the clock is faked, so promises and timers behave normally. 10:00 on 18 Oct 2026 in the machine's own zone.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 18, 10, 0, 0));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  describe("the first question", () => {
    it("asks for the browser's local calendar date, then shows the answer with its heading and its parts", async () => {
      getBalances().mockResolvedValue(respond({ resolvedDate: "2026-10-18" }));
      setup();

      await waitFor(() => expect(screen.getByTestId("lookup-heading")).toHaveTextContent("Balances at the end of 18 Oct 2026"));
      expect(getBalances()).toHaveBeenCalledWith({ date: "2026-10-18" });
      expect(screen.getByTestId("ingested-through")).toBeInTheDocument();
      expect(screen.getByTestId("unlinked-notice")).toBeInTheDocument();
      expect(screen.getByTestId("balances-table")).toBeInTheDocument();
    });

    it("shows a loading heading before the first answer arrives", () => {
      getBalances().mockReturnValue(new Promise(() => {}));
      setup();
      expect(screen.getByTestId("lookup-heading")).toHaveTextContent("Loading balances");
    });

    it("asks again, once and quietly, for the day before when the API says the date is in the future", async () => {
      getBalances().mockRejectedValueOnce(futureRefusal()).mockResolvedValueOnce(respond({ resolvedDate: "2026-10-17" }));
      setup();

      await waitFor(() => expect(screen.getByTestId("lookup-heading")).toHaveTextContent("Balances at the end of 17 Oct 2026"));
      expect(getBalances().mock.calls.map(([params]) => params)).toEqual([{ date: "2026-10-18" }, { date: "2026-10-17" }]);
      expect(screen.queryByTestId("balances-error")).not.toBeInTheDocument();
      expect(screen.getByTestId("lookup-date-input")).toHaveValue("2026-10-17");
    });

    it("does not hide the error while it is quietly retrying, and shows a second refusal like any other", async () => {
      getBalances().mockRejectedValue(futureRefusal());
      setup();

      expect(await screen.findByTestId("balances-error")).toHaveTextContent("That is after today. Choose today or an earlier date.");
      expect(getBalances()).toHaveBeenCalledTimes(2); // once, and the one retry
    });

    it("does NOT retry for a date the owner chose", async () => {
      getBalances().mockResolvedValueOnce(respond());
      setup();
      await screen.findByTestId("balances-result");
      getBalances().mockRejectedValue(futureRefusal());

      fireEvent.change(screen.getByTestId("lookup-date-input"), { target: { value: "2026-05-02" } });

      expect(await screen.findByTestId("balances-error")).toBeInTheDocument();
      expect(getBalances()).toHaveBeenCalledTimes(2); // the first answer, and the owner's one request, not retried
    });
  });

  describe("what the API's answer controls", () => {
    it("tells the parent the API's today, and uses it as the latest date the input accepts", async () => {
      getBalances().mockResolvedValue(respond({ today: "2026-10-18" }));
      const { onToday } = setup();
      await screen.findByTestId("balances-result");
      expect(onToday).toHaveBeenCalledWith("2026-10-18");
      expect(screen.getByTestId("lookup-date-input")).toHaveAttribute("max", "2026-10-18");
      expect(screen.getByTestId("lookup-date-input")).toHaveAttribute("min", "2000-01-01");
    });

    it("sends the Today button to the API's today, not the browser's", async () => {
      getBalances().mockResolvedValue(respond({ today: "2026-10-19", resolvedDate: "2026-07-31" })); // the API is a day ahead
      setup();
      await screen.findByTestId("balances-result");
      await userEvent.setup().click(screen.getByTestId("lookup-today-button"));
      await waitFor(() => expect(getBalances()).toHaveBeenLastCalledWith({ date: "2026-10-19" }));
    });
  });

  describe("changing the date", () => {
    it("looks up the new date, keeping the old result on screen, dimmed, until the new one arrives", async () => {
      getBalances().mockResolvedValueOnce(respond());
      setup();
      await screen.findByTestId("balances-result");
      getBalances().mockReturnValue(new Promise(() => {}));

      fireEvent.change(screen.getByTestId("lookup-date-input"), { target: { value: "2026-05-02" } });

      await waitFor(() => expect(getBalances()).toHaveBeenLastCalledWith({ date: "2026-05-02" }));
      const result = screen.getByTestId("balances-result");
      expect(result).toHaveAttribute("aria-busy", "true");
      expect(result.className).toContain("opacity-60");
      expect(screen.getByTestId("balances-table")).toBeInTheDocument();
    });

    it("ignores an incomplete or out-of-range value rather than asking the API about it", async () => {
      getBalances().mockResolvedValue(respond());
      setup();
      await screen.findByTestId("balances-result");
      fireEvent.change(screen.getByTestId("lookup-date-input"), { target: { value: "" } });
      fireEvent.change(screen.getByTestId("lookup-date-input"), { target: { value: "1999-12-31" } });
      fireEvent.change(screen.getByTestId("lookup-date-input"), { target: { value: "2026-12-31" } });
      expect(getBalances()).toHaveBeenCalledTimes(1);
    });

    it("jumps to the last ingested date when the date asked for is later", async () => {
      getBalances().mockResolvedValue(respond({ resolvedDate: "2026-10-18", ingestedThroughDate: "2026-07-31" }));
      setup();
      await userEvent.setup().click(await screen.findByTestId("ingested-through-jump"));
      await waitFor(() => expect(getBalances()).toHaveBeenLastCalledWith({ date: "2026-07-31" }));
    });
  });

  describe("by month", () => {
    async function inMonthMode(first: BalancesResponse = respond({ resolvedDate: "2026-07-31" })) {
      getBalances().mockResolvedValue(first);
      const view = setup();
      await screen.findByTestId("balances-result");
      const user = userEvent.setup();
      await user.click(screen.getByTestId("lookup-mode-month"));
      return { ...view, user };
    }

    it("switches to the month of the result, so the view does not jump", async () => {
      await inMonthMode();
      await waitFor(() => expect(getBalances()).toHaveBeenLastCalledWith({ month: "2026-07" }));
      expect(screen.getByTestId("lookup-month-select")).toHaveValue("7");
      expect(screen.getByTestId("lookup-year-select")).toHaveValue("2026");
      expect(screen.queryByTestId("lookup-date-input")).not.toBeInTheDocument();
      expect(screen.getByTestId("lookup-mode-month")).toHaveAttribute("aria-pressed", "true");
    });

    it("words the heading for the current month so far, from the response", async () => {
      getBalances().mockImplementation(async (params) => ("month" in params ? balancesMonthFixture() : respond({ resolvedDate: "2026-10-18" })));
      setup();
      await screen.findByTestId("balances-result");
      await userEvent.setup().click(screen.getByTestId("lookup-mode-month"));
      await waitFor(() =>
        expect(screen.getByTestId("lookup-heading")).toHaveTextContent("Balances for October 2026 so far (to 18 Oct 2026, today)"),
      );
    });

    it("looks up another month and another year", async () => {
      const { user } = await inMonthMode();
      await user.selectOptions(screen.getByTestId("lookup-month-select"), "5");
      await waitFor(() => expect(getBalances()).toHaveBeenLastCalledWith({ month: "2026-05" }));
      await user.selectOptions(screen.getByTestId("lookup-year-select"), "2025");
      await waitFor(() => expect(getBalances()).toHaveBeenLastCalledWith({ month: "2025-05" }));
    });

    it("does not offer a month after the current one, and pulls the month back when the year becomes this year", async () => {
      const { user } = await inMonthMode();
      const months = within(screen.getByTestId("lookup-month-select")).getAllByRole("option");
      expect(months.filter((o) => (o as HTMLOptionElement).disabled).map((o) => o.textContent)).toEqual(["November", "December"]);

      await user.selectOptions(screen.getByTestId("lookup-year-select"), "2025");
      await user.selectOptions(screen.getByTestId("lookup-month-select"), "12"); // December 2025 is allowed
      await waitFor(() => expect(getBalances()).toHaveBeenLastCalledWith({ month: "2025-12" }));
      await user.selectOptions(screen.getByTestId("lookup-year-select"), "2026");
      await waitFor(() => expect(getBalances()).toHaveBeenLastCalledWith({ month: "2026-10" })); // not December 2026
    });

    it("lists the years back to 2000", async () => {
      await inMonthMode();
      const years = within(screen.getByTestId("lookup-year-select")).getAllByRole("option");
      expect(years[0]).toHaveTextContent("2026");
      expect(years[years.length - 1]).toHaveTextContent("2000");
    });

    it("goes back to a date lookup on the day the month result resolved to", async () => {
      const { user } = await inMonthMode(respond({ resolvedDate: "2026-07-31" }));
      getBalances().mockResolvedValue(respond({ resolvedDate: "2026-07-31", requestedMonth: "2026-07" }));
      await waitFor(() => expect(getBalances()).toHaveBeenLastCalledWith({ month: "2026-07" }));
      await user.click(screen.getByTestId("lookup-mode-date"));
      expect(screen.getByTestId("lookup-date-input")).toHaveValue("2026-07-31");
    });
  });

  describe("when it goes wrong", () => {
    it("shows the sentence and a Try again that asks once more, and does not retry on its own", async () => {
      getBalances().mockRejectedValueOnce(new ApiError(500, { error: "unknown", message: "Internal Server Error" }));
      setup();
      expect(await screen.findByTestId("balances-error")).toHaveTextContent("The server had a problem. Please try again.");
      expect(screen.queryByTestId("balances-result")).not.toBeInTheDocument();
      expect(getBalances()).toHaveBeenCalledTimes(1);

      getBalances().mockResolvedValue(respond());
      await userEvent.setup().click(screen.getByTestId("balances-retry"));
      expect(await screen.findByTestId("balances-table")).toBeInTheDocument();
      expect(screen.queryByTestId("balances-error")).not.toBeInTheDocument();
    });

    it("says when the server could not be reached", async () => {
      getBalances().mockRejectedValue(new TypeError("Failed to fetch"));
      setup();
      expect(await screen.findByTestId("balances-error")).toHaveTextContent("Couldn't reach the server.");
    });
  });

  it("passes the Set balance prompt up with the account", async () => {
    getBalances().mockResolvedValue(respond());
    const { onSetBalance } = setup();
    await userEvent.setup().click(await screen.findByTestId(`set-balance-${FIXTURE_ACCOUNT_IDS.fresh}`));
    expect(onSetBalance).toHaveBeenCalledWith(FIXTURE_ACCOUNT_IDS.fresh);
  });
});
