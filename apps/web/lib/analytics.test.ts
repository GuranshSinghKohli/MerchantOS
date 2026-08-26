import { describe, expect, it } from "vitest";
import { analyticsSearch, formatMoney, formatPct, isQueryReady } from "./analytics";

describe("analytics formatters", () => {
  it("formats money and missing AOV", () => {
    expect(formatMoney("100.00")).toContain("100");
    expect(formatMoney(null)).toBe("—");
  });

  it("formats growth and undefined baselines", () => {
    expect(formatPct("12.50")).toBe("+12.5%");
    expect(formatPct("-4.00")).toBe("-4.0%");
    expect(formatPct(null)).toBe("—");
  });

  it("does not treat incomplete custom ranges as ready", () => {
    expect(isQueryReady({ preset: "last_7", compare: "previous_period" })).toBe(true);
    expect(isQueryReady({ preset: "custom", compare: "previous_period" })).toBe(false);
    expect(
      isQueryReady({ preset: "custom", compare: "previous_period", from: "2020-01-01", to: "2020-01-31" }),
    ).toBe(true);
  });

  it("keeps tenant identity out of query strings", () => {
    const search = analyticsSearch({ preset: "last_7", compare: "previous_period" });
    expect(search).not.toContain("merchant");
    expect(search).not.toContain("tenant");
  });
});
