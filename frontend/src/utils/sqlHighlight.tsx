import type { ReactNode } from "react";

const KEYWORDS = new Set(
  (
    "select from where group by order having limit offset join inner left right full outer cross on as and or not in is null like ilike " +
    "between exists case when then else end distinct union all intersect except with asc desc over partition cast interval true false " +
    "using filter within lateral nulls first last"
  ).split(" "),
);

const TOKEN =
  /(--[^\n]*)|('(?:[^']|'')*')|(\b\d+(?:\.\d+)?\b)|("(?:[^"]|"")*")|([A-Za-z_][A-Za-z0-9_]*)(\s*\()?|(\s+)|(.)/g;

/** Small dependency-free SQL syntax highlighter that returns React nodes. */
export function highlightSql(sql: string): ReactNode[] {
  const out: ReactNode[] = [];
  let key = 0;
  for (const m of sql.matchAll(TOKEN)) {
    const [text, comment, str, num, quoted, word, paren] = m;
    const k = key++;
    if (comment) out.push(<span key={k} className="text-slate-400 italic">{comment}</span>);
    else if (str) out.push(<span key={k} className="text-emerald-700">{str}</span>);
    else if (num) out.push(<span key={k} className="text-amber-700">{num}</span>);
    else if (quoted) out.push(<span key={k} className="text-slate-800">{quoted}</span>);
    else if (word) {
      const lower = word.toLowerCase();
      if (paren) {
        out.push(
          <span key={k}>
            <span className="text-sky-700">{word}</span>
            {paren}
          </span>,
        );
      } else if (KEYWORDS.has(lower)) out.push(<span key={k} className="font-semibold text-indigo-700">{word}</span>);
      else out.push(<span key={k}>{word}</span>);
    } else out.push(text);
  }
  return out;
}
