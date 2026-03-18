"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import ChartRenderer, { ChartConfig } from "../components/ChartRenderer";
import CsvUpload from "../components/CsvUpload";
import SampleQuestions from "../components/SampleQuestions";

type DatabaseName = "ecommerce" | "saas";
type QueryStatus = "success" | "clarification" | "error";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

type QueryResponse = {
  status: QueryStatus;
  sql: string | null;
  sql_explanation: string;
  results: Array<Record<string, unknown>>;
  row_count: number;
  execution_time_ms: number;
  chart: {
    type: string;
    config: Record<string, unknown>;
  };
  insight: {
    summary: string;
    key_findings: string[];
    suggested_follow_ups: string[];
  };
  clarification_question: string | null;
  conversation_id: string;
};

type ChatMessage =
  | {
      id: string;
      role: "user";
      text: string;
      createdAt: string;
    }
  | {
      id: string;
      role: "agent";
      payload: QueryResponse;
      createdAt: string;
    };

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function toCsv(rows: Array<Record<string, unknown>>): string {
  if (!rows.length) {
    return "";
  }

  const headers = Object.keys(rows[0]);
  const escapeCell = (value: unknown): string => {
    const text = String(value ?? "");
    if (text.includes(",") || text.includes("\n") || text.includes('"')) {
      return `"${text.replaceAll('"', '""')}"`;
    }
    return text;
  };

  const lines = [headers.join(",")];
  for (const row of rows) {
    lines.push(headers.map((h) => escapeCell(row[h])).join(","));
  }
  return lines.join("\n");
}

function downloadCsv(rows: Array<Record<string, unknown>>, fileName: string): void {
  const csv = toCsv(rows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

function LoadingMessage() {
  const phases = [
    "Analyzing your question...",
    "Writing SQL...",
    "Running query...",
    "Generating insights...",
  ];
  const [phaseIndex, setPhaseIndex] = useState<number>(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setPhaseIndex((prev: number) => (prev + 1) % phases.length);
    }, 1100);
    return () => window.clearInterval(timer);
  }, [phases.length]);

  return (
    <div className="w-full max-w-4xl rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="mb-3 h-3 w-36 animate-pulse rounded bg-slate-800" />
      <div className="mb-2 h-3 w-full animate-pulse rounded bg-slate-800" />
      <div className="mb-3 h-3 w-5/6 animate-pulse rounded bg-slate-800" />
      <p className="text-sm text-slate-300">{phases[phaseIndex]}</p>
    </div>
  );
}

function normalizeChartType(type: string): ChartConfig["type"] {
  if (
    type === "bar" ||
    type === "line" ||
    type === "pie" ||
    type === "scatter" ||
    type === "area" ||
    type === "table" ||
    type === "metric_card"
  ) {
    return type;
  }
  return "table";
}

