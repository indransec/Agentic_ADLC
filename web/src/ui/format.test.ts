// Mirrors adlc.ui.format (the Streamlit helpers this replaces).
import { describe, expect, it } from "vitest";

import { ago, duration, kpiValue, label, money, when } from "./format";

describe("format", () => {
  it("durations", () => {
    expect(duration(42)).toBe("42s");
    expect(duration(3725)).toBe("1h 2m");
    expect(duration(90061)).toBe("1d 1h 1m");
  });

  it("money keeps four decimals under a dollar", () => {
    expect(money("0.0125")).toBe("$0.0125");
    expect(money(1234.5)).toBe("$1,234.50");
    expect(money(null)).toBe("—");
    expect(money("n/a")).toBe("n/a");
  });

  it("times read in UTC", () => {
    expect(when("2026-11-19T14:05:00.000000Z")).toBe("19 Nov 2026, 14:05 UTC");
    expect(when("2026-11-19T15:05:00+01:00")).toBe("19 Nov 2026, 14:05 UTC");
    expect(when(null)).toBe("—");
    expect(when("soon")).toBe("soon");
  });

  it("ago", () => {
    const now = new Date("2026-11-19T15:00:00Z");
    expect(ago("2026-11-19T14:55:00Z", now)).toBe("5m ago");
    expect(ago("2026-11-19T17:00:00Z", now)).toBe("in 2h");
    expect(ago("2026-11-19T15:00:30Z", now)).toBe("just now");
  });

  it("KPI values", () => {
    expect(kpiValue({ value: null, unit: "ratio" })).toBe("no data");
    expect(kpiValue({ value: 0.75, unit: "ratio" })).toBe("75%");
    expect(kpiValue({ value: 3725, unit: "seconds" })).toBe("1h 2m");
    expect(kpiValue({ value: 3, unit: "count" })).toBe("3");
  });

  it("column names read as words", () => {
    expect(label("usecase_id")).toBe("Use case ID");
    expect(label("cost_usd")).toBe("Cost USD");
  });
});
