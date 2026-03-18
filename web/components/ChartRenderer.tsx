"use client";

import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ChartConfig {
  type: "bar" | "line" | "pie" | "scatter" | "area" | "table" | "metric_card";
  data: Record<string, unknown>[];
  x_axis?: string;
  y_axis?: string;
  series?: string;
  title: string;
  x_label?: string;
  y_label?: string;
  format_hints?: Record<string, "currency" | "percent" | "number" | "date">;
}

type SortDirection = "asc" | "desc";

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#f43f5e", "#a855f7"];
const EMPTY_ROWS: Array<Record<string, unknown>> = [];

function detectNumericKeys(rows: Array<Record<string, unknown>>): string[] {
  if (!rows.length) return [];
  const keys = Object.keys(rows[0]);
  return keys.filter((key) =>
    rows.some((r) => {
      const v = r[key];
      return typeof v === "number" || (typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v)));
    }),
  );
}

function formatByHint(value: unknown, hint?: "currency" | "percent" | "number" | "date"): string {
  if (value === null || value === undefined || value === "") return "-";

  if (hint === "currency") {
    const n = Number(value);
    if (Number.isNaN(n)) return String(value);
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: "USD",
      notation: Math.abs(n) >= 1_000_000 ? "compact" : "standard",
      maximumFractionDigits: 2,
    }).format(n);
  }

  if (hint === "percent") {
    const n = Number(value);
    if (Number.isNaN(n)) return String(value);
    const pct = Math.abs(n) <= 1 ? n * 100 : n;
    return `${pct.toFixed(1)}%`;
  }

  if (hint === "date") {
    if (!(value instanceof Date) && typeof value !== "string" && typeof value !== "number") {
      return String(value);
    }
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
  }

  if (hint === "number") {
    const n = Number(value);
    if (Number.isNaN(n)) return String(value);
    return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (typeof value === "string") {
    const d = new Date(value);
    if (!Number.isNaN(d.getTime()) && /\d{4}-\d{2}-\d{2}/.test(value)) {
      return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
    }
  }

  return String(value);
}

function sortableValue(v: unknown): string | number {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") return v;
  const asNum = Number(v);
  if (!Number.isNaN(asNum) && String(v).trim() !== "") return asNum;
  if (v instanceof Date || typeof v === "string" || typeof v === "number") {
    const asDate = new Date(v).getTime();
    if (!Number.isNaN(asDate)) return asDate;
  }
  return String(v).toLowerCase();
}

