import { describe, expect, it } from "vitest";
import { recommendChart } from "../utils/charts";
import { toCsv } from "../utils/csv";

describe("recommendChart", () => {
  it("uses a bar chart for category vs number", () => {
    const plan = recommendChart(["name", "total"], [["a", 1], ["b", 2], ["c", 3]]);
    expect(plan?.type).toBe("bar");
    expect(plan?.labelKey).toBe("name");
    expect(plan?.valueKeys).toEqual(["total"]);
  });

  it("uses a line chart for date axes", () => {
    const plan = recommendChart(["month", "revenue"], [["2026-01-01", 10], ["2026-02-01", 12], ["2026-03-01", 9]]);
    expect(plan?.type).toBe("line");
    expect(plan?.alternatives).toContain("bar");
  });

  it("offers a pie for a few status categories with positive values", () => {
    const plan = recommendChart(["status", "orders"], [["pending", 5], ["shipped", 7], ["completed", 20]]);
    expect(plan?.type).toBe("pie");
  });

  it("returns null when there is no numeric column or a single row", () => {
    expect(recommendChart(["a", "b"], [["x", "y"], ["z", "w"]])).toBeNull();
    expect(recommendChart(["a", "b"], [["x", 1]])).toBeNull();
    expect(recommendChart(["a"], [[1], [2]])).toBeNull();
  });

  it("does not chart id columns as measures", () => {
    const plan = recommendChart(["customer_id", "spend"], [[1, 10], [2, 20], [3, 30]]);
    expect(plan?.valueKeys).toEqual(["spend"]);
  });

  it("caps the number of plotted points", () => {
    const rows = Array.from({ length: 80 }, (_, i) => [`c${i}`, i + 1]);
    const plan = recommendChart(["c", "v"], rows);
    expect(plan?.data).toHaveLength(30);
    expect(plan?.truncated).toBe(true);
  });
});

describe("toCsv", () => {
  it("quotes commas, quotes and newlines", () => {
    expect(toCsv(["a", "b"], [['x,"y"', "line\nbreak"]])).toBe('a,b\r\n"x,""y""","line\nbreak"');
  });

  it("renders null as empty and keeps numbers", () => {
    expect(toCsv(["a", "b"], [[null, -3.5]])).toBe("a,b\r\n,-3.5");
  });

  it("neutralises spreadsheet formulas", () => {
    expect(toCsv(["a"], [["=SUM(A1)"], ["@cmd"]])).toBe("a\r\n'=SUM(A1)\r\n'@cmd");
  });
});
