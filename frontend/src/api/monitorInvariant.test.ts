import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("monitor api invariant", () => {
  it("does not introduce /monitor/status calls", () => {
    const files = [
      path.resolve(__dirname, "simV2.ts"),
      path.resolve(__dirname, "businesses.ts"),
      path.resolve(__dirname, "../app/routes/BusinessSelectPage.tsx"),
      path.resolve(__dirname, "../features/simulator-v2/SimulatorV2Page.tsx"),
      path.resolve(__dirname, "../features/ledger/LedgerPage.tsx"),
      path.resolve(__dirname, "../features/signals-center/SignalsCenter.tsx"),
    ];
    const joined = files.map((f) => fs.readFileSync(f, "utf8")).join("\n");
    expect(joined.includes("/monitor/status")).toBe(false);
  });
});
