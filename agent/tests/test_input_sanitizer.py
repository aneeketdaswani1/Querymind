"""Quick tests for input sanitization behavior."""

from agent.core.input_sanitizer import sanitize_user_input


def test_sanitize_user_input_allows_simple_analytics_question() -> None:
    """Simple, legitimate analytics question should pass unchanged in meaning."""
    result = sanitize_user_input("What is total revenue by month for 2024?")

    assert result.is_safe is True
    assert result.rejection_reason is None
    assert "total revenue by month" in result.cleaned_question.lower()
