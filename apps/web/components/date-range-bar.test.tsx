import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { routerReplace, searchParams } from "../vitest.setup";
import { DateRangeBar } from "./date-range-bar";

describe("date range filters", () => {
  beforeEach(() => {
    routerReplace.mockClear();
    const keys = [...searchParams.keys()];
    for (const key of keys) searchParams.delete(key);
  });

  it("writes preset and compare into the URL and never sends tenant identity", () => {
    render(<DateRangeBar />);
    fireEvent.change(screen.getByLabelText("Date range"), { target: { value: "last_7" } });
    fireEvent.change(screen.getByLabelText("Compare"), { target: { value: "previous_month" } });
    expect(routerReplace).toHaveBeenCalledTimes(2);
    const urls = routerReplace.mock.calls.map((call) => String(call[0]));
    expect(urls[0]).toContain("preset=last_7");
    expect(urls[1]).toContain("compare=previous_month");
    expect(urls.join(" ")).not.toContain("merchant");
    expect(urls.join(" ")).not.toContain("tenant");
  });

  it("shows custom from/to inputs when preset is custom", () => {
    searchParams.set("preset", "custom");
    render(<DateRangeBar />);
    expect(screen.getByLabelText("From")).toBeTruthy();
    expect(screen.getByLabelText("To")).toBeTruthy();
  });
});
