import { describe, expect, it } from "vitest";
import { normalizeVendorDisplay, normalizeVendorKey } from "./vendors";

describe("vendors utils", () => {
  it("normalizes vendor keys consistently", () => {
    expect(normalizeVendorKey("ACME CO*123")).toBe("acme");
    expect(normalizeVendorKey("ACME Co. 123")).toBe("acme");
  });

  it("prefers canonical display when available", () => {
    expect(normalizeVendorDisplay("ACME CO*123", "Acme Corp")).toBe("Acme Corp");
    expect(normalizeVendorDisplay("ACME CO*123", "")).toBe("ACME CO*123");
  });
});
