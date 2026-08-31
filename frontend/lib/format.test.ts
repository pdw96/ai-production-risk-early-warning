import { describe, expect, it } from "vitest";

import { format_date, format_percentage, format_quantity } from "./format";

describe("operation formatters", () => {
  it("formats quantities with Korean numeric grouping", () => {
    expect(format_quantity(1234.5)).toBe("1,234.5개");
  });

  it("formats percentages to one decimal place", () => {
    expect(format_percentage(81.25)).toBe("81.3%");
  });

  it("formats API dates as YYYY.MM.DD and handles missing estimates", () => {
    expect(format_date("2026-08-31")).toBe("2026.08.31");
    expect(format_date(null)).toBe("예측 불가");
  });
});
