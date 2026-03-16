"""Main LangGraph graph definition for QueryMind.

Assembles the StateGraph with nodes and edges to create the complete agent workflow
for converting natural language questions into insights.
"""

from langgraph.graph import StateGraph, END

from agent.graph.state import QueryMindState
from agent.graph.nodes import (
	load_schema,
	generate_sql,
	check_safety,
	execute_query,
	handle_error,
	recommend_viz,
	generate_insight,
	ask_clarification,
)


def build_agent_graph():
	"""Build and compile the QueryMind LangGraph workflow."""
	graph = StateGraph(QueryMindState)

	# Add nodes
	graph.add_node("load_schema", load_schema)
	graph.add_node("generate_sql", generate_sql)
	graph.add_node("check_safety", check_safety)
	graph.add_node("execute_query", execute_query)
	graph.add_node("handle_error", handle_error)
	graph.add_node("recommend_viz", recommend_viz)
	graph.add_node("generate_insight", generate_insight)
	graph.add_node("ask_clarification", ask_clarification)

	# Set entry point
	graph.set_entry_point("load_schema")

	# Edges
	graph.add_edge("load_schema", "generate_sql")

	# After SQL generation: either clarify or check safety
	graph.add_conditional_edges(
		"generate_sql",
		lambda s: "ask_clarification" if s.needs_clarification else "check_safety",
	)

	# After safety check: pass or block
	graph.add_conditional_edges(
		"check_safety",
		lambda s: "execute_query" if s.safety_check_passed else END,
	)

	# After execution: success or error
	graph.add_conditional_edges(
		"execute_query",
		lambda s: "handle_error" if s.execution_error else "recommend_viz",
	)

	# Error handling: retry or give up
	graph.add_conditional_edges(
		"handle_error",
		lambda s: "generate_sql" if s.retry_count < 2 else END,
	)

	# Happy path continues
	graph.add_edge("recommend_viz", "generate_insight")
	graph.add_edge("generate_insight", END)
	graph.add_edge("ask_clarification", END)  # Returns to user for input

	return graph.compile()


# Usage:
# agent = build_agent_graph()
# result = await agent.ainvoke({"current_question": "What are our top products?"})
