"""SQL generator module for QueryMind.

Handles the LLM-based SQL generation with structured output. Converts natural language
questions into executable SQL queries using Claude language models with schema context
and few-shot examples. Supports multi-turn conversations and self-correction on errors.
"""

from typing import Optional, List, Literal
from datetime import datetime
import re
import structlog
from pydantic import BaseModel, Field

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from agent.core.schema_loader import SchemaLoader
from agent.prompts.system import SQL_SYSTEM_PROMPT, CLARIFICATION_PROMPT
from agent.prompts.few_shot import get_relevant_examples, format_examples_for_prompt

logger = structlog.get_logger(__name__)


# ============================================================================
# PYDANTIC MODELS FOR STRUCTURED OUTPUT
# ============================================================================

class SQLResult(BaseModel):
    """Structured result from SQL generation."""
    
    status: Literal["sql_generated", "clarification_needed", "out_of_scope"]
    sql: Optional[str] = Field(
        None,
        description="The generated SQL query, or None if clarification/out-of-scope"
    )
    explanation: str = Field(
        description="Why this SQL answers the question or why clarification is needed"
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="Assumptions made during SQL generation (e.g., 'revenue = quantity * price')"
    )
    confidence: float = Field(
        default=0.9,
        description="Confidence score from 0.0 to 1.0 in the generated query"
    )
    clarification_question: Optional[str] = Field(
        None,
        description="If status == 'clarification_needed', the specific question to ask"
    )


class ConversationMessage(BaseModel):
    """A message in the conversation history."""
    
    role: Literal["user", "assistant"]
    content: str
    timestamp: Optional[datetime] = None


# ============================================================================
# SQL GENERATOR CLASS
# ============================================================================

