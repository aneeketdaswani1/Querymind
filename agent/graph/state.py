"""Graph state definitions for QueryMind.

Defines the Pydantic models representing the message state and intermediate results
flowing through the LangGraph nodes. The QueryMindState represents the complete
state of a query from question to final insights.

The state uses:
- Annotated[list, add_messages] for automatic message deduplication
- Literal types for status/chart types for type safety
- Optional fields for intermediate results
- Structured metadata for visualization and insights
"""

from typing import Literal, Optional, Annotated, List, Dict, Any
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


class QueryMindState(BaseModel):
    """
    The complete state that flows through the QueryMind agent graph.
    
    Represents all data needed to track a query from user question through
    SQL generation, execution, visualization, and insight generation.
    
    The state is designed to support multi-turn conversations and can be
    persisted between turns for context maintenance.
    """
    
    # ========================================================================
    # CONVERSATION CONTEXT
    # ========================================================================
    
    messages: Annotated[List[Dict[str, str]], add_messages] = Field(
        default_factory=list,
        description="Chat history with automatic deduplication via add_messages"
    )
    
    current_question: str = Field(
        default="",
        description="The current user question being processed"
    )
    
    # ========================================================================
    # SCHEMA & DATABASE CONTEXT
    # ========================================================================
    
    schema_text: str = Field(
        default="",
        description="Formatted database schema for LLM context"
    )
    
    active_database: str = Field(
        default="ecommerce",
        description="Which database schema we're querying (ecommerce | saas)"
    )
    
    # ========================================================================
    # SQL GENERATION PIPELINE
    # ========================================================================
    
    generated_sql: Optional[str] = Field(
        default=None,
        description="The generated SQL query"
    )
    
    sql_explanation: Optional[str] = Field(
        default=None,
        description="Why this SQL query answers the question"
    )
    
    sql_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0 to 1.0) in the generated SQL"
    )
    
    sql_assumptions: List[str] = Field(
        default_factory=list,
        description="Assumptions made during SQL generation (e.g., revenue calculation)"
    )
    
    # ========================================================================
    # SAFETY CHECKING
    # ========================================================================
    
    safety_check_passed: bool = Field(
        default=False,
        description="Whether the query passed safety validation"
    )
    
    safety_check_reason: Optional[str] = Field(
        default=None,
        description="Reason if safety check failed (violation details)"
    )
    
    # ========================================================================
    # QUERY EXECUTION
    # ========================================================================
    
    query_results: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Raw query results as list of dictionaries"
    )
    
    row_count: int = Field(
        default=0,
        description="Number of rows returned from query"
    )
    
    execution_time_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Query execution time in milliseconds"
    )
    
    execution_error: Optional[str] = Field(
        default=None,
        description="Error message if query execution failed"
    )
    
    retry_count: int = Field(
        default=0,
        ge=0,
        description="Number of times the query has been retried"
    )
    
    # ========================================================================
    # VISUALIZATION RECOMMENDATION
    # ========================================================================
    
    chart_type: Literal[
        "bar", "line", "pie", "table", "scatter", "area", "none"
    ] = Field(
        default="table",
        description="Recommended chart type for visualization"
    )
    
    chart_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Chart configuration including axis labels, colors, options"
    )
    
    # ========================================================================
    # INSIGHT GENERATION
    # ========================================================================
    
    insight_text: str = Field(
        default="",
        description="Natural language explanation of query results"
    )
    
    key_findings: List[str] = Field(
        default_factory=list,
        description="Bullet-point summary of key insights"
    )
    
    # ========================================================================
    # FLOW CONTROL & STATUS
    # ========================================================================
    
    status: Literal[
        "generating", "checking", "executing", "visualizing", 
        "narrating", "clarifying", "error", "done"
    ] = Field(
        default="generating",
        description="Current stage in the agent workflow"
    )
    
    needs_clarification: bool = Field(
        default=False,
        description="Whether user clarification is needed"
    )
    
    clarification_question: Optional[str] = Field(
        default=None,
        description="Specific question to ask if clarification is needed"
    )
    
    # ========================================================================
    # MODEL CONFIGURATION
    # ========================================================================
    
    class Config:
        """Pydantic configuration."""
        arbitrary_types_allowed = True


# ============================================================================
# STATE HELPERS & TRANSITIONS
# ============================================================================

def create_initial_state(
    question: str,
    schema_text: str = "",
    active_database: str = "ecommerce",
    messages: Optional[List[Dict[str, str]]] = None
) -> QueryMindState:
    """
    Create initial state for a new query.
    
    Args:
        question: User's natural language question
        schema_text: Formatted database schema
        active_database: Database to query (ecommerce | saas)
        messages: Optional initial message history
    
    Returns:
        Initialized QueryMindState ready for graph execution
    """
    return QueryMindState(
        messages=messages or [],
        current_question=question,
        schema_text=schema_text,
        active_database=active_database,
        status="generating"
    )


def state_transition_to_checking(state: QueryMindState) -> QueryMindState:
    """Transition state from generating to safety checking."""
    state.status = "checking"
    return state


def state_transition_to_executing(state: QueryMindState) -> QueryMindState:
    """Transition state from checking to execution."""
    state.status = "executing"
    return state


def state_transition_to_visualizing(state: QueryMindState) -> QueryMindState:
    """Transition state from executing to visualization."""
    state.status = "visualizing"
    return state


def state_transition_to_narrating(state: QueryMindState) -> QueryMindState:
    """Transition state from visualizing to insight narration."""
    state.status = "narrating"
    return state


def state_transition_to_clarifying(
    state: QueryMindState,
    clarification_question: str
) -> QueryMindState:
    """Transition state to clarification mode."""
    state.status = "clarifying"
    state.needs_clarification = True
    state.clarification_question = clarification_question
    return state


def state_transition_to_error(
    state: QueryMindState,
    error_message: str
) -> QueryMindState:
    """Transition state to error mode."""
    state.status = "error"
    state.execution_error = error_message
    return state


def state_transition_to_done(state: QueryMindState) -> QueryMindState:
    """Transition state to completion."""
    state.status = "done"
    return state


def should_retry(state: QueryMindState, max_retries: int = 2) -> bool:
    """
    Determine if query should be retried.
    
    Args:
        state: Current state
        max_retries: Maximum retry count
    
    Returns:
        True if retry count < max_retries and there's an execution error
    """
    return (
        state.execution_error is not None
        and state.retry_count < max_retries
    )


def add_message_to_state(
    state: QueryMindState,
    role: str,
    content: str
) -> QueryMindState:
    """
    Add a message to state history.
    
    Args:
        state: Current state
        role: "user" or "assistant"
        content: Message content
    
    Returns:
        Updated state with new message
    """
    new_message = {"role": role, "content": content}
    # add_messages will handle deduplication
    state.messages = [*state.messages, new_message]
    return state
