import { describe, expect, it } from "vitest";
import { accountName, compactMoney, dayLabel, money, ms, signedMoney } from "./format";

describe("format", () => {
  it("formats dollars with cents", () => {
    expect(money(1672.69)).toBe("$1,672.69");
    expect(money(-304.29)).toBe("-$304.29");
    expect(money(null)).toBe("-");
  });
  it("signs and compacts", () => {
    expect(signedMoney(400)).toBe("+$400.00");
    expect(compactMoney(4800)).toBe("$4.8k");
    expect(compactMoney(-852)).toBe("-$852");
  });
  it("formats durations and account ids", () => {
    expect(ms(950)).toBe("950 ms");
    expect(ms(7634)).toBe("7.6 s");
    expect(accountName("sav")).toBe("Savings");
    expect(accountName("other")).toBe("other");
  });
  it("labels ISO dates like the server", () => {
    expect(dayLabel("2026-10-11")).toBe("Sun, Oct 11");
    expect(dayLabel("2026-10-23")).toBe("Fri, Oct 23");
    expect(dayLabel("soon")).toBe("soon");
    expect(dayLabel(undefined)).toBe("");
  });
});
