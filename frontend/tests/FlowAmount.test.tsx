import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FlowAmount } from "../src/components/FlowAmount";

// Issue #17: Review's proposal/disagreement tables only have room for one Amount
// column (unlike TransactionsPage's separate Out-flow/In-flow columns), so a bare
// number gave no way to tell inflow from outflow at a glance.
describe("FlowAmount", () => {
  it("shows an outflow with a minus sign", () => {
    render(<FlowAmount outFlow="45.20" inFlow={null} />);
    expect(screen.getByText("-45.20")).toBeInTheDocument();
  });

  it("shows an inflow with a plus sign", () => {
    render(<FlowAmount outFlow={null} inFlow="5000.00" />);
    expect(screen.getByText("+5000.00")).toBeInTheDocument();
  });

  it("renders nothing when neither is set", () => {
    const { container } = render(<FlowAmount outFlow={null} inFlow={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
