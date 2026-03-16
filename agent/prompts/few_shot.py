"""Few-shot examples for QueryMind agent.

Provides example question-SQL pairs to improve LLM performance through in-context learning
for SQL generation tasks. Includes dynamic example selection based on question similarity
to surface the most relevant patterns for a given query.
"""

from typing import List, Dict, Any, Optional
import re
from difflib import SequenceMatcher
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# FEW-SHOT EXAMPLES - DIVERSE BUSINESS QUESTIONS WITH SQL SOLUTIONS
# ============================================================================

FEW_SHOT_EXAMPLES = [
    {
        "question": "What are our top 5 products by revenue?",
        "sql": "SELECT p.name, ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount / 100))::NUMERIC, 2) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.id GROUP BY p.id, p.name ORDER BY revenue DESC LIMIT 5;",
        "explanation": "Joins order_items with products, calculates revenue accounting for discounts, groups by product, sorts descending.",
        "schema": "ecommerce",
        "patterns": ["JOIN", "GROUP BY", "ORDER BY", "SUM", "LIMIT"]
    },
    {
        "question": "What is our monthly revenue trend for 2024?",
        "sql": "SELECT DATE_TRUNC('month', o.order_date)::DATE AS month, ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount / 100))::NUMERIC, 2) AS revenue FROM orders o JOIN order_items oi ON o.id = oi.order_id WHERE o.order_date >= '2024-01-01' AND o.order_date < '2025-01-01' GROUP BY DATE_TRUNC('month', o.order_date) ORDER BY month;",
        "explanation": "Truncates dates to month, filters to 2024, aggregates revenue per month, orders chronologically.",
        "schema": "ecommerce",
        "patterns": ["DATE_TRUNC", "WHERE", "GROUP BY", "ORDER BY", "SUM"]
    },
    {
        "question": "Show customer revenue breakdown by segment",
        "sql": "SELECT c.segment, COUNT(DISTINCT c.id) AS customer_count, ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount / 100))::NUMERIC, 2) AS total_revenue, ROUND(AVG(oi.quantity * oi.unit_price * (1 - oi.discount / 100))::NUMERIC, 2) AS avg_revenue_per_order FROM customers c JOIN orders o ON c.id = o.customer_id JOIN order_items oi ON o.id = oi.order_id GROUP BY c.segment ORDER BY total_revenue DESC;",
        "explanation": "Multi-table JOIN with customers, orders, and order_items. Uses GROUP BY with COUNT DISTINCT for customer uniqueness.",
        "schema": "ecommerce",
        "patterns": ["JOIN", "GROUP BY", "COUNT DISTINCT", "SUM", "AVG", "HAVING"]
    },
    {
        "question": "Which products have the highest return rate?",
        "sql": "WITH product_returns AS (SELECT p.id, p.name, COUNT(oi.id) as total_sold, COUNT(r.id) as returned FROM products p JOIN order_items oi ON p.id = oi.product_id LEFT JOIN returns r ON oi.id = r.order_item_id GROUP BY p.id, p.name) SELECT name, ROUND(100.0 * returned / NULLIF(total_sold, 0), 2) AS return_rate_pct FROM product_returns WHERE total_sold > 10 ORDER BY return_rate_pct DESC LIMIT 10;",
        "explanation": "Uses CTE with LEFT JOIN to include all products. Calculates percentage with NULLIF to prevent division by zero. HAVING filters for significance.",
        "schema": "ecommerce",
        "patterns": ["CTE", "LEFT JOIN", "CASE WHEN", "NULLIF", "COUNT", "WHERE HAVING"]
    },
    {
        "question": "What is the average order value by customer segment?",
        "sql": "SELECT c.segment, COUNT(o.id) AS order_count, COUNT(DISTINCT c.id) AS customer_count, ROUND(AVG(order_total)::NUMERIC, 2) AS avg_order_value FROM customers c JOIN orders o ON c.id = o.customer_id JOIN (SELECT order_id, SUM(quantity * unit_price * (1 - discount / 100)) as order_total FROM order_items GROUP BY order_id) oi_totals ON o.id = oi_totals.order_id GROUP BY c.segment ORDER BY avg_order_value DESC;",
        "explanation": "Subquery calculates order totals, then joined with main query. Demonstrates nested calculation pattern.",
        "schema": "ecommerce",
        "patterns": ["SUBQUERY", "JOIN", "GROUP BY", "SUM", "AVG"]
    },
    {
        "question": "What is our monthly recurring revenue (MRR) by plan tier?",
        "sql": "SELECT u.plan, ROUND(SUM(u.mrr)::NUMERIC, 2) AS total_mrr, COUNT(DISTINCT u.id) AS active_users, ROUND(AVG(u.mrr)::NUMERIC, 2) AS avg_mrr_per_user FROM users u WHERE u.status = 'active' GROUP BY u.plan ORDER BY total_mrr DESC;",
        "explanation": "Filters only active users, groups by plan tier, calculates aggregate MRR metrics per segment.",
        "schema": "saas",
        "patterns": ["WHERE", "GROUP BY", "SUM", "AVG", "COUNT", "ORDER BY"]
    },
    {
        "question": "Show daily active users trend over the last 90 days",
        "sql": "SELECT e.event_date, COUNT(DISTINCT e.user_id) AS daily_active_users FROM events e WHERE e.event_date >= CURRENT_DATE - INTERVAL '90 days' GROUP BY e.event_date ORDER BY e.event_date DESC;",
        "explanation": "Filters events to last 90 days using date math, counts distinct users per day for DAU metric.",
        "schema": "saas",
        "patterns": ["WHERE", "INTERVAL", "COUNT DISTINCT", "GROUP BY", "ORDER BY"]
    },
    {
        "question": "Calculate customer lifetime value segments",
        "sql": "WITH customer_metrics AS (SELECT u.id, u.plan, u.mrr, COUNT(DISTINCT i.id) AS invoice_count, ROUND(SUM(CASE WHEN i.status = 'paid' THEN i.amount ELSE 0 END)::NUMERIC, 2) AS total_paid FROM users u LEFT JOIN invoices i ON u.id = i.user_id GROUP BY u.id, u.plan, u.mrr) SELECT id, plan, mrr, invoice_count, total_paid, CASE WHEN mrr > 500 THEN 'HIGH_VALUE' WHEN mrr > 100 THEN 'MID_VALUE' ELSE 'LOW_VALUE' END AS customer_segment FROM customer_metrics ORDER BY total_paid DESC;",
        "explanation": "CTE with LEFT JOIN and CASE WHEN for segmentation. Demonstrates complex aggregation with conditional SUM.",
        "schema": "saas",
        "patterns": ["CTE", "LEFT JOIN", "CASE WHEN", "SUM", "GROUP BY"]
    },
    {
        "question": "Top features by adoption rate among paying customers",
        "sql": "WITH paying_users AS (SELECT DISTINCT u.id FROM users u WHERE u.plan != 'free'), feature_stats AS (SELECT f.feature_name, COUNT(DISTINCT f.user_id) as users_with_feature, SUM(f.usage_count) as total_usage FROM features_usage f JOIN paying_users pu ON f.user_id = pu.id WHERE f.date >= CURRENT_DATE - INTERVAL '30 days' GROUP BY f.feature_name) SELECT feature_name, users_with_feature, total_usage, ROUND(100.0 * total_usage / NULLIF(users_with_feature * (SELECT COUNT(DISTINCT id) FROM paying_users), 0), 2) AS adoption_score FROM feature_stats ORDER BY adoption_score DESC LIMIT 10;",
        "explanation": "Multiple CTEs, JOIN with aggregation, window-like calculation. Shows complex real-world analytics pattern.",
        "schema": "saas",
        "patterns": ["CTE", "JOIN", "SUBQUERY", "GROUP BY", "CASE WHEN", "NULLIF"]
    },
    {
        "question": "Orders with highest discount percentage that had returns",
        "sql": "SELECT o.id, c.segment, o.order_date, COUNT(oi.id) AS items_ordered, COUNT(r.id) AS items_returned, ROUND(100.0 * AVG(oi.discount), 2) AS avg_discount_pct, ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount / 100))::NUMERIC, 2) AS order_revenue FROM orders o JOIN customers c ON o.customer_id = c.id JOIN order_items oi ON o.id = oi.order_id LEFT JOIN returns r ON oi.id = r.order_item_id WHERE r.id IS NOT NULL GROUP BY o.id, c.segment, o.order_date HAVING AVG(oi.discount) > 10 ORDER BY avg_discount_pct DESC LIMIT 20;",
        "explanation": "Complex JOIN chain with LEFT JOIN for returns, HAVING clause filters, demonstrates discount vs return correlation.",
        "schema": "ecommerce",
        "patterns": ["JOIN", "LEFT JOIN", "GROUP BY", "HAVING", "WHERE", "AVG", "ROUND"]
    },
    {
        "question": "Churn analysis: Which cohorts have highest retention?",
        "sql": "WITH user_cohorts AS (SELECT DATE_TRUNC('month', u.signup_date)::DATE AS signup_cohort, u.id, u.status FROM users u), cohort_stats AS (SELECT signup_cohort, COUNT(*) AS cohort_size, COUNT(CASE WHEN status = 'active' THEN 1 END) AS active_count, COUNT(CASE WHEN status = 'churned' THEN 1 END) AS churned_count FROM user_cohorts GROUP BY signup_cohort) SELECT signup_cohort, cohort_size, active_count, churned_count, ROUND(100.0 * active_count / NULLIF(cohort_size, 0), 2) AS retention_pct FROM cohort_stats WHERE cohort_size > 10 ORDER BY signup_cohort DESC;",
        "explanation": "CTE for cohort grouping, multiple conditional COUNTs for status tracking, percentage calculation with NULL safety.",
        "schema": "saas",
        "patterns": ["CTE", "GROUP BY", "CASE WHEN", "COUNT", "NULLIF", "DATE_TRUNC"]
    }
]


