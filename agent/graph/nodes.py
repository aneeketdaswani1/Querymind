"""Graph node implementations for QueryMind.

Contains individual node functions that process state and represent steps in the
SQL generation and analysis workflow (schema loading, SQL generation, safety checks, etc.).

Each node:
- Receives the complete QueryMindState
- Performs one focused task
- Returns a dict of state updates
- Is typed as async for non-blocking operations
"""

import structlog
from typing import Dict, Any

from agent.graph.state import QueryMindState
from agent.core.schema_loader import SchemaLoader
from agent.core.sql_generator import SQLGenerator, ConversationMessage
from agent.core.safety_checker import SafetyChecker
from agent.core.query_executor import QueryExecutor
from agent.core.viz_recommender import VizRecommender
from agent.core.insight_narrator import InsightNarrator
from agent.config import AGENT_DATABASE_URL, ANTHROPIC_API_KEY, LLM_MODEL

from langchain_anthropic import ChatAnthropic

logger = structlog.get_logger(__name__)

# Singleton instances (initialized once)
_schema_loader = None
_sql_generator = None
_safety_checker = None
_query_executor = None
_viz_recommender = None
_insight_narrator = None


def _initialize_components():
    """Initialize all components on first use."""
    global _schema_loader, _sql_generator, _safety_checker, _query_executor, _viz_recommender, _insight_narrator
    
    if _schema_loader is not None:
        return  # Already initialized
    
    logger.info("initializing_graph_components")
    
    # Initialize LLM client
    llm = ChatAnthropic(
        api_key=ANTHROPIC_API_KEY,
        model=LLM_MODEL,
        temperature=0.7
    )
    
    # Initialize components
    _schema_loader = SchemaLoader(AGENT_DATABASE_URL)
    _sql_generator = SQLGenerator(llm, _schema_loader)
    _safety_checker = SafetyChecker()
    _query_executor = QueryExecutor(AGENT_DATABASE_URL)
    _viz_recommender = VizRecommender()
    _insight_narrator = InsightNarrator(llm)
    
    logger.info("graph_components_initialized")


# ============================================================================
# NODE 1: LOAD SCHEMA
# ============================================================================

async def load_schema(state: QueryMindState) -> Dict[str, Any]:
    """
    Load database schema into state. Only runs once per session (cached).
    
    This node introspects the PostgreSQL database and caches the schema text
    for use in SQL generation. The schema includes table definitions, columns,
    sample values for categorical columns, and foreign key relationships.
    
    Args:
        state: Current QueryMindState
    
    Returns:
        Dict with updated state containing schema_text
    """
    _initialize_components()
    
    logger.info("load_schema_node_started", active_database=state.active_database)
    
    try:
        # If schema already loaded, skip
        if state.schema_text:
            logger.debug("schema_already_loaded_in_state")
            return {"schema_text": state.schema_text}
        
        # Get schema from loader (cached internally)
        schema_text = _schema_loader.get_schema_text()
        
        logger.info(
            "schema_loaded",
            schema_length=len(schema_text),
            active_database=state.active_database
        )
        
        return {"schema_text": schema_text}
    
    except Exception as e:
        logger.error("load_schema_failed", error=str(e))
        return {
            "schema_text": "",
            "status": "error",
            "execution_error": f"Failed to load schema: {str(e)}"
        }


# ============================================================================
# NODE 2: GENERATE SQL
# ============================================================================

