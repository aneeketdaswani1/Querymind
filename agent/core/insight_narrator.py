"""Insight narrator module for QueryMind.

Generates human-readable explanations and insights from query results using
natural language generation to help users understand data patterns and trends.
"""

from typing import List, Dict, Any, Tuple
import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

logger = structlog.get_logger(__name__)


INSIGHT_SYSTEM_PROMPT = """You are a data insights expert. Analyze the provided query results and generate:
1. A natural language summary (2-3 sentences) of what the data shows
2. 3-5 key findings as bullet points
3. Notable trends or anomalies
4. One recommended action or insight

Be concise, focus on actionable insights, and avoid jargon. Format as:
SUMMARY: [2-3 sentences]
KEY FINDINGS:
- [finding 1]
- [finding 2]
- [finding 3]
ANOMALIES: [if any, otherwise "None"]
RECOMMENDED ACTION: [specific action based on data]
"""


class InsightNarrator:
    """
    Generates human-readable insights from query results using Claude LLM.
    
    Features:
    - Summarizes query results in natural language
    - Identifies patterns and trends
    - Highlights anomalies
    - Provides actionable recommendations
    """
    
    def __init__(self, llm_client: ChatAnthropic):
        """
        Initialize InsightNarrator.
        
        Args:
            llm_client: Initialized ChatAnthropic client for Claude
        """
        self.llm = llm_client
        logger.debug("insight_narrator_initialized")
    
    async def generate(
        self,
        results: List[Dict[str, Any]],
        query: str,
        sql_explanation: str = "",
        question: str = ""
    ) -> Tuple[str, List[str]]:
        """
        Generate natural language insights from query results.
        
        Args:
            results: Query results (list of dicts)
            query: The SQL query that generated these results
            sql_explanation: Explanation of what the query does
            question: Original user question (for context)
        
        Returns:
            Tuple of (insight_text: str, key_findings: List[str])
            - insight_text: Full narrative summary with trends and recommendations
            - key_findings: List of 3-5 bullet point findings
        """
        if not results:
            logger.info("generate_insight_empty_results")
            return "No data returned from query.", []
        
        logger.debug(
            "generating_insight",
            num_rows=len(results),
            num_columns=len(results[0]) if results else 0
        )
        
        # Format results for LLM
        formatted_results = self._format_results_for_llm(results)
        
        # Build prompt
        prompt = self._build_prompt(
            formatted_results,
            query,
            sql_explanation,
            question
        )
        
        try:
            # Call LLM for insights
            message = await self.llm.ainvoke([
                SystemMessage(content=INSIGHT_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ])
            
            insight_full = message.content
            
            # Parse structured sections from response
            key_findings = self._extract_key_findings(insight_full)
            
            logger.info(
                "insight_generated",
                num_findings=len(key_findings),
                text_length=len(insight_full)
            )
            
            return insight_full, key_findings
        
        except Exception as e:
            logger.error("insight_generation_failed", error=str(e))
            # Fallback to simple summary
            fallback = self._generate_fallback_insight(results, question)
            return fallback, []
    
    def _format_results_for_llm(
        self,
        results: List[Dict[str, Any]],
        max_rows: int = 50
    ) -> str:
        """
        Format query results as readable text for LLM analysis.
        
        Args:
            results: Query results
            max_rows: Maximum rows to include (for token economy)
        
        Returns:
            Formatted results as string
        """
        if not results:
            return "No results"
        
        # Limit to max_rows
        displayed = results[:max_rows]
        
        lines = ["Query Results:"]
        lines.append(f"Total rows: {len(results)}")
        
        if len(results) > max_rows:
            lines.append(f"(Showing first {max_rows} rows)")
        
        lines.append("")
        
        # Table format
        columns = list(results[0].keys())
        header = " | ".join(str(c)[:15].ljust(15) for c in columns)
        lines.append(header)
        lines.append("-" * len(header))
        
        for row in displayed:
            values = []
            for col in columns:
                val = str(row.get(col, ""))[:15]
                values.append(val.ljust(15))
            lines.append(" | ".join(values))
        
        return "\n".join(lines)
    
    def _build_prompt(
        self,
        formatted_results: str,
        query: str,
        sql_explanation: str = "",
        question: str = ""
    ) -> str:
        """
        Build the prompt for insight generation.
        
        Args:
            formatted_results: Formatted query results
            query: SQL query
            sql_explanation: What the query does
            question: Original user question
        
        Returns:
            Complete prompt for LLM
        """
        parts = []
        
        if question:
            parts.append(f"Original Question: {question}")
            parts.append("")
        
        parts.append(f"Query: {query}")
        
        if sql_explanation:
            parts.append(f"What this query does: {sql_explanation}")
        
        parts.append("")
        parts.append(formatted_results)
        parts.append("")
        parts.append("Generate insights from this data:")
        
        return "\n".join(parts)
    
    def _extract_key_findings(self, insight_text: str) -> List[str]:
        """
        Extract key findings from the LLM response.
        
        Args:
            insight_text: Full insight text from LLM
        
        Returns:
            List of key finding bullet points
        """
        findings = []
        
        # Look for KEY FINDINGS section
        if "KEY FINDINGS:" in insight_text:
            start = insight_text.find("KEY FINDINGS:") + len("KEY FINDINGS:")
            end = insight_text.find("ANOMALIES:") if "ANOMALIES:" in insight_text else len(insight_text)
            findings_section = insight_text[start:end].strip()
            
            # Split by bullet points
            for line in findings_section.split("\n"):
                line = line.strip()
                if line and line.startswith("-"):
                    findings.append(line[1:].strip())
                elif line and line[0].isdigit() and "." in line:
                    findings.append(line.split(".", 1)[1].strip())
        
        return findings[:5]  # Return up to 5 findings
    
    def _generate_fallback_insight(
        self,
        results: List[Dict[str, Any]],
        question: str
    ) -> str:
        """
        Generate a simple fallback insight if LLM call fails.
        
        Args:
            results: Query results
            question: Original question
        
        Returns:
            Simple insight based on data
        """
        summary = f"Query returned {len(results)} rows."
        
        if question:
            summary += f" In response to: {question[:80]}..."
        
        if results:
            # Try to extract a simple fact
            first_row = results[0]
            if len(first_row) == 1:
                key, val = list(first_row.items())[0]
                summary += f" Result: {key} = {val}"
        
        return summary

