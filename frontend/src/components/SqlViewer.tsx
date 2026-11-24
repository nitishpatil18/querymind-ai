import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { highlightSql } from "../utils/sqlHighlight";
import { Button } from "./ui";

export function SqlViewer({ sql, showCopy = true }: { sql: string; showCopy?: boolean }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable (insecure context): ignore */
    }
  }

  return (
    <div className="relative rounded-lg border border-slate-200 bg-slate-50">
      {showCopy && (
        <div className="absolute right-2 top-2">
          <Button variant="secondary" onClick={copy} icon={copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />} className="!px-2 !py-1 text-xs">
            {copied ? "Copied" : "Copy SQL"}
          </Button>
        </div>
      )}
      <pre aria-label="Generated SQL" className="max-h-96 overflow-auto p-4 pr-28 font-mono text-[13px] leading-relaxed text-slate-800">
        <code>{highlightSql(sql)}</code>
      </pre>
    </div>
  );
}