async def generate_sql(state: QueryMindState) -> Dict[str, Any]:
    """
    Call SQLGenerator to convert question to SQL. Returns updated state
    with generated_sql, confidence, and other LLM output fields.
    
    This node uses the LLM with the schema context and few-shot examples
    to generate SQL that answers the user's question. It handles:
    - Low confidence: returns clarification_needed status
    - Conversation history: includes previous messages for multi-turn support
    - Error handling: graceful fallback on LLM failures
    
    Args:
        state: Current QueryMindState with current_question set
    
    Returns:
        Dict with: generated_sql, sql_explanation, sql_confidence, sql_assumptions,
        needs_clarification, clarification_question
    """
    _initialize_components()
    
    logger.info("generate_sql_node_started", question=state.current_question[:80])
    
    try:
        # Convert state messages to ConversationMessage format for SQLGenerator
        conversation_history = []
        if state.messages:
            for msg in state.messages:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    conversation_history.append(
                        ConversationMessage(role=msg["role"], content=msg["content"])
                    )
        
        # Call SQL generator
        result = await _sql_generator.generate(
            question=state.current_question,
            conversation_history=conversation_history if conversation_history else None,
            max_retries=2
        )
        
        logger.info(
            "sql_generated",
            status=result.status,
            confidence=result.confidence,
            has_sql=result.sql is not None
        )
        
        # Handle different statuses
        if result.status == "clarification_needed":
            return {
                "needs_clarification": True,
                "clarification_question": result.clarification_question,
                "status": "clarifying"
            }
        
        if result.status == "out_of_scope":
            return {
                "status": "error",
                "execution_error": f"Question is out of scope: {result.explanation}"
            }
        
        # SQL generated successfully
        return {
            "generated_sql": result.sql,
            "sql_explanation": result.explanation,
            "sql_confidence": result.confidence,
            "sql_assumptions": result.assumptions,
            "status": "checking"  # Move to safety check
        }
    
    except Exception as e:
        logger.error("sql_generation_error", error=str(e))
        return {
            "status": "error",
            "execution_error": f"Failed to generate SQL: {str(e)}"
        }


# ============================================================================
# NODE 3: CHECK SAFETY
# ============================================================================

async def check_safety(state: QueryMindState) -> Dict[str, Any]:
    """
    Run SafetyChecker on the generated SQL. Sets safety_check_passed = True/False.
    
    This node validates that the generated SQL:
    - Contains only SELECT/WITH operations (no INSERT/UPDATE/DELETE/DROP/ALTER)
    - Is a single statement (no multiple statements or chaining)
    - Doesn't have dangerous SQL injection patterns
    - Is approved for execution
    
    If safety check fails, transitions to error state. If it passes, moves to execution.
    
    Args:
        state: Current QueryMindState with generated_sql set
    
    Returns:
        Dict with: safety_check_passed, safety_check_reason, and next status
    """
    _initialize_components()
    
    logger.info("check_safety_node_started", has_sql=state.generated_sql is not None)
    
    if not state.generated_sql:
        logger.warning("check_safety_no_sql_to_check")
        return {
            "safety_check_passed": False,
            "safety_check_reason": "No SQL query to check",
            "status": "error"
        }
    
    try:
        schema_dict = _schema_loader.get_schema_dict()

        # Run safety check
        safety_result = _safety_checker.check(state.generated_sql, schema=schema_dict)
        
        logger.info(
            "safety_check_completed",
            is_safe=safety_result.passed,
            reason=safety_result.reason,
        )
        
        if not safety_result.passed:
            return {
                "safety_check_passed": False,
                "safety_check_reason": safety_result.reason,
                "status": "error",
                "execution_error": f"Safety check failed: {safety_result.reason}"
            }
        
        # Safety check passed - proceed to execution
        return {
            "safety_check_passed": True,
            "safety_check_reason": safety_result.reason,
            "generated_sql": safety_result.sanitized_sql,
            "status": "executing"
        }
    
    except Exception as e:
        logger.error("safety_check_error", error=str(e))
        return {
            "safety_check_passed": False,
            "safety_check_reason": f"Error during safety check: {str(e)}",
            "status": "error"
        }


# ============================================================================
# NODE 4: EXECUTE QUERY
# ============================================================================