# ============================================================================
# UTILITY FUNCTIONS FOR EXAMPLE SELECTION
# ============================================================================

def _tokenize(text: str) -> set:
    """
    Tokenize text into lowercase words for similarity comparison.
    
    Args:
        text: Text to tokenize
    
    Returns:
        Set of tokens (words)
    """
    # Convert to lowercase and split on whitespace/punctuation
    text = text.lower()
    tokens = re.findall(r'\b\w+\b', text)
    return set(tokens)


def _extract_sql_patterns(sql: str) -> set:
    """
    Extract SQL keywords and patterns from a query.
    
    Args:
        sql: SQL query string
    
    Returns:
        Set of SQL patterns (SELECT, JOIN, GROUP BY, etc.)
    """
    patterns = set()
    sql_upper = sql.upper()
    
    # Check for common SQL patterns
    if 'SELECT' in sql_upper:
        patterns.add('SELECT')
    if 'JOIN' in sql_upper:
        patterns.add('JOIN')
    if 'GROUP BY' in sql_upper:
        patterns.add('GROUP_BY')
    if 'HAVING' in sql_upper:
        patterns.add('HAVING')
    if 'WHERE' in sql_upper:
        patterns.add('WHERE')
    if 'ORDER BY' in sql_upper:
        patterns.add('ORDER_BY')
    if 'LIMIT' in sql_upper:
        patterns.add('LIMIT')
    if 'WITH' in sql_upper:
        patterns.add('CTE')
    if 'CASE WHEN' in sql_upper:
        patterns.add('CASE_WHEN')
    if 'LEFT JOIN' in sql_upper:
        patterns.add('LEFT_JOIN')
    if 'SUBQUERY' in sql_upper or '(SELECT' in sql_upper:
        patterns.add('SUBQUERY')
    if 'WINDOW' in sql_upper or 'OVER' in sql_upper or 'ROW_NUMBER' in sql_upper:
        patterns.add('WINDOW_FUNCTION')
    if 'SUM(' in sql_upper or 'AVG(' in sql_upper or 'COUNT(' in sql_upper or 'MIN(' in sql_upper or 'MAX(' in sql_upper:
        patterns.add('AGGREGATION')
    if 'DATE_TRUNC' in sql_upper or 'INTERVAL' in sql_upper or 'CURRENT_DATE' in sql_upper:
        patterns.add('DATE_MATH')
    if 'COALESCE' in sql_upper or 'NULLIF' in sql_upper or 'CASE' in sql_upper:
        patterns.add('NULL_HANDLING')
    if '::' in sql_upper:
        patterns.add('CASTING')
    
    return patterns


