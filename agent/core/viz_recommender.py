"""Visualization recommender module for QueryMind.

Keeps visualization decision logic server-side so the frontend can render charts
from a structured config using local data context.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

import structlog

logger = structlog.get_logger(__name__)

ChartType = Literal[
    "bar", "line", "pie", "scatter", "area", "table", "metric_card"
]


@dataclass
class VizConfig:
    """Structured chart recommendation returned to the frontend."""

    chart_type: ChartType
    x_axis: Optional[str]
    y_axis: Optional[str]
    series: Optional[str]
    title: str
    x_label: str
    y_label: str
    sort_by: Optional[str]
    format_hints: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize config for API transport."""
        return asdict(self)


class VizRecommender:
    """Rule-based visualization recommender."""

    def recommend(
        self,
        sql: str,
        results: List[Dict[str, Any]],
        column_types: Dict[str, str],
    ) -> VizConfig:
        """Analyze results and recommend best visualization config."""
        if not results:
            return VizConfig(
                chart_type="table",
                x_axis=None,
                y_axis=None,
                series=None,
                title="No results",
                x_label="",
                y_label="",
                sort_by=None,
                format_hints={},
            )

        cols = list(results[0].keys())
        inferred_types = self._merge_column_types(results, column_types)
        numeric_cols = [c for c in cols if inferred_types.get(c) == "numeric"]
        date_cols = [c for c in cols if inferred_types.get(c) == "date"]
        categorical_cols = [c for c in cols if inferred_types.get(c) == "categorical"]

        format_hints = self._build_format_hints(cols, inferred_types)

        # 1) 1 row + 1 numeric -> single metric card
        if len(results) == 1 and len(numeric_cols) == 1:
            metric = numeric_cols[0]
            return VizConfig(
                chart_type="metric_card",
                x_axis=None,
                y_axis=metric,
                series=None,
                title=self._title_from_sql(sql, default=f"{self._pretty(metric)}"),
                x_label="",
                y_label=self._pretty(metric),
                sort_by=None,
                format_hints=format_hints,
            )

        # 2) 1 row + multiple numeric -> metric card grid
        if len(results) == 1 and len(numeric_cols) > 1:
            return VizConfig(
                chart_type="metric_card",
                x_axis=None,
                y_axis=None,
                series=None,
                title=self._title_from_sql(sql, default="Summary metrics"),
                x_label="",
                y_label="",
                sort_by=None,
                format_hints={**format_hints, "layout": "grid"},
            )

        # 3) date + numeric
        if date_cols and numeric_cols:
            x = date_cols[0]
            if len(numeric_cols) > 1:
                # 8) Date + multiple numeric -> area for compact multi-series trend
                return VizConfig(
                    chart_type="area",
                    x_axis=x,
                    y_axis=numeric_cols[0],
                    series=numeric_cols[1] if len(numeric_cols) > 1 else None,
                    title=self._title_from_sql(sql, default=f"Trends over {self._pretty(x)}"),
                    x_label=self._pretty(x),
                    y_label="Values",
                    sort_by=x,
                    format_hints={**format_hints, "stacked": "false", "multi_series": "true"},
                )
            return VizConfig(
                chart_type="line",
                x_axis=x,
                y_axis=numeric_cols[0],
                series=None,
                title=self._title_from_sql(sql, default=f"{self._pretty(numeric_cols[0])} over time"),
                x_label=self._pretty(x),
                y_label=self._pretty(numeric_cols[0]),
                sort_by=x,
                format_hints=format_hints,
            )

        # 4/5) categorical + numeric
        if categorical_cols and numeric_cols:
            cat = self._best_categorical(categorical_cols, results)
            metric = numeric_cols[0]
            uniq = self._unique_count(results, cat)
            if uniq <= 8:
                # Pie if values look like a part-of-whole distribution.
                if self._sums_to_100(results, metric):
                    return VizConfig(
                        chart_type="pie",
                        x_axis=cat,
                        y_axis=metric,
                        series=None,
                        title=self._title_from_sql(sql, default=f"{self._pretty(metric)} distribution"),
                        x_label=self._pretty(cat),
                        y_label=self._pretty(metric),
                        sort_by=metric,
                        format_hints=format_hints,
                    )

                # Bar chart; suggest horizontal for long labels.
                orientation = "horizontal" if self._long_labels(results, cat) else "vertical"
                return VizConfig(
                    chart_type="bar",
                    x_axis=cat,
                    y_axis=metric,
                    series=None,
                    title=self._title_from_sql(sql, default=f"{self._pretty(metric)} by {self._pretty(cat)}"),
                    x_label=self._pretty(cat),
                    y_label=self._pretty(metric),
                    sort_by=metric,
                    format_hints={**format_hints, "orientation": orientation},
                )

        # 6) two numeric -> scatter
        if len(numeric_cols) >= 2:
            return VizConfig(
                chart_type="scatter",
                x_axis=numeric_cols[0],
                y_axis=numeric_cols[1],
                series=None,
                title=self._title_from_sql(sql, default="Correlation view"),
                x_label=self._pretty(numeric_cols[0]),
                y_label=self._pretty(numeric_cols[1]),
                sort_by=None,
                format_hints=format_hints,
            )

        # 9) many rows mixed types -> table
        if len(results) > 15 and len(set(inferred_types.values())) > 1:
            sort_by = date_cols[0] if date_cols else (numeric_cols[0] if numeric_cols else None)
            return VizConfig(
                chart_type="table",
                x_axis=None,
                y_axis=None,
                series=None,
                title=self._title_from_sql(sql, default="Detailed results"),
                x_label="",
                y_label="",
                sort_by=sort_by,
                format_hints=format_hints,
            )

        # 10) fallback
        return VizConfig(
            chart_type="table",
            x_axis=None,
            y_axis=None,
            series=None,
            title=self._title_from_sql(sql, default="Query results"),
            x_label="",
            y_label="",
            sort_by=numeric_cols[0] if numeric_cols else None,
            format_hints=format_hints,
        )

    def _merge_column_types(
        self,
        results: List[Dict[str, Any]],
        column_types: Dict[str, str],
    ) -> Dict[str, str]:
        merged: Dict[str, str] = {}
        sample = results[:10]

        for col in results[0].keys():
            explicit = (column_types.get(col) or "").lower()
            if explicit in {"numeric", "number", "int", "float", "decimal"}:
                merged[col] = "numeric"
                continue
            if explicit in {"date", "datetime", "timestamp", "time"}:
                merged[col] = "date"
                continue
            if explicit in {"string", "text", "category", "categorical"}:
                merged[col] = "categorical"
                continue

            merged[col] = self._infer_type_from_values(sample, col)

        return merged

    def _infer_type_from_values(self, rows: List[Dict[str, Any]], col: str) -> str:
        values = [r.get(col) for r in rows if r.get(col) is not None]
        if not values:
            return "categorical"

        if all(self._is_date(v) for v in values):
            return "date"

        numeric_hits = 0
        for v in values:
            try:
                float(v)
                numeric_hits += 1
            except (TypeError, ValueError):
                pass
        if numeric_hits >= max(1, int(0.8 * len(values))):
            return "numeric"

        return "categorical"

    def _is_date(self, value: Any) -> bool:
        if isinstance(value, (date, datetime)):
            return True
        if not isinstance(value, str):
            return False

        candidate = value.strip()
        date_patterns = [
            "%Y-%m-%d",
            "%Y-%m",
            "%Y/%m/%d",
            "%m/%d/%Y",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ]
        for pattern in date_patterns:
            try:
                datetime.strptime(candidate[: len(pattern)], pattern)
                return True
            except ValueError:
                continue
        return False

    def _best_categorical(self, cats: List[str], results: List[Dict[str, Any]]) -> str:
        ranked = sorted(cats, key=lambda c: self._unique_count(results, c))
        return ranked[0]

    def _unique_count(self, results: List[Dict[str, Any]], col: str) -> int:
        return len({str(r.get(col)) for r in results})

    def _sums_to_100(self, results: List[Dict[str, Any]], metric_col: str) -> bool:
        vals: List[float] = []
        for row in results:
            value = row.get(metric_col)
            try:
                vals.append(float(value))
            except (TypeError, ValueError):
                return False
        if not vals:
            return False
        total = sum(vals)
        return (95.0 <= total <= 105.0) or (0.95 <= total <= 1.05)

    def _long_labels(self, results: List[Dict[str, Any]], col: str) -> bool:
        avg_len = sum(len(str(r.get(col, ""))) for r in results) / max(1, len(results))
        return avg_len > 15

    def _build_format_hints(self, cols: List[str], types: Dict[str, str]) -> Dict[str, str]:
        hints: Dict[str, str] = {}
        for c in cols:
            c_lower = c.lower()

            if types.get(c) == "date":
                hints[c] = "date:mon_yyyy"

            if any(token in c_lower for token in ["revenue", "price", "amount", "mrr"]):
                hints[c] = "currency"

            if (
                "percent" in c_lower
                or c_lower.endswith("_pct")
                or c_lower.endswith("_percentage")
                or c_lower == "pct"
            ):
                hints[c] = "percentage"

        return hints

    def _title_from_sql(self, sql: str, default: str) -> str:
        normalized = " ".join(sql.strip().split())
        if not normalized:
            return default
        if len(normalized) <= 80:
            return default
        return default

    def _pretty(self, name: str) -> str:
        return name.replace("_", " ").strip().title()