function AgentMessage({
  message,
  onRetry,
  onSendFollowUp,
}: {
  message: Extract<ChatMessage, { role: "agent" }>;
  onRetry: () => void;
  onSendFollowUp: (text: string) => void;
}) {
  const [showSql, setShowSql] = useState<boolean>(false);
  const [clarificationValue, setClarificationValue] = useState<string>("");

  const payload = message.payload;
  const chartConfigRaw = payload.chart?.config ?? {};
  const chartConfig: ChartConfig = {
    type: normalizeChartType(payload.chart?.type ?? "table"),
    data: payload.results as Array<Record<string, unknown>>,
    title: String((chartConfigRaw.title as string | undefined) ?? payload.sql_explanation ?? "Results"),
    x_axis: String(
      (chartConfigRaw.x_axis as string | undefined) ??
        (chartConfigRaw.x_column as string | undefined) ??
        (chartConfigRaw.label_column as string | undefined) ??
        "",
    ),
    y_axis: String(
      (chartConfigRaw.y_axis as string | undefined) ??
        (chartConfigRaw.y_column as string | undefined) ??
        (chartConfigRaw.value_column as string | undefined) ??
        "",
    ),
    x_label: (chartConfigRaw.x_label as string | undefined) ?? undefined,
    y_label: (chartConfigRaw.y_label as string | undefined) ?? undefined,
    series: (chartConfigRaw.series as string | undefined) ?? undefined,
    format_hints: (chartConfigRaw.format_hints as ChartConfig["format_hints"] | undefined) ?? undefined,
  };

  const copySql = useCallback(async () => {
    if (!payload.sql) {
      return;
    }
    await navigator.clipboard.writeText(payload.sql);
  }, [payload.sql]);

  return (
    <div className="w-full max-w-4xl rounded-xl border border-slate-800 bg-slate-900 p-4 text-slate-100">
      {payload.status === "error" ? (
        <div className="rounded-lg border border-red-900 bg-red-950/30 p-3">
          <p className="text-sm text-red-300">I ran into an issue processing your request.</p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 rounded bg-blue-600 px-3 py-1 text-xs font-semibold text-white hover:bg-blue-500"
          >
            Retry
          </button>
        </div>
      ) : null}

      {payload.sql ? (
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setShowSql((prev) => !prev)}
              className="text-sm font-medium text-blue-400 hover:text-blue-300"
            >
              {showSql ? "Hide SQL" : "Show SQL"}
            </button>
            <button
              type="button"
              onClick={copySql}
              className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
            >
              Copy SQL
            </button>
          </div>
          {showSql ? (
            <SyntaxHighlighter language="sql" style={oneDark} customStyle={{ margin: 0, borderRadius: 8 }}>
              {payload.sql}
            </SyntaxHighlighter>
          ) : null}
        </div>
      ) : null}

      {payload.results.length ? (
        <div className="mt-4 space-y-3">
          <ChartRenderer config={chartConfig} />

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => downloadCsv(payload.results, `results-${message.id}.csv`)}
              className="rounded border border-slate-700 px-3 py-1 text-xs text-slate-200 hover:bg-slate-800"
            >
              Download CSV
            </button>
          </div>

          {chartConfig.type !== "table" ? (
            <ChartRenderer
              config={{
                type: "table",
                data: payload.results as Array<Record<string, unknown>>,
                title: "Raw Data",
                format_hints: chartConfig.format_hints,
              }}
            />
          ) : null}
        </div>
      ) : null}

      {payload.insight.summary ? (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <p className="text-sm text-slate-100">{payload.insight.summary}</p>
          {payload.insight.key_findings.length ? (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
              {payload.insight.key_findings.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {payload.insight.suggested_follow_ups.length ? (
        <div className="mt-4">
          <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Suggested follow-ups</p>
          <div className="flex flex-wrap gap-2">
            {payload.insight.suggested_follow_ups.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => onSendFollowUp(suggestion)}
                className="rounded-full border border-slate-700 bg-slate-800 px-3 py-1 text-xs text-slate-200 hover:border-blue-600"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {payload.status === "clarification" && payload.clarification_question ? (
        <div className="mt-4 rounded-lg border border-amber-800 bg-amber-950/30 p-3">
          <p className="text-sm text-amber-200">{payload.clarification_question}</p>
          <div className="mt-2 flex gap-2">
            <input
              value={clarificationValue}
              onChange={(e) => setClarificationValue(e.target.value)}
              placeholder="Add clarification..."
              className="flex-1 rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-blue-600"
            />
            <button
              type="button"
              onClick={() => {
                const text = clarificationValue.trim();
                if (!text) {
                  return;
                }
                onSendFollowUp(text);
                setClarificationValue("");
              }}
              className="rounded bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
            >
              Submit
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function Page() {
  const [database, setDatabase] = useState<DatabaseName>("ecommerce");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);
  const [lastPrompt, setLastPrompt] = useState<string>("");

  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const userHistory = useMemo(() => {
    return messages.filter((m): m is Extract<ChatMessage, { role: "user" }> => m.role === "user");
  }, [messages]);

  const sendQuestion = useCallback(
    async (question: string) => {
      const text = question.trim();
      if (!text || loading) {
        return;
      }

      const userMessage: ChatMessage = {
        id: makeId(),
        role: "user",
        text,
        createdAt: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setInputValue("");
      setLastPrompt(text);
      setLoading(true);

      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/query`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: text,
            database,
            conversation_id: conversationId,
          }),
        });

        const payload = (await response.json()) as QueryResponse;
        if (payload.conversation_id) {
          setConversationId(payload.conversation_id);
        }

        const agentMessage: ChatMessage = {
          id: makeId(),
          role: "agent",
          payload,
          createdAt: new Date().toISOString(),
        };

        setMessages((prev) => [...prev, agentMessage]);
      } catch {
        const fallback: QueryResponse = {
          status: "error",
          sql: null,
          sql_explanation: "",
          results: [],
          row_count: 0,
          execution_time_ms: 0,
          chart: { type: "table", config: {} },
          insight: { summary: "", key_findings: [], suggested_follow_ups: [] },
          clarification_question: null,
          conversation_id: conversationId ?? makeId(),
        };
        setMessages((prev) => [
          ...prev,
          {
            id: makeId(),
            role: "agent",
            payload: fallback,
            createdAt: new Date().toISOString(),
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [conversationId, database, loading],
  );

  const submitCurrent = useCallback(() => {
    void sendQuestion(inputValue);
  }, [inputValue, sendQuestion]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex h-screen max-w-[1600px] overflow-hidden">
        <aside
          className={`fixed inset-y-0 left-0 z-40 w-80 border-r border-slate-800 bg-slate-900 p-4 transition-transform md:static md:translate-x-0 ${
            sidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="mb-4 flex items-center justify-between md:hidden">
            <h2 className="text-sm font-semibold text-slate-200">Sidebar</h2>
            <button
              type="button"
              onClick={() => setSidebarOpen(false)}
              className="rounded border border-slate-700 px-2 py-1 text-xs"
            >
              Close
            </button>
          </div>

          <div className="mb-6">
            <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Database</p>
            <div className="grid grid-cols-2 gap-2">
              {(["ecommerce", "saas"] as DatabaseName[]).map((db) => (
                <button
                  key={db}
                  type="button"
                  onClick={() => setDatabase(db)}
                  className={`rounded px-3 py-2 text-sm font-medium ${
                    database === db
                      ? "bg-blue-600 text-white"
                      : "border border-slate-700 bg-slate-800 text-slate-200 hover:border-blue-600"
                  }`}
                >
                  {db}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-6">
            <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Conversation History</p>
            <div className="max-h-44 space-y-2 overflow-auto rounded-lg border border-slate-800 bg-slate-950/40 p-2">
              {userHistory.length ? (
                userHistory.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => setInputValue(m.text)}
                    className="w-full rounded bg-slate-800 px-2 py-1 text-left text-xs text-slate-300 hover:bg-slate-700"
                  >
                    {m.text}
                  </button>
                ))
              ) : (
                <p className="text-xs text-slate-500">No prior prompts yet.</p>
              )}
            </div>
          </div>

          <CsvUpload apiBaseUrl={API_BASE_URL} />

          <SampleQuestions
            database={database}
            onQuestionSelect={(question) => {
              void sendQuestion(question);
            }}
          />
        </aside>

        {sidebarOpen ? (
          <button
            type="button"
            className="fixed inset-0 z-30 bg-black/50 md:hidden"
            aria-label="Close menu"
            onClick={() => setSidebarOpen(false)}
          />
        ) : null}

        <main className="relative flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-slate-800 bg-slate-950/80 px-4 py-3">
            <div>
              <h1 className="text-lg font-semibold text-slate-100">QueryMind Chat</h1>
              <p className="text-xs text-slate-300">Ask questions, inspect SQL, and explore results.</p>
            </div>
            <button
              type="button"
              className="rounded border border-slate-700 px-3 py-1 text-xs text-slate-200 md:hidden"
              onClick={() => setSidebarOpen(true)}
            >
              Menu
            </button>
          </header>

          <section className="flex-1 space-y-4 overflow-y-auto px-4 py-4 pb-36">
            {!messages.length ? (
              <div className="mx-auto mt-10 max-w-2xl rounded-xl border border-slate-800 bg-slate-900 p-6 text-center">
                <p className="text-lg font-semibold text-slate-100">Start with a data question</p>
                <p className="mt-2 text-sm text-slate-300">
                  Example: How many customers do we have?
                </p>
              </div>
            ) : null}

            {messages.map((message) =>
              message.role === "user" ? (
                <div key={message.id} className="flex justify-end">
                  <div className="max-w-2xl rounded-2xl bg-blue-600 px-4 py-3 text-sm text-white shadow-lg">
                    {message.text}
                  </div>
                </div>
              ) : (
                <div key={message.id} className="flex justify-start">
                  <AgentMessage
                    message={message}
                    onRetry={() => void sendQuestion(lastPrompt)}
                    onSendFollowUp={(text: string) => void sendQuestion(text)}
                  />
                </div>
              ),
            )}

            {loading ? (
              <div className="flex justify-start">
                <LoadingMessage />
              </div>
            ) : null}

            <div ref={bottomRef} />
          </section>

          <div className="absolute inset-x-0 bottom-0 border-t border-slate-800 bg-slate-950/95 p-3">
            <div className="mx-auto flex max-w-4xl gap-2">
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submitCurrent();
                  }
                }}
                placeholder="Ask your question..."
                className="min-h-[54px] flex-1 resize-y rounded-lg border border-slate-700 bg-slate-900 px-3 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-blue-600"
              />
              <button
                type="button"
                onClick={submitCurrent}
                disabled={loading || !inputValue.trim()}
                className="rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Send
              </button>
            </div>
            <p className="mx-auto mt-2 max-w-4xl text-xs text-slate-500">Enter to send, Shift+Enter for newline.</p>
          </div>
        </main>
      </div>
    </div>
  );
}