function SortableTable({ config }: { config: ChartConfig }) {
  const rows = config.data.length ? config.data : EMPTY_ROWS;
  const columns = rows.length ? Object.keys(rows[0]) : [];
  const [sortKey, setSortKey] = useState<string>(columns[0] ?? "");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const left = sortableValue(a[sortKey]);
      const right = sortableValue(b[sortKey]);
      if (left < right) return sortDirection === "asc" ? -1 : 1;
      if (left > right) return sortDirection === "asc" ? 1 : -1;
      return 0;
    });
    return copy;
  }, [rows, sortKey, sortDirection]);

  const toggleSort = (column: string) => {
    if (sortKey === column) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(column);
    setSortDirection("asc");
  };

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-2">
      <div className="mb-2 text-sm font-semibold text-slate-100">{config.title}</div>
      <div className="max-h-80 overflow-auto rounded border border-slate-800">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-slate-900">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  className="cursor-pointer px-3 py-2 text-left text-xs uppercase tracking-wide text-slate-300"
                  onClick={() => toggleSort(col)}
                >
                  {col}
                  {sortKey === col ? (sortDirection === "asc" ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row, idx) => (
              <tr key={`${idx}-${String(row[columns[0]] ?? idx)}`} className="border-t border-slate-800 hover:bg-slate-800/30">
                {columns.map((col) => (
                  <td key={`${idx}-${col}`} className="px-3 py-2 text-slate-100">
                    {formatByHint(row[col], config.format_hints?.[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MetricCard({ config }: { config: ChartConfig }) {
  const key = config.y_axis || Object.keys(config.data?.[0] ?? {})[0] || "value";
  const raw = config.data?.[0]?.[key];
  const formatted = formatByHint(raw, config.format_hints?.[key] ?? "number");

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-5">
      <p className="text-xs uppercase tracking-wider text-slate-300">{config.title}</p>
      <p className="mt-2 text-4xl font-bold text-slate-100">{formatted}</p>
      {config.y_label ? <p className="mt-1 text-sm text-slate-300">{config.y_label}</p> : null}
    </div>
  );
}

export default function ChartRenderer({ config }: { config: ChartConfig }) {
  const data = config.data.length ? config.data : EMPTY_ROWS;

  if (!data.length) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm text-slate-300">
        No data available for chart rendering.
      </div>
    );
  }

  const xKey = config.x_axis ?? "";
  const yKey = config.y_axis ?? "";

  const numericKeys = detectNumericKeys(data).filter((k) => k !== xKey && k !== config.series);
  const areaKeys = yKey ? [yKey, ...numericKeys.filter((k) => k !== yKey)] : numericKeys;

  const tooltipFormatter = (value: unknown, name: string | number | undefined) => {
    const seriesName = String(name ?? "value");
    return [formatByHint(value, config.format_hints?.[seriesName]), seriesName];
  };

  if (config.type === "table") {
    return <SortableTable config={config} />;
  }

  if (config.type === "metric_card") {
    return <MetricCard config={config} />;
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
      <div className="mb-2 text-sm font-semibold text-slate-100">{config.title}</div>
      <div className="h-[320px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          {config.type === "bar" ? (
            <BarChart data={data} margin={{ top: 12, right: 16, left: 0, bottom: 20 }}>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis dataKey={xKey} stroke="#cbd5e1" tick={{ fill: "#cbd5e1", fontSize: 12 }} label={config.x_label ? { value: config.x_label, position: "insideBottom", fill: "#cbd5e1" } : undefined} />
              <YAxis stroke="#cbd5e1" tick={{ fill: "#cbd5e1", fontSize: 12 }} label={config.y_label ? { value: config.y_label, angle: -90, position: "insideLeft", fill: "#cbd5e1" } : undefined} tickFormatter={(v) => formatByHint(v, config.format_hints?.[yKey])} />
              <Tooltip formatter={tooltipFormatter} contentStyle={{ background: "#0f172a", border: "1px solid #334155", color: "#e2e8f0" }} />
              <Bar dataKey={yKey} fill={COLORS[0]} radius={[6, 6, 0, 0]} animationDuration={650} />
            </BarChart>
          ) : config.type === "line" ? (
            <LineChart data={data} margin={{ top: 12, right: 16, left: 0, bottom: 20 }}>
              <defs>
                <linearGradient id="line-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis dataKey={xKey} stroke="#cbd5e1" tick={{ fill: "#cbd5e1", fontSize: 12 }} label={config.x_label ? { value: config.x_label, position: "insideBottom", fill: "#cbd5e1" } : undefined} />
              <YAxis stroke="#cbd5e1" tick={{ fill: "#cbd5e1", fontSize: 12 }} label={config.y_label ? { value: config.y_label, angle: -90, position: "insideLeft", fill: "#cbd5e1" } : undefined} tickFormatter={(v) => formatByHint(v, config.format_hints?.[yKey])} />
              <Tooltip formatter={tooltipFormatter} contentStyle={{ background: "#0f172a", border: "1px solid #334155", color: "#e2e8f0" }} />
              <Area type="monotone" dataKey={yKey} stroke="none" fill="url(#line-fill)" animationDuration={650} />
              <Line type="monotone" dataKey={yKey} stroke="#3b82f6" strokeWidth={3} dot={{ r: 4, fill: "#3b82f6" }} activeDot={{ r: 6 }} animationDuration={650} />
            </LineChart>
          ) : config.type === "pie" ? (
            <PieChart>
              <Tooltip formatter={tooltipFormatter} contentStyle={{ background: "#0f172a", border: "1px solid #334155", color: "#e2e8f0" }} />
              <Legend wrapperStyle={{ color: "#cbd5e1" }} />
              <Pie
                data={data}
                dataKey={yKey}
                nameKey={xKey}
                outerRadius={110}
                label={(entry) => {
                  const val = Number(entry.value ?? 0);
                  const total = data.reduce((acc, row) => acc + Number(row[yKey] ?? 0), 0);
                  const pct = total ? ((val / total) * 100).toFixed(1) : "0.0";
                  return `${entry.name}: ${pct}%`;
                }}
                animationDuration={650}
              >
                {data.map((_, idx) => (
                  <Cell key={`pie-${idx}`} fill={COLORS[idx % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          ) : config.type === "scatter" ? (
            <ScatterChart margin={{ top: 12, right: 16, left: 0, bottom: 20 }}>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis dataKey={xKey} stroke="#cbd5e1" tick={{ fill: "#cbd5e1", fontSize: 12 }} name={config.x_label || xKey} tickFormatter={(v) => formatByHint(v, config.format_hints?.[xKey])} />
              <YAxis dataKey={yKey} stroke="#cbd5e1" tick={{ fill: "#cbd5e1", fontSize: 12 }} name={config.y_label || yKey} tickFormatter={(v) => formatByHint(v, config.format_hints?.[yKey])} />
              <Tooltip
                cursor={{ strokeDasharray: "3 3" }}
                contentStyle={{ background: "#0f172a", border: "1px solid #334155", color: "#e2e8f0" }}
                formatter={tooltipFormatter}
              />
              <Scatter data={data} fill="#3b82f6" animationDuration={650} />
            </ScatterChart>
          ) : (
            <AreaChart data={data} margin={{ top: 12, right: 16, left: 0, bottom: 20 }}>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis dataKey={xKey} stroke="#cbd5e1" tick={{ fill: "#cbd5e1", fontSize: 12 }} label={config.x_label ? { value: config.x_label, position: "insideBottom", fill: "#cbd5e1" } : undefined} />
              <YAxis stroke="#cbd5e1" tick={{ fill: "#cbd5e1", fontSize: 12 }} label={config.y_label ? { value: config.y_label, angle: -90, position: "insideLeft", fill: "#cbd5e1" } : undefined} />
              <Tooltip formatter={tooltipFormatter} contentStyle={{ background: "#0f172a", border: "1px solid #334155", color: "#e2e8f0" }} />
              <Legend wrapperStyle={{ color: "#cbd5e1" }} />
              {areaKeys.map((key, idx) => (
                <Area
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={COLORS[idx % COLORS.length]}
                  fill={COLORS[idx % COLORS.length]}
                  fillOpacity={0.2}
                  stackId={config.series ? "stack" : undefined}
                  animationDuration={650}
                />
              ))}
            </AreaChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
