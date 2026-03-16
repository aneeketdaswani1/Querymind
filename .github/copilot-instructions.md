# QueryMind - Project Instructions for Copilot

## Project Overview
QueryMind is an AI Data Analyst Agent that converts natural language
questions into SQL queries, executes them safely, visualizes results,
and explains insights.

## Tech Stack
- Agent: Python 3.11+, LangGraph, LangChain, Pydantic v2
- API: FastAPI, SQLAlchemy, psycopg2, Redis
- Frontend: Next.js 14 (App Router), TypeScript, Tailwind CSS, Recharts
- Database: PostgreSQL 16
- LLM: Anthropic Claude (via langchain-anthropic)

## Code Conventions
- Python: Use type hints everywhere, async/await for IO operations
- Use Pydantic v2 BaseModel for all data schemas
- Use structlog for logging (not print statements)
- Frontend: Use TypeScript strict mode, functional components with hooks
- All API responses use Pydantic schemas
- Tests: pytest for Python, Vitest for TypeScript

## Architecture Rules
- The agent is built as a LangGraph StateGraph
- All SQL execution MUST go through SafetyChecker first
- Database connections use a READ-ONLY PostgreSQL user
- Never generate INSERT/UPDATE/DELETE SQL
- Use structured output (with_structured_output) for all LLM calls

## File Structure
/agent — Python LangGraph agent
/api — FastAPI backend
/web — Next.js frontend
/data — SQL seed files