async def execute_query(state: QueryMindState) -> Dict[str, Any]:
    """
    Execute the validated SQL. Capture results, row_count, execution_time.
    Handle errors gracefully.
    
    This node executes the safe, validated SQL against PostgreSQL using a
    read-only connection. It:
    - Times the execution
    - Limits result rows to prevent memory issues
    - Serializes datetime/date objects to ISO strings
    - Captures detailed error messages on failure
    - Increments retry count for error handling
    
    Args:
        state: Current QueryMindState with safety_check_passed=True
    
    Returns:
        Dict with: query_results, row_count, execution_time_ms, execution_error,
        and next status (executing -> visualizing on success, executing -> error on failure)
    """
    _initialize_components()
    
    logger.info("execute_query_node_started", has_sql=state.generated_sql is not None)
    
    if not state.generated_sql or not state.safety_check_passed:
        logger.warning("execute_query_preconditions_not_met")
        return {
            "status": "error",
            "execution_error": "Query not ready for execution (missing SQL or failed safety check)"
        }
    
    try:
        # Execute query
        results, row_count, execution_time_ms, error_msg = await _query_executor.execute(
            sql=state.generated_sql
        )
        
        logger.info(
            "query_executed",
            row_count=row_count,
            execution_time_ms=execution_time_ms,
            has_error=bool(error_msg)
        )
        
        if error_msg:
            # Execution failed
            return {
                "query_results": [],
                "row_count": 0,
                "execution_time_ms": execution_time_ms,
                "execution_error": error_msg,
                "retry_count": state.retry_count + 1,
                "status": "error"
            }
        
        # Execution successful
        return {
            "query_results": results,
            "row_count": row_count,
            "execution_time_ms": execution_time_ms,
            "execution_error": None,
            "retry_count": 0,  # Reset retry count on success
            "status": "visualizing"
        }
    
    except Exception as e:
        logger.error("execute_query_error", error=str(e))
        return {
            "query_results": [],
            "row_count": 0,
            "execution_time_ms": 0.0,
            "execution_error": f"Query execution error: {str(e)}",
            "retry_count": state.retry_count + 1,
            "status": "error"
        }


# ============================================================================
# NODE 5: HANDLE ERROR
# ============================================================================

async def handle_error(state: QueryMindState) -> Dict[str, Any]:
    """
    If execution fails, increment retry_count. If retries < 2, trigger SQL
    refinement. Else return error message.
    
    This node handles query execution failures by:
    - Checking if we're under the retry limit (max 2 retries)
    - If retries available: calling SQLGenerator.refine() with the error message
    - If retries exhausted: returning the error to the user
    - Updating status accordingly
    
    Args:
        state: Current QueryMindState with execution_error set
    
    Returns:
        Dict with: status, generated_sql (refined if retried), execution_error (if final),
        and retry_count
    """
    _initialize_components()
    
    logger.info(
        "handle_error_node_started",
        retry_count=state.retry_count,
        error=state.execution_error[:100] if state.execution_error else None
    )
    
    if not state.execution_error:
        logger.debug("handle_error_no_error_to_handle")
        return {"status": "done"}
    
    # Check if we can retry
    max_retries = 2
    if state.retry_count >= max_retries:
        logger.warning("execute_max_retries_exceeded", retry_count=state.retry_count)
        return {
            "status": "error",
            "execution_error": f"Query failed after {max_retries} retries: {state.execution_error}"
        }
    
    try:
        logger.info("attempting_sql_refinement", retry_count=state.retry_count)
        
        # Convert messages to ConversationMessage format
        conversation_history = []
        if state.messages:
            for msg in state.messages:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    conversation_history.append(
                        ConversationMessage(role=msg["role"], content=msg["content"])
                    )
        
        # Call SQLGenerator.refine() to fix the query
        refined_result = await _sql_generator.refine(
            original_sql=state.generated_sql or "",
            error_message=state.execution_error,
            question=state.current_question,
            conversation_history=conversation_history if conversation_history else None
        )
        
        logger.info(
            "sql_refined",
            confidence=refined_result.confidence,
            has_sql=refined_result.sql is not None
        )
        
        # Return refined SQL for re-execution
        return {
            "generated_sql": refined_result.sql,
            "sql_explanation": refined_result.explanation,
            "retry_count": state.retry_count + 1,
            "status": "checking"  # Go back to safety check with refined SQL
        }
    
    except Exception as e:
        logger.error("sql_refinement_error", error=str(e))
        return {
            "status": "error",
            "execution_error": f"Failed to refine query: {state.execution_error}"
        }


# ============================================================================
# NODE 6: RECOMMEND VISUALIZATION
# ============================================================================

