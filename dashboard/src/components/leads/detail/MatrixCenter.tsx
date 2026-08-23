"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { Lead } from "@/lib/types";
import type { MatrixMessage, MatrixOutput } from "@/lib/matrix-api";
import { generateMatrixChat, listMatrixOutputs } from "@/lib/matrix-api";

function useCopyToClipboard() {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const copy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback: select text for manual copy
    }
  }, []);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return { copied, copy };
}

export function MatrixCenter({ lead }: { lead: Lead }) {
  const applicationNumber = lead.application_number;

  const [messages, setMessages] = useState<MatrixMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [history, setHistory] = useState<MatrixOutput[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const { copied, copy } = useCopyToClipboard();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const loadHistory = useCallback(async () => {
    try {
      const resp = await listMatrixOutputs(applicationNumber);
      setHistory(resp.outputs);
      setHistoryLoaded(true);
    } catch {
      // Non-fatal
    }
  }, [applicationNumber]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const sendMessage = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    const userMessage: MatrixMessage = { role: "user", content: trimmed };
    const updatedMessages = [...messages, userMessage];

    setMessages(updatedMessages);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const resp = await generateMatrixChat(
        applicationNumber,
        updatedMessages
      );

      const assistantMessage: MatrixMessage = {
        role: "assistant",
        content: resp.output,
      };
      setMessages([...updatedMessages, assistantMessage]);
      await loadHistory();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Matrix generation failed"
      );
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [input, loading, messages, applicationNumber, loadHistory]);

  const handleNewConversation = useCallback(() => {
    setMessages([]);
    setInput("");
    setError(null);
    inputRef.current?.focus();
  }, []);

  const handleHistorySelect = useCallback((output: MatrixOutput) => {
    const userMessage: MatrixMessage = {
      role: "user",
      content: output.instruction,
    };
    const assistantMessage: MatrixMessage = {
      role: "assistant",
      content: output.output,
    };
    setMessages([userMessage, assistantMessage]);
    setError(null);
    setShowHistory(false);
  }, []);

  const handleCopyMessage = useCallback(
    (content: string) => {
      copy(content);
    },
    [copy]
  );

  return (
    <details className="group rounded-lg border border-border-subtle bg-card">
      <summary
        className="flex cursor-pointer items-center justify-between px-5 py-4 select-none"
        onClick={(e) => {
          e.preventDefault();
          const details = e.currentTarget.parentElement as HTMLDetailsElement;
          details.open = !details.open;
        }}
      >
        <div className="flex items-center gap-3">
          <svg
            className="h-4 w-4 shrink-0 text-foreground-faint transition-transform group-open:rotate-90"
            viewBox="0 0 12 12"
            fill="currentColor"
          >
            <path d="M4.5 2l4 4-4 4" />
          </svg>
          <h3 className="text-[13px] font-semibold uppercase tracking-[0.1em] text-foreground">
            Profile Matrix
          </h3>
          {messages.length > 0 && (
            <span className="rounded bg-accent-soft px-1.5 py-0.5 text-[10px] font-medium text-accent-strong">
              {messages.length} message{messages.length === 1 ? "" : "s"}
            </span>
          )}
        </div>
      </summary>

      <div className="flex flex-col px-5 pb-5">
        {/* Toolbar */}
        <div className="mb-3 flex items-center gap-2">
          <button
            onClick={handleNewConversation}
            disabled={loading}
            className="rounded-lg border border-border-subtle bg-surface px-3 py-1.5 text-[11px] text-foreground-muted transition-all hover:border-border-strong hover:text-foreground"
          >
            New conversation
          </button>
          <button
            onClick={() => setShowHistory(!showHistory)}
            disabled={!historyLoaded}
            className={`rounded-lg border px-3 py-1.5 text-[11px] transition-all ${
              showHistory
                ? "border-accent/40 bg-accent-soft text-accent-strong"
                : "border-border-subtle bg-surface text-foreground-muted hover:border-border-strong hover:text-foreground"
            }`}
          >
            History
            {history.length > 0 && (
              <span className="ml-1 text-[10px] opacity-60">
                ({history.length})
              </span>
            )}
          </button>
        </div>

        {/* History Panel */}
        {showHistory && historyLoaded && history.length > 0 && (
          <div className="mb-3 max-h-[200px] overflow-y-auto rounded-lg border border-border-subtle bg-surface/60 p-2">
            <div className="flex flex-col gap-1">
              {history.map((output) => (
                <button
                  key={output.id}
                  onClick={() => handleHistorySelect(output)}
                  className="flex items-center gap-3 rounded-md border border-transparent px-3 py-2 text-left transition-all hover:border-border-strong hover:bg-background/50"
                >
                  <span className="text-[11px] font-semibold text-foreground">
                    v{output.version}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[11px] text-foreground-muted">
                    {output.instruction}
                  </span>
                  <div className="flex items-center gap-2">
                    {output.is_draft && (
                      <span className="rounded bg-status-caution-soft px-1.5 py-0.5 text-[9px] font-medium text-status-caution">
                        DRAFT
                      </span>
                    )}
                    <span className="text-[10px] text-foreground-faint">
                      {new Date(output.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mb-3 rounded-lg border border-status-negative/30 bg-status-negative-soft p-3 text-xs text-status-negative">
            {error}
          </div>
        )}

        {/* Chat Messages */}
        <div className="mb-3 max-h-[500px] min-h-[200px] overflow-y-auto rounded-lg border border-border-subtle bg-background/50 p-4">
          {messages.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <div className="max-w-sm text-center">
                <p className="text-sm text-foreground-muted">
                  Ask me anything about this profile.
                </p>
                <p className="mt-2 text-[11px] text-foreground-faint">
                  I have access to the full applicant, case, property,
                  opportunity, and intelligence data for this application.
                </p>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`group/msg max-w-[85%] rounded-lg px-4 py-3 text-xs leading-relaxed ${
                      msg.role === "user"
                        ? "bg-accent-soft text-accent-strong"
                        : "bg-surface text-foreground"
                    }`}
                  >
                    <pre className="whitespace-pre-wrap font-sans">
                      {msg.content}
                    </pre>
                    {msg.role === "assistant" && (
                      <button
                        onClick={() => handleCopyMessage(msg.content)}
                        className="mt-2 flex items-center gap-1 text-[10px] text-foreground-faint opacity-0 transition-opacity group-hover/msg:opacity-100"
                      >
                        {copied ? (
                          <>
                            <svg
                              className="h-3 w-3 text-status-positive"
                              fill="none"
                              viewBox="0 0 24 24"
                              strokeWidth={2}
                              stroke="currentColor"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M4.5 12.75l6 6 9-13.5"
                              />
                            </svg>
                            Copied
                          </>
                        ) : (
                          <>
                            <svg
                              className="h-3 w-3"
                              fill="none"
                              viewBox="0 0 24 24"
                              strokeWidth={1.5}
                              stroke="currentColor"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184"
                              />
                            </svg>
                            Copy
                          </>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex justify-start">
                  <div className="rounded-lg bg-surface px-4 py-3 text-xs text-foreground-muted">
                    <div className="flex items-center gap-2">
                      <svg
                        className="h-3.5 w-3.5 animate-spin"
                        viewBox="0 0 24 24"
                        fill="none"
                      >
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                        />
                      </svg>
                      Thinking...
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder='e.g. "Write a professional email about the application review..."'
            rows={2}
            className="flex-1 resize-none rounded-lg border border-border-subtle bg-background p-3 text-xs leading-relaxed text-foreground placeholder:text-foreground-faint/50 focus:border-accent/50 focus:outline-none focus:ring-1 focus:ring-accent/20"
            style={{ minHeight: "44px", maxHeight: "120px" }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className={`flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-lg transition-all ${
              loading
                ? "cursor-wait border border-priority-high/30 bg-priority-high-soft text-priority-high"
                : !input.trim()
                  ? "cursor-not-allowed border border-border-subtle bg-surface text-foreground-faint"
                  : "border border-accent/40 bg-accent-soft text-accent-strong hover:border-accent/60 hover:bg-accent/10"
            }`}
          >
            {loading ? (
              <svg
                className="h-4 w-4 animate-spin"
                viewBox="0 0 24 24"
                fill="none"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
            ) : (
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
                />
              </svg>
            )}
          </button>
        </div>
        <div className="mt-1.5 text-[10px] text-foreground-faint">
          Enter to send · Shift+Enter for newline
        </div>
      </div>
    </details>
  );
}
