import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { IngestedThrough, UnlinkedNotice } from "../src/components/balances/IngestedThrough";
import { describeUnlinked } from "../src/lib/balances";
import { balancesDateFixture } from "./balancesFixtures";

describe("IngestedThrough", () => {
  it("says how far the transactions go", () => {
    render(<IngestedThrough resolvedDate="2026-07-31" ingestedThroughDate="2026-09-30" onJumpTo={vi.fn()} />);
    expect(screen.getByTestId("ingested-through")).toHaveTextContent("Transactions are ingested through 30 Sep 2026.");
    expect(screen.queryByTestId("ingested-through-jump")).not.toBeInTheDocument();
    expect(screen.getByTestId("ingested-through").className).not.toContain("amber");
  });

  it("is plain when the date asked for is exactly the last ingested day", () => {
    render(<IngestedThrough resolvedDate="2026-09-30" ingestedThroughDate="2026-09-30" onJumpTo={vi.fn()} />);
    expect(screen.queryByTestId("ingested-through-jump")).not.toBeInTheDocument();
  });

  it("warns, in words and amber, when the date is later, and offers the last real date", async () => {
    const onJumpTo = vi.fn();
    render(<IngestedThrough resolvedDate="2026-10-18" ingestedThroughDate="2026-09-30" onJumpTo={onJumpTo} />);
    const line = screen.getByTestId("ingested-through");
    expect(line).toHaveTextContent("This date is later, so the figures don't include any activity after it.");
    expect(line.className).toContain("amber");
    await userEvent.setup().click(screen.getByTestId("ingested-through-jump"));
    expect(screen.getByTestId("ingested-through-jump")).toHaveTextContent("Show 30 Sep 2026");
    expect(onJumpTo).toHaveBeenCalledWith("2026-09-30");
  });

  it("says so when nothing has been ingested at all", () => {
    render(<IngestedThrough resolvedDate="2026-10-18" ingestedThroughDate={null} onJumpTo={vi.fn()} />);
    expect(screen.getByTestId("ingested-through")).toHaveTextContent("No transactions have been ingested yet.");
  });
});

describe("UnlinkedNotice", () => {
  it("renders nothing without a notice", () => {
    const { container } = render(<UnlinkedNotice notice={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("words the real notice, with no button, since it is information only", () => {
    const notice = balancesDateFixture().unlinkedTransactions;
    render(<UnlinkedNotice notice={notice} />);
    const element = screen.getByTestId("unlinked-notice");
    expect(element).toHaveTextContent(describeUnlinked(notice!));
    expect(element).toHaveTextContent("2 transactions from GXS Bank, dated 15 Jul to 31 Jul 2026 (net SGD 100.00 and USD -5.50)");
    expect(element.querySelector("button")).toBeNull();
  });
});
