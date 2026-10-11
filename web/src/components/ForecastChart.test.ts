import { describe, expect, it } from "vitest";
import { niceTicks } from "./ForecastChart";

describe("niceTicks", () => {
  it("picks round steps and keeps zero", () => {
    expect(niceTicks(-852, 4800)).toEqual([0, 2000, 4000]);
    expect(niceTicks(0, 5200)).toEqual([0, 2000, 4000]);
    expect(niceTicks(-1600, 2400)).toEqual([-1000, 0, 1000, 2000]);
  });
});
