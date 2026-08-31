import { describe, expect, it } from "vitest";
import { isValidShopDomain, normalizeShopDomain } from "./shop-domain";

describe("shop domain", () => {
  it("accepts myshopify domains and rejects others", () => {
    expect(isValidShopDomain("Acme-Store.myshopify.com")).toBe(true);
    expect(normalizeShopDomain("https://acme-store.myshopify.com/admin")).toBe(
      "acme-store.myshopify.com",
    );
    expect(isValidShopDomain("acme.com")).toBe(false);
    expect(isValidShopDomain("not a shop")).toBe(false);
  });
});