async def recommend_viz(state: QueryMindState) -> Dict[str, Any]:
    """
    Analyze query results and pick the best chart type. Rules:
    - Time series data (date column + metric) -> line chart
    - Categorical comparison (< 10 categories + metric) -> bar chart
    - Part-of-whole (percentages summing to ~100%) -> pie chart
    - Two numeric columns -> scatter plot
    - > 10 rows with no clear pattern -> table
    - Single number result -> big number card
    
    Sets chart_type and chart_config in state.
    
    Args:
        state: Current QueryMindState with query_results set
    
    Returns:
        Dict with: chart_type, chart_config, and next status (narrating)
    """
    _initialize_components()
    
    logger.info(
        "recommend_viz_node_started",
        row_count=state.row_count,
        has_results=state.query_results is not None
    )
    
    if not state.query_results:
        logger.warning("recommend_viz_no_results")
        return {
            "chart_type": "none",
            "chart_config": {},
            "status": "narrating"
        }
    
    try:
        # Get visualization recommendation
        sample_row = state.query_results[0] if state.query_results else {}
        column_types = {
            col: _infer_column_type(state.query_results, col)
            for col in sample_row.keys()
        }
        viz_config = _viz_recommender.recommend(
            sql=state.generated_sql or "",
            results=state.query_results,
            column_types=column_types,
        )
        
        logger.info(
            "viz_recommended",
            chart_type=viz_config.chart_type,
            num_results=len(state.query_results)
        )
        
        return {
            "chart_type": viz_config.chart_type,
            "chart_config": viz_config.to_dict(),
            "status": "narrating"
        }
    
    except Exception as e:
        logger.error("viz_recommendation_error", error=str(e))
        return {
            "chart_type": "table",
            "chart_config": {"display": "table"},
            "status": "narrating"
        }


def _infer_column_type(results: list[dict], column: str) -> str:
    """Infer coarse type for a result column: numeric, date, or categorical."""
    values = [row.get(column) for row in results[:10] if row.get(column) is not None]
    if not values:
        return "categorical"

    # Numeric check
    numeric_hits = 0
    for value in values:
        try:
            float(value)
            numeric_hits += 1
        except (TypeError, ValueError):
            pass
    if numeric_hits >= max(1, int(0.8 * len(values))):
        return "numeric"

    # Date-ish check
    date_tokens = ["-", "/", "T", ":"]
    if all(isinstance(v, str) and any(t in v for t in date_tokens) for v in values):
        return "date"

    return "categorical"


# ============================================================================
# NODE 7: GENERATE INSIGHT
# ============================================================================

async def generate_insight(state: QueryMindState) -> Dict[str, Any]:
    """
    Use LLM to generate a natural language summary of the results.
    Include: what the data shows, key trends, anomalies, and a recommended action.
    Format as insight_text (paragraph) and key_findings (3-5 bullet points).
    
    Args:
        state: Current QueryMindState with query_results set
    
    Returns:
        Dict with: insight_text, key_findings, and next status (done)
    """
    _initialize_components()
    
    logger.info(
        "generate_insight_node_started",
        row_count=state.row_count,
        question=state.current_question[:80]
    )
    
    if not state.query_results:
        logger.warning("generate_insight_no_results")
        return {
            "insight_text": "No data to analyze.",
            "key_findings": [],
            "status": "done"
        }
    
    try:
        # Generate insights
        insight_text, key_findings = await _insight_narrator.generate(
            results=state.query_results,
            query=state.generated_sql or "",
            sql_explanation=state.sql_explanation or "",
            question=state.current_question
        )
        
        logger.info(
            "insight_generated",
            num_findings=len(key_findings),
            text_length=len(insight_text)
        )
        
        return {
            "insight_text": insight_text,
            "key_findings": key_findings,
            "status": "done"
        }
    
    except Exception as e:
        logger.error("insight_generation_error", error=str(e))
        # Return fallback
        return {
            "insight_text": f"Query returned {state.row_count} rows.",
            "key_findings": [],
            "status": "done"
        }


# ============================================================================
# NODE 8: ASK CLARIFICATION
# ============================================================================

async def ask_clarification(state: QueryMindState) -> Dict[str, Any]:
    """
    Return the clarification question to the user and pause for input.
    
    This node is reached when the LLM determined the user's question was
    ambiguous and needs clarification before proceeding with SQL generation.
    
    The clarification_question is set in state and will be returned to the user.
    After the user responds with clarification, a new query cycle begins.
    
    Args:
        state: Current QueryMindState with needs_clarification=True
    
    Returns:
        Dict with: status=clarifying, and clarification_question already in state
    """
    logger.info(
        "ask_clarification_node_started",
        question=state.clarification_question[:100] if state.clarification_question else None
    )
    
    # Simply transition to clarifying status - the question is already in state
    return {
        "status": "clarifying"
    }

