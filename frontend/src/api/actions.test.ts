import { describe, expect, it } from "vitest";
import * as actions from "./actions";

describe("actions api exports", () => {
  it("exposes the action endpoints used by the UI", () => {
    expect(typeof actions.getActions).toBe("function");
    expect(typeof actions.refreshActions).toBe("function");
    expect(typeof actions.resolveAction).toBe("function");
    expect(typeof actions.snoozeAction).toBe("function");
    expect(typeof actions.assignAction).toBe("function");
    expect(typeof actions.fetchActionTriage).toBe("function");
    expect(typeof actions.fetchActionEvents).toBe("function");
  });
});
