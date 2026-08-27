import { describe, expect, it } from "vitest";
import { changedFields, displayValue, fieldLabel } from "./actions";

describe("action display helpers", () => {
  it("names the changed product fields", () => {
    expect(
      changedFields(
        { title: "Old Mug", description: "", tags: ["old"], status: "ACTIVE" },
        { title: "New Mug", description: "", tags: ["old"], status: "ACTIVE" },
      ),
    ).toEqual(["title"]);
    expect(fieldLabel("title")).toBe("Product title");
    expect(displayValue(["summer", "sale"])).toBe("summer, sale");
  });
});
