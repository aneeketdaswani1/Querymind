"""Visualization recommender module for QueryMind.

Analyzes query results and recommends appropriate visualization types (charts, tables, etc.)
based on data characteristics and structure using LLM-based analysis.
"""

from typing import List, Dict, Any, Tuple, Literal
from datetime import datetime, date
import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger(__name__)


class VizRecommender:
    """
    Analyzes query results and recommends best chart type for visualization.
    
    Rules for chart selection:
    - Time series (date column + metric) -> line chart
    - Categorical comparison (< 10 categories + metric) -> bar chart
    - Part-of-whole (percentages summing to ~100%) -> pie chart
    - Two numeric columns -> scatter plot
    - > 10 rows with no clear pattern -> table
    - Single number result -> metric/big number card
    """
    
    def __init__(self, llm_client: ChatAnthropic):
        """
        Initialize VizRecommender.
        
        Args:
            llm_client: Initialized ChatAnthropic client for Claude
        """
        self.llm = llm_client
        logger.debug("viz_recommender_initialized")
    
    def recommend(
        self,
        results: List[Dict[str, Any]],
        query: str,
        explanation: str = ""
    ) -> Tuple[Literal["bar", "line", "pie", "table", "scatter", "area", "none"], Dict[str, Any]]:
        """
        Analyze results and recommend chart type with configuration.
        
        Args:
            results: Query results (list of dicts)
            query: The SQL query that generated these results
            explanation: LLM explanation of what the query does
        
        Returns:
            Tuple of (chart_type, chart_config)
            - chart_type: Recommended visualization type
            - chart_config: Configuration dict with labels, colors, data mappings
        """
        if not results:
            logger.info("recommend_empty_results")
            return "none", {}
        
        if len(results) == 1 and len(results[0]) == 1:
            # Single number result
            logger.info("recommend_metric_card")
            return "none", {"type": "metric", "value": list(results[0].values())[0]}
        
        # Analyze data structure
        columns = list(results[0].keys())
        logger.debug("analyzing_results", num_rows=len(results), num_columns=len(columns))
        
        # Check for time series pattern
        time_series = self._detect_time_series(results, columns)
        if time_series:
            logger.info("recommend_chart", chart_type="line")
            config = self._build_time_series_config(results, time_series["date_col"], time_series["metric_col"])
            return "line", config
        
        # Check for categorical data
        categorical = self._detect_categorical(results, columns)
        if categorical:
            logger.info("recommend_chart", chart_type="bar")
            config = self._build_categorical_config(results, categorical["cat_col"], categorical["metric_col"])
            return "bar", config
        
        # Check for part-of-whole pattern
        part_of_whole = self._detect_part_of_whole(results, columns)
        if part_of_whole:
            logger.info("recommend_chart", chart_type="pie")
            config = self._build_part_of_whole_config(results, part_of_whole["label_col"], part_of_whole["value_col"])
            return "pie", config
        
        # Check for scatter pattern (two numeric columns)
        scatter = self._detect_scatter(results, columns)
        if scatter and len(results) > 3:
            logger.info("recommend_chart", chart_type="scatter")
            config = self._build_scatter_config(results, scatter["x_col"], scatter["y_col"])
            return "scatter", config
        
        # Default to table
        logger.info("recommend_chart", chart_type="table", reason="no_clear_pattern")
        config = {"display": "table"}
        return "table", config
    
    def _detect_time_series(
        self,
        results: List[Dict[str, Any]],
        columns: List[str]
    ) -> Dict[str, str]:
        """
        Detect if data is a time series (date column + numeric metric).
        
        Args:
            results: Query results
            columns: Column names
        
        Returns:
            Dict with date_col and metric_col if pattern detected, empty dict otherwise
        """
        date_cols = [col for col in columns if self._is_date_column(results, col)]
        metric_cols = [col for col in columns if self._is_numeric_column(results, col) and col not in date_cols]
        
        if date_cols and metric_cols and len(results) >= 3:
            return {
                "date_col": date_cols[0],
                "metric_col": metric_cols[0]
            }
        
        return {}
    
    def _detect_categorical(
        self,
        results: List[Dict[str, Any]],
        columns: List[str]
    ) -> Dict[str, str]:
        """
        Detect categorical comparison pattern (< 10 categories + metric).
        
        Args:
            results: Query results
            columns: Column names
        
        Returns:
            Dict with cat_col and metric_col if pattern detected
        """
        cat_cols = [col for col in columns if self._is_categorical_column(results, col)]
        metric_cols = [col for col in columns if self._is_numeric_column(results, col) and col not in cat_cols]
        
        if cat_cols and metric_cols:
            # Check if categories are limited (< 10)
            unique_count = len(set(str(row[cat_cols[0]]) for row in results))
            if unique_count < 10 and unique_count >= 2:
                return {
                    "cat_col": cat_cols[0],
                    "metric_col": metric_cols[0]
                }
        
        return {}
    
    def _detect_part_of_whole(
        self,
        results: List[Dict[str, Any]],
        columns: List[str]
    ) -> Dict[str, str]:
        """
        Detect part-of-whole pattern (percentages or values summing to ~100%).
        
        Args:
            results: Query results
            columns: Column names
        
        Returns:
            Dict with label_col and value_col if pattern detected
        """
        if len(columns) < 2:
            return {}
        
        # Look for numeric columns that might represent percentages/portions
        numeric_cols = [col for col in columns if self._is_numeric_column(results, col)]
        
        if len(numeric_cols) >= 1:
            # Get total of first numeric column
            total = sum(float(row.get(numeric_cols[0], 0)) for row in results if row.get(numeric_cols[0]))
            
            # If total is close to 100, likely a pie chart
            if 95 < total < 105 or 0.95 < total < 1.05:
                # Use first non-numeric column as label
                label_cols = [col for col in columns if col not in numeric_cols]
                if label_cols:
                    return {
                        "label_col": label_cols[0],
                        "value_col": numeric_cols[0]
                    }
        
        return {}
    
    def _detect_scatter(
        self,
        results: List[Dict[str, Any]],
        columns: List[str]
    ) -> Dict[str, str]:
        """
        Detect scatter pattern (two numeric columns).
        
        Args:
            results: Query results
            columns: Column names
        
        Returns:
            Dict with x_col and y_col if pattern detected
        """
        numeric_cols = [col for col in columns if self._is_numeric_column(results, col)]
        
        if len(numeric_cols) >= 2:
            return {
                "x_col": numeric_cols[0],
                "y_col": numeric_cols[1]
            }
        
        return {}
    
    def _is_date_column(self, results: List[Dict[str, Any]], col: str) -> bool:
        """Check if column contains date/datetime values."""
        for row in results[:5]:  # Check first 5 rows
            val = row.get(col)
            if val and isinstance(val, (datetime, date)):
                return True
            if val and isinstance(val, str) and self._looks_like_date(val):
                return True
        return False
    
    def _is_numeric_column(self, results: List[Dict[str, Any]], col: str) -> bool:
        """Check if column contains numeric values."""
        for row in results[:5]:
            val = row.get(col)
            if val is not None:
                try:
                    float(val)
                    return True
                except (TypeError, ValueError):
                    return False
        return False
    
    def _is_categorical_column(self, results: List[Dict[str, Any]], col: str) -> bool:
        """Check if column contains categorical (string) values."""
        for row in results[:5]:
            val = row.get(col)
            if val and isinstance(val, str) and not self._looks_like_date(val):
                return True
        return False
    
    def _looks_like_date(self, s: str) -> bool:
        """Check if string looks like a date."""
        date_patterns = [
            "-",  # YYYY-MM-DD or YYYY-MM
            "/",  # MM/DD/YYYY
            "T",  # ISO format
        ]
        return any(pattern in s for pattern in date_patterns) and len(s.split()[0]) >= 8
    
    def _build_time_series_config(
        self,
        results: List[Dict[str, Any]],
        date_col: str,
        metric_col: str
    ) -> Dict[str, Any]:
        """Build configuration for time series chart."""
        return {
            "type": "line",
            "x_column": date_col,
            "y_column": metric_col,
            "title": f"{metric_col} over {date_col}",
            "show_legend": True,
            "responsive": True
        }
    
    def _build_categorical_config(
        self,
        results: List[Dict[str, Any]],
        cat_col: str,
        metric_col: str
    ) -> Dict[str, Any]:
        """Build configuration for categorical bar chart."""
        return {
            "type": "bar",
            "x_column": cat_col,
            "y_column": metric_col,
            "title": f"{metric_col} by {cat_col}",
            "show_legend": True,
            "responsive": True
        }
    
    def _build_part_of_whole_config(
        self,
        results: List[Dict[str, Any]],
        label_col: str,
        value_col: str
    ) -> Dict[str, Any]:
        """Build configuration for pie chart."""
        return {
            "type": "pie",
            "label_column": label_col,
            "value_column": value_col,
            "title": f"Distribution of {value_col}",
            "show_legend": True,
            "responsive": True
        }
    
    def _build_scatter_config(
        self,
        results: List[Dict[str, Any]],
        x_col: str,
        y_col: str
    ) -> Dict[str, Any]:
        """Build configuration for scatter plot."""
        return {
            "type": "scatter",
            "x_column": x_col,
            "y_column": y_col,
            "title": f"{y_col} vs {x_col}",
            "show_legend": True,
            "responsive": True
        }