class SQLGenerator:
    """
    Generates SQL queries from natural language questions using Claude LLM.
    
    Uses structured output (Pydantic) to ensure valid JSON responses.
    Supports multi-turn conversations and self-correction on query errors.
    """
    
    def __init__(self, llm_client: ChatAnthropic, schema_loader: SchemaLoader):
        """
        Initialize SQLGenerator.
        
        Args:
            llm_client: Initialized ChatAnthropic client for Claude
            schema_loader: SchemaLoader instance for database schema info
        """
        self.llm = llm_client
        self.schema = schema_loader
        self._retry_count = 0
        self._max_retries = 2
        
        logger.info("sql_generator_initialized")
    
    def _strip_markdown_fences(self, sql: Optional[str]) -> Optional[str]:
        """
        Remove markdown code fences from SQL output.
        
        Handles patterns like:
        - ```sql ... ```
        - ``` ... ```
        - Single backticks
        
        Args:
            sql: Potentially fenced SQL string
        
        Returns:
            Clean SQL without fences
        """
        if not sql:
            return None
        
        # Remove sql/SQL language identifier and fences
        sql = re.sub(r'```sql\n?', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'```\n?', '', sql)
        sql = re.sub(r'^`+|`+$', '', sql)  # Remove leading/trailing backticks
        
        # Strip whitespace
        sql = sql.strip()
        
        return sql if sql else None
    
    def _build_system_prompt(self, schema_json: str) -> str:
        """
        Build the system prompt with schema injection.
        
        Args:
            schema_json: Formatted schema text from SchemaLoader
        
        Returns:
            Complete system prompt with schema
        """
        return SQL_SYSTEM_PROMPT.format(schema=schema_json)
    
    def _build_user_message(
        self,
        question: str,
        conversation_history: Optional[List[ConversationMessage]] = None,
        schema_json: Optional[str] = None,
        error_context: Optional[str] = None
    ) -> str:
        """
        Build the user message with context and few-shot examples.
        
        Args:
            question: The user's natural language question
            conversation_history: Previous messages for context
            schema_json: Schema information (for refinement)
            error_context: If refining, the error message from failed query
        
        Returns:
            Complete user message for LLM
        """
        message_parts = []
        
        # Add conversation context if available
        if conversation_history and len(conversation_history) > 0:
            message_parts.append("## Previous Conversation Context:")
            for msg in conversation_history[-5:]:  # Last 5 messages for context
                role = "User" if msg.role == "user" else "Assistant"
                message_parts.append(f"{role}: {msg.content}")
            message_parts.append("")
        
        # Add error context if refining
        if error_context:
            message_parts.append("## Previous Query Error:")
            message_parts.append(error_context)
            message_parts.append("")
            message_parts.append("Please provide a corrected query that fixes this error.")
            message_parts.append("")
        
        # Add few-shot examples
        relevant_examples = get_relevant_examples(
            question,
            schema_name=None,  # Auto-detect from question context
            k=3
        )
        if relevant_examples:
            message_parts.append("## Similar Examples:")
            message_parts.append(format_examples_for_prompt(relevant_examples))
            message_parts.append("")
        
        # Add the actual question
        message_parts.append("## Your Question:")
        message_parts.append(question)
        
        return "\n".join(message_parts)
    
    async def generate(
        self,
        question: str,
        conversation_history: Optional[List[ConversationMessage]] = None,
        max_retries: int = 2
    ) -> SQLResult:
        """
        Generate SQL query from natural language question.
        
        Uses structured output (Pydantic) so the LLM always returns valid JSON.
        Includes conversation history for multi-turn context.
        Checks confidence and returns clarification if needed.
        
        Args:
            question: Natural language question
            conversation_history: Optional list of previous messages for context
            max_retries: Maximum refinement retries on error (default 2)
        
        Returns:
            SQLResult with status, sql, explanation, assumptions, confidence
        
        Raises:
            ValueError: If LLM fails to produce valid response after retries
        """
        self._retry_count = 0
        self._max_retries = max_retries
        
        logger.info(
            "sql_generation_started",
            question_snippet=question[:100],
            has_history=conversation_history is not None
        )
        
        try:
            # Get schema from loader
            schema_json = self.schema.get_schema_text()
            
            # Build system prompt with schema
            system_prompt = self._build_system_prompt(schema_json)
            
            # Build user message with few-shot examples
            user_message = self._build_user_message(
                question,
                conversation_history=conversation_history,
                schema_json=schema_json
            )
            
            # Create LLM with structured output
            llm_structured = self.llm.with_structured_output(SQLResult)
            
            # Call LLM
            logger.debug("calling_llm", system_length=len(system_prompt), user_length=len(user_message))
            
            result = await llm_structured.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ])
            
            # Clean up SQL if present
            if result.sql:
                result.sql = self._strip_markdown_fences(result.sql)
            
            # Check confidence threshold
            if result.confidence < 0.6:
                logger.info("low_confidence_detected", confidence=result.confidence)
                result.status = "clarification_needed"
                if not result.clarification_question:
                    result.clarification_question = (
                        f"Your question may be ambiguous. Could you clarify: {question[:80]}... "
                        "Are you asking for [specification 1] or [specification 2]?"
                    )
            
            logger.info(
                "sql_generation_complete",
                status=result.status,
                confidence=result.confidence,
                has_sql=result.sql is not None
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "sql_generation_failed",
                error=str(e),
                question_snippet=question[:100]
            )
            raise
    
    async def refine(
        self,
        original_sql: str,
        error_message: str,
        question: str,
        conversation_history: Optional[List[ConversationMessage]] = None
    ) -> SQLResult:
        """
        Refine SQL query after execution error through self-correction.
        
        If the generated SQL fails to execute, this method sends the error
        back to the LLM for correction. Retries up to 2 times before giving up.
        
        Args:
            original_sql: The SQL query that failed
            error_message: PostgreSQL error message
            question: Original user question
            conversation_history: Optional conversation context
        
        Returns:
            SQLResult with corrected SQL or failure status
        """
        self._retry_count += 1
        
        logger.warning(
            "sql_refinement_started",
            retry_count=self._retry_count,
            max_retries=self._max_retries,
            error_snippet=error_message[:100]
        )
        
        if self._retry_count > self._max_retries:
            logger.error("max_retries_exceeded", retry_count=self._retry_count)
            return SQLResult(
                status="out_of_scope",
                sql=None,
                explanation=f"Failed to generate valid SQL after {self._max_retries} attempts. "
                           f"Last error: {error_message}",
                confidence=0.0
            )
        
        error_context = (
            f"Previous query failed:\n```sql\n{original_sql}\n```\n\n"
            f"Error: {error_message}\n\n"
            f"Please provide a corrected query."
        )
        
        try:
            schema_json = self.schema.get_schema_text()
            system_prompt = self._build_system_prompt(schema_json)
            
            user_message = self._build_user_message(
                question,
                conversation_history=conversation_history,
                schema_json=schema_json,
                error_context=error_context
            )
            
            llm_structured = self.llm.with_structured_output(SQLResult)
            
            logger.debug("calling_llm_for_refinement", retry=self._retry_count)
            
            result = await llm_structured.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ])
            
            if result.sql:
                result.sql = self._strip_markdown_fences(result.sql)
            
            logger.info(
                "sql_refinement_complete",
                retry_count=self._retry_count,
                status=result.status,
                has_sql=result.sql is not None
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "sql_refinement_failed",
                error=str(e),
                retry_count=self._retry_count
            )
            
            # On LLM error, return error result without recursing
            return SQLResult(
                status="out_of_scope",
                sql=None,
                explanation=f"SQL refinement failed: {str(e)}",
                confidence=0.0
            )
    
    async def generate_with_retry(
        self,
        question: str,
        conversation_history: Optional[List[ConversationMessage]] = None,
        executor_func=None
    ) -> SQLResult:
        """
        Generate SQL and automatically retry on execution errors.
        
        Convenience method that generates SQL, optionally executes it,
        and refines on error up to max_retries times.
        
        Args:
            question: Natural language question
            conversation_history: Optional conversation context
            executor_func: Optional async function to execute SQL (for auto-retry)
                          Should accept sql string and return (success, error_message)
        
        Returns:
            Final SQLResult after retries
        """
        result = await self.generate(question, conversation_history)
        
        if executor_func and result.sql and result.status == "sql_generated":
            while self._retry_count < self._max_retries:
                logger.debug("executing_sql", retry=self._retry_count)
                
                try:
                    success, error_msg = await executor_func(result.sql)
                    
                    if success:
                        logger.info("sql_execution_success", retry=self._retry_count)
                        return result
                    
                    # Execute failed, refine
                    logger.warning("sql_execution_failed", error_snippet=error_msg[:100])
                    result = await self.refine(result.sql, error_msg, question, conversation_history)
                    
                except Exception as e:
                    logger.error("executor_error", error=str(e))
                    result.status = "out_of_scope"
                    result.sql = None
                    result.explanation = f"Execution error: {str(e)}"
                    break
        
        return result
