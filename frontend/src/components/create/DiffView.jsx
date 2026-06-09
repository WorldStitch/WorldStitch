import { useMemo } from 'react';
import { CheckCircle, XCircle } from 'lucide-react';

// ── Myers line diff ──────────────────────────────────────────────────────────

function diffLines(oldText, newText) {
  const a = (oldText || '').split('\n');
  const b = (newText || '').split('\n');
  const m = a.length;
  const n = b.length;

  // Build LCS table (O(m*n) — fine for note-length content)
  const dp = Array.from({ length: m + 1 }, () => new Int32Array(n + 1));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] =
        a[i - 1] === b[j - 1]
          ? dp[i - 1][j - 1] + 1
          : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }

  // Backtrack
  const result = [];
  let i = m,
    j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      result.unshift({ type: 'equal', text: a[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      result.unshift({ type: 'add', text: b[j - 1] });
      j--;
    } else {
      result.unshift({ type: 'remove', text: a[i - 1] });
      i--;
    }
  }

  return result;
}

/**
 * Collapses long runs of unchanged lines to keep the diff readable.
 * Keeps up to `context` lines of context around each change.
 */
function collapseContext(hunks, context = 3) {
  if (hunks.length === 0) return [];

  const changed = new Set(
    hunks
      .map((h, i) => (h.type !== 'equal' ? i : -1))
      .filter((i) => i !== -1)
  );

  const visible = new Set();
  changed.forEach((idx) => {
    for (let k = Math.max(0, idx - context); k <= Math.min(hunks.length - 1, idx + context); k++) {
      visible.add(k);
    }
  });

  const result = [];
  let gap = false;
  for (let i = 0; i < hunks.length; i++) {
    if (visible.has(i)) {
      if (gap) {
        result.push({ type: 'ellipsis' });
        gap = false;
      }
      result.push(hunks[i]);
    } else {
      gap = true;
    }
  }
  if (gap) result.push({ type: 'ellipsis' });

  return result;
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Diff view with Accept / Reject.
 *
 * Props:
 *   command    string   — the command that produced this diff (e.g. "Rewrite")
 *   oldText    string   — original note content (or selected text)
 *   newText    string   — AI-proposed content
 *   loading    boolean  — AI is still streaming
 *   onAccept   () => void
 *   onReject   () => void
 */
export default function DiffView({ command, oldText, newText, loading, onAccept, onReject }) {
  const hunks = useMemo(
    () => collapseContext(diffLines(oldText, newText)),
    [oldText, newText]
  );

  const addCount = hunks.filter((h) => h.type === 'add').length;
  const removeCount = hunks.filter((h) => h.type === 'remove').length;

  return (
    <div className="flex flex-col h-full bg-card border-t border-txt-muted/10">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-txt-muted/10 flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-txt">
            {command ? `AI: ${command}` : 'AI Proposal'}
          </span>
          {!loading && (
            <div className="flex items-center gap-2 text-xs">
              {addCount > 0 && (
                <span className="text-green-400 font-mono">+{addCount}</span>
              )}
              {removeCount > 0 && (
                <span className="text-danger font-mono">−{removeCount}</span>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {loading ? (
            <span className="text-xs text-txt-muted animate-pulse">Generating…</span>
          ) : (
            <>
              <button
                type="button"
                onClick={onReject}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-txt-muted hover:text-danger hover:bg-danger/10 transition border border-transparent hover:border-danger/20"
              >
                <XCircle size={13} />
                Reject
              </button>
              <button
                type="button"
                onClick={onAccept}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-green/15 text-green-400 hover:bg-green/25 transition border border-green/20"
              >
                <CheckCircle size={13} />
                Accept
              </button>
            </>
          )}
        </div>
      </div>

      {/* Diff body */}
      <div className="flex-1 overflow-y-auto font-mono text-xs leading-relaxed p-2">
        {loading ? (
          <div className="p-4 space-y-2">
            {[...Array(5)].map((_, i) => (
              <div
                key={i}
                className="h-3 rounded bg-elevated/60 animate-pulse"
                style={{ width: `${60 + Math.random() * 35}%` }}
              />
            ))}
          </div>
        ) : hunks.length === 0 ? (
          <div className="p-4 text-txt-muted text-center">No changes proposed.</div>
        ) : (
          <table className="w-full border-collapse">
            <tbody>
              {hunks.map((hunk, i) => {
                if (hunk.type === 'ellipsis') {
                  return (
                    <tr key={`ellipsis-${i}`}>
                      <td
                        colSpan={2}
                        className="px-3 py-0.5 text-txt-muted/40 text-center select-none"
                      >
                        ···
                      </td>
                    </tr>
                  );
                }

                const cls =
                  hunk.type === 'add'
                    ? 'diff-line-add'
                    : hunk.type === 'remove'
                    ? 'diff-line-remove'
                    : 'diff-line-equal';

                const prefix =
                  hunk.type === 'add' ? '+' : hunk.type === 'remove' ? '−' : ' ';

                const textColor =
                  hunk.type === 'add'
                    ? 'text-green-400'
                    : hunk.type === 'remove'
                    ? 'text-danger'
                    : 'text-txt-muted';

                return (
                  <tr key={i} className={cls}>
                    <td
                      className={`w-5 pl-3 pr-1 py-0.5 select-none ${textColor} font-bold`}
                    >
                      {prefix}
                    </td>
                    <td className="px-1 py-0.5 whitespace-pre-wrap break-words text-txt">
                      {hunk.text || ' '}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer hint */}
      {!loading && (
        <div className="px-4 py-2 border-t border-txt-muted/10 text-xs text-txt-muted flex-shrink-0">
          Accept replaces the note content · Reject discards this proposal
        </div>
      )}
    </div>
  );
}
