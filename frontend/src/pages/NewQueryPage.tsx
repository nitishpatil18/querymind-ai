import { Eraser, Send, Sparkles } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { TurnCard } from "../components/TurnCard";
import { Alert, Button, Card, PageHeader } from "../components/ui";
import { ApiError, api } from "../services/api";
import type { GenerateResponse } from "../types/api";

const EXAMPLES = [
  "Which 5 customers spent the most?",
  "Monthly revenue for completed orders in the last 6 months",
  "Top 10 products by units sold",
  "How many orders are in each status?",
];

export function NewQueryPage() {
  const location = useLocation();
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<GenerateResponse[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const prefill = (location.state as { question?: string } | null)?.question;
    if (prefill) setQuestion(prefill);
  }, [location.state]);

  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === "function") bottomRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length]);

  async function ask(text: string, regenerateOf?: number | null) {
    const q = text.trim();
    if (!q || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.chat({ question: q, conversation_id: conversationId, regenerate_of: regenerateOf ?? null });
      setConversationId(res.conversation_id);
      setTurns((t) => [...t, res]);
      setQuestion("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void ask(question);
  }

  function reset() {
    setTurns([]);
    setConversationId(null);
    setError(null);
    setQuestion("");
  }

  return (
    <div>
      <PageHeader
        title="New Query"
        description="Ask a question about your data in plain English. Follow-ups like “now only for 2026” reuse the context of this conversation."
        actions={
          turns.length > 0 ? (
            <Button onClick={reset} icon={<Eraser className="h-4 w-4" />}>
              New conversation
            </Button>
          ) : undefined
        }
      />

      <div className="space-y-4">
        {turns.length === 0 && (
          <Card className="p-5">
            <p className="flex items-center gap-2 text-sm font-medium text-slate-700">
              <Sparkles className="h-4 w-4 text-brand-600" aria-hidden /> Try one of these
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" onClick={() => setQuestion(ex)} className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:border-brand-600 hover:text-brand-700">
                  {ex}
                </button>
              ))}
            </div>
          </Card>
        )}

        {turns.map((t) => (
          <TurnCard key={t.history_id} turn={t} busy={loading} onRegenerate={(turn) => void ask(turn.question, turn.history_id)} />
        ))}

        {loading && (
          <div role="status" className="rounded-xl border border-slate-200 bg-white px-4 py-6 text-sm text-slate-500">
            Retrieving schema context and generating SQL…
          </div>
        )}
        {error && <Alert kind="error" title="Could not generate a query">{error}</Alert>}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={onSubmit} className="sticky bottom-0 mt-4 bg-slate-50 pb-2 pt-2">
        <div className="flex items-end gap-2 rounded-xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-brand-600">
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <textarea
            id="question"
            rows={2}
            value={question}
            maxLength={2000}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void ask(question);
              }
            }}
            placeholder={turns.length ? "Ask a follow-up…" : "Ask a question about your data…"}
            className="min-h-[3rem] flex-1 resize-none bg-transparent px-2 py-1 text-sm outline-none"
          />
          <Button type="submit" variant="primary" loading={loading} disabled={!question.trim()} icon={<Send className="h-4 w-4" />}>
            Ask
          </Button>
        </div>
      </form>
    </div>
  );
}
