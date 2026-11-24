import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../services/api";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({ ok: status < 400, status, text: async () => (typeof body === "string" ? body : JSON.stringify(body)) });
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("api client", () => {
  it("posts JSON to the chat endpoint", async () => {
    const fetchFn = stubFetch(200, { history_id: 1 });
    await api.chat({ question: "q", conversation_id: null });
    const [url, init] = fetchFn.mock.calls[0];
    expect(url).toBe("/api/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ question: "q", conversation_id: null });
  });

  it("maps structured backend errors", async () => {
    stubFetch(422, { error: { code: "validation_error", message: "Only SELECT is allowed.", details: { rule: "x" } } });
    await expect(api.execute({ sql: "DELETE FROM t" })).rejects.toMatchObject({ name: "ApiError", status: 422, code: "validation_error", message: "Only SELECT is allowed." });
  });

  it("handles non-JSON proxy errors", async () => {
    stubFetch(502, "<html>Bad gateway</html>");
    await expect(api.health()).rejects.toMatchObject({ status: 502, message: "Request failed (502)." });
  });

  it("reports an unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await api.health().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("network_error");
  });
});
