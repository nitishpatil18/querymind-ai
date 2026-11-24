import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResultsTable } from "../components/ResultsTable";
import { TurnCard } from "../components/TurnCard";
import { NewQueryPage } from "../pages/NewQueryPage";
import { ApiError, api } from "../services/api";
import { makeResult, makeTurn } from "./fixtures";

// Recharts needs real layout measurements, which jsdom does not provide.
vi.mock("recharts", async () => {
  const React = await import("react");
  const Stub = ({ children }: { children?: React.ReactNode }) => React.createElement("div", null, children);
  return {
    ResponsiveContainer: Stub,
    BarChart: Stub,
    LineChart: Stub,
    PieChart: Stub,
    Bar: Stub,
    Line: Stub,
    Pie: Stub,
    Cell: Stub,
    XAxis: Stub,
    YAxis: Stub,
    CartesianGrid: Stub,
    Tooltip: Stub,
    Legend: Stub,
  };
});

beforeEach(() => {
  vi.restoreAllMocks();
});

const noop = () => {};

describe("ResultsTable", () => {
  it("shows rows, counts and sorts on header click", async () => {
    render(<ResultsTable result={makeResult()} />);
    expect(screen.getByTestId("row-count")).toHaveTextContent("3 rows");
    const names = () => screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[1].textContent);
    expect(names()).toEqual(["Asha", "Ravi", "Meera"]);
    await userEvent.click(screen.getByRole("button", { name: "Sort by spend" }));
    expect(names()).toEqual(["Meera", "Ravi", "Asha"]);
    await userEvent.click(screen.getByRole("button", { name: "Sort by spend" }));
    expect(names()).toEqual(["Asha", "Ravi", "Meera"]);
  });

  it("paginates", async () => {
    const rows = Array.from({ length: 30 }, (_, i) => [`n${i}`, i]);
    render(<ResultsTable result={makeResult({ rows, row_count: 30 })} />);
    expect(screen.getByTestId("page-indicator")).toHaveTextContent("Page 1 of 2");
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByTestId("page-indicator")).toHaveTextContent("Page 2 of 2");
  });

  it("explains empty results and flags truncation", () => {
    const { rerender } = render(<ResultsTable result={makeResult({ rows: [], row_count: 0 })} />);
    expect(screen.getByText(/returned no rows/)).toBeInTheDocument();
    rerender(<ResultsTable result={makeResult({ truncated: true, max_rows: 1000 })} />);
    expect(screen.getByText(/limited to 1,000 rows/)).toBeInTheDocument();
  });
});

describe("TurnCard", () => {
  it("runs a validated query and shows the result", async () => {
    const exec = vi.spyOn(api, "execute").mockResolvedValue(makeResult());
    render(<TurnCard turn={makeTurn()} busy={false} onRegenerate={noop} />);
    expect(screen.getByText("validated read-only")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /run query/i }));
    expect(exec).toHaveBeenCalledWith({ sql: expect.stringContaining("SELECT"), history_id: 1 });
    expect(await screen.findByTestId("row-count")).toHaveTextContent("3 rows");
  });

  it("shows execution errors from the backend", async () => {
    vi.spyOn(api, "execute").mockRejectedValue(new ApiError("Query exceeded the time limit.", 400, "execution_error"));
    render(<TurnCard turn={makeTurn()} busy={false} onRegenerate={noop} />);
    await userEvent.click(screen.getByRole("button", { name: /run query/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Query exceeded the time limit.");
  });

  it("does not offer to run clarification or refusal answers", () => {
    const { rerender } = render(
      <TurnCard turn={makeTurn({ status: "clarification_needed", sql: null, validation: null, clarification_question: "Which year?" })} busy={false} onRegenerate={noop} />,
    );
    expect(screen.getByText("Which year?")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run query/i })).not.toBeInTheDocument();
    rerender(<TurnCard turn={makeTurn({ status: "cannot_answer", sql: null, validation: null, message: "No such data." })} busy={false} onRegenerate={noop} />);
    expect(screen.getByText("No such data.")).toBeInTheDocument();
  });

  it("does not offer to run SQL that failed validation", () => {
    const turn = makeTurn({
      status: "invalid_sql",
      validation: {
        valid: false,
        normalized_sql: null,
        statement_type: "delete",
        dialect: "postgres",
        tables: [],
        errors: [{ code: "forbidden_statement", message: "Only SELECT is allowed." }],
        warnings: [],
      },
    });
    render(<TurnCard turn={turn} busy={false} onRegenerate={noop} />);
    expect(screen.getByText("Only SELECT is allowed.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run query/i })).not.toBeInTheDocument();
  });

  it("reveals retrieval context with table sources", async () => {
    render(<TurnCard turn={makeTurn()} busy={false} onRegenerate={noop} />);
    await userEvent.click(screen.getByRole("button", { name: /retrieved schema context/i }));
    expect(screen.getByText("added via foreign key")).toBeInTheDocument();
    expect(screen.getByText("semantic match")).toBeInTheDocument();
  });
});

describe("NewQueryPage", () => {
  const renderPage = () =>
    render(
      <MemoryRouter>
        <NewQueryPage />
      </MemoryRouter>,
    );

  it("sends the question, keeps the conversation id for follow-ups and renders the answer", async () => {
    const chat = vi.spyOn(api, "chat").mockResolvedValue(makeTurn());
    renderPage();
    await userEvent.type(screen.getByLabelText("Your question"), "Top customers by spend");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(chat).toHaveBeenCalledWith({ question: "Top customers by spend", conversation_id: null, regenerate_of: null });
    expect(await screen.findByText("Sums order totals per customer.")).toBeInTheDocument();

    chat.mockResolvedValueOnce(makeTurn({ history_id: 2, question: "only 2026" }));
    await userEvent.type(screen.getByLabelText("Your question"), "only 2026");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(chat).toHaveBeenLastCalledWith({ question: "only 2026", conversation_id: "conv-1", regenerate_of: null });
  });

  it("surfaces backend errors and keeps the input", async () => {
    vi.spyOn(api, "chat").mockRejectedValue(new ApiError("The language model is not configured.", 503, "llm_not_configured"));
    renderPage();
    await userEvent.type(screen.getByLabelText("Your question"), "hello");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The language model is not configured.");
    expect(screen.getByLabelText("Your question")).toHaveValue("hello");
  });

  it("disables Ask for empty input", () => {
    renderPage();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
  });
});
