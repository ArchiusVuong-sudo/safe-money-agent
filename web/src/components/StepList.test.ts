import { describe, expect, it } from "vitest";
import type { Step } from "../lib/types";
import { toItems } from "./StepList";

const step = (seq: number, type: string, name = "", data: Record<string, unknown> = {}): Step => ({
  seq,
  type,
  name,
  data,
  ms: 1,
  at: "2026-10-11T00:00:00Z",
});

describe("toItems", () => {
  it("pairs each tool call with its result", () => {
    const items = toItems(
      [step(1, "tool_call", "forecast"), step(2, "tool_call", "get_accounts"), step(3, "tool_result", "forecast"), step(4, "tool_result", "get_accounts")],
      false,
    );
    expect(items.map((i) => i.kind)).toEqual(["tool", "tool"]);
    expect(items[0]!.kind === "tool" && items[0]!.result?.seq).toBe(3);
  });

  it("shows a waiting row while an approval is open", () => {
    const perm = step(1, "permission", "move_money", { decision: "ask_user", approval_id: "a1" });
    expect(toItems([perm], true).map((i) => i.kind)).toEqual(["step", "waiting"]);
    expect(toItems([perm, step(2, "approval", "move_money", { approval_id: "a1" })], true).map((i) => i.kind)).toEqual(["step", "step"]);
    expect(toItems([perm], false).map((i) => i.kind)).toEqual(["step"]);
  });
});