def _calculate_similarity(question: str, example_question: str, example_patterns: set) -> float:
    """
    Calculate similarity between a question and an example question.
    
    Combines:
    1. Token overlap similarity (Jaccard)
    2. Sequence matching ratio
    3. SQL pattern matching
    
    Args:
        question: User's question
        example_question: Example question to compare against
        example_patterns: SQL patterns from the example
    
    Returns:
        Similarity score (0 to 1)
    """
    # Token overlap (Jaccard similarity)
    user_tokens = _tokenize(question)
    example_tokens = _tokenize(example_question)
    
    if not user_tokens or not example_tokens:
        jaccard_sim = 0.0
    else:
        intersection = len(user_tokens & example_tokens)
        union = len(user_tokens | example_tokens)
        jaccard_sim = intersection / union if union > 0 else 0.0
    
    # Sequence matching ratio
    sequence_sim = SequenceMatcher(None, 
                                   question.lower(), 
                                   example_question.lower()).ratio()
    
    # Extract patterns from user question
    # Simple heuristic: detect keywords
    user_patterns = set()
    question_lower = question.lower()
    
    if any(word in question_lower for word in ['monthly', 'daily', 'yearly', 'trend', 'over time', 'by month', 'by day']):
        user_patterns.add('DATE_MATH')
    if any(word in question_lower for word in ['top', 'highest', 'most', 'best', 'worst', 'lowest']):
        user_patterns.add('ORDER_BY')
    if any(word in question_lower for word in ['by', 'segment', 'group', 'breakdown', 'distribution']):
        user_patterns.add('GROUP_BY')
    if any(word in question_lower for word in ['churn', 'cohort', 'retention', 'lifetime']):
        user_patterns.add('CTE')
    if any(word in question_lower for word in ['rate', 'average', 'total', 'sum', 'count', 'number']):
        user_patterns.add('AGGREGATION')
    
    # Pattern matching
    pattern_overlap = len(user_patterns & example_patterns)
    pattern_sim = pattern_overlap / max(len(user_patterns | example_patterns), 1)
    
    # Weighted combination
    similarity = (0.4 * jaccard_sim) + (0.3 * sequence_sim) + (0.3 * pattern_sim)
    
    return similarity


