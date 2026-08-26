import { describe, expect, it } from "vitest";
import { apiUrl, fetchHealth } from "./api";

describe("apiUrl", () => {
  it("joins the API origin and path", () => {
    expect(apiUrl("/health")).toBe("http://localhost:8000/health");
  });
});

describe("fetchHealth", () => {
  it("parses a successful health payload", async () => {
    const fetcher: typeof fetch = async () =>
      new Response(JSON.stringify({ status: "ok", version: "0.1.0" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    await expect(fetchHealth(fetcher)).resolves.toEqual({
      status: "ok",
      version: "0.1.0",
    });
  });
});