def get_relevant_examples(
    question: str,
    schema_name: Optional[str] = None,
    k: int = 3
) -> List[Dict[str, Any]]:
    """
    Get the most relevant few-shot examples for a given question.
    
    Uses embedding similarity (token overlap, sequence matching, pattern matching)
    to select the most relevant examples dynamically. This improves SQL accuracy
    significantly over using all examples every time.
    
    Args:
        question: User's natural language question
        schema_name: Optional schema filter ('ecommerce' or 'saas')
        k: Number of examples to return (default 3)
    
    Returns:
        List of k most relevant examples, sorted by relevance score descending
    
    Example:
        >>> examples = get_relevant_examples("what are top products by revenue?", "ecommerce", k=3)
        >>> [example['sql'] for example in examples]  # Get SQL queries
    """
    # Filter examples by schema if specified
    candidate_examples = FEW_SHOT_EXAMPLES
    if schema_name:
        candidate_examples = [
            ex for ex in FEW_SHOT_EXAMPLES 
            if ex.get("schema") == schema_name
        ]
    
    if not candidate_examples:
        logger.warning("no_examples_for_schema", schema=schema_name, using_all=True)
        candidate_examples = FEW_SHOT_EXAMPLES
    
    # Calculate similarity for each example
    scored_examples = []
    for example in candidate_examples:
        similarity = _calculate_similarity(
            question,
            example["question"],
            set(example.get("patterns", []))
        )
        scored_examples.append({
            **example,
            "similarity_score": similarity
        })
    
    # Sort by similarity descending
    scored_examples.sort(key=lambda x: x["similarity_score"], reverse=True)
    
    # Return top k
    result = scored_examples[:k]
    
    logger.info(
        "relevant_examples_selected",
        question_snippet=question[:50],
        schema=schema_name,
        examples_returned=len(result),
        top_score=result[0]["similarity_score"] if result else 0,
        scores=[f"{ex['similarity_score']:.2f}" for ex in result]
    )
    
    return result


def format_examples_for_prompt(
    examples: List[Dict[str, Any]],
    include_explanation: bool = True
) -> str:
    """
    Format selected examples for inclusion in LLM prompt.
    
    Args:
        examples: List of example dicts from get_relevant_examples()
        include_explanation: Whether to include explanation in output
    
    Returns:
        Formatted string ready for LLM prompt injection
    """
    lines = []
    for i, ex in enumerate(examples, 1):
        lines.append(f"## Example {i}:")
        lines.append(f"**Question**: {ex['question']}")
        lines.append(f"**Query**:")
        lines.append("```sql")
        lines.append(ex['sql'])
        lines.append("```")
        if include_explanation and ex.get('explanation'):
            lines.append(f"**Explanation**: {ex['explanation']}")
        lines.append("")
    
    return "\n".join(lines)
