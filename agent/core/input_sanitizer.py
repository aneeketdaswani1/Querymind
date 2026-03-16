"""Input sanitizer module for QueryMind.

Sanitizes and validates user input for SQL injection prevention and ensures
input conforms to expected formats and constraints.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Optional

from pydantic import BaseModel, Field


class SanitizedInput(BaseModel):
	"""Result of user input sanitization and safety checks."""

	cleaned_question: str = Field(default="")
	is_safe: bool = Field(default=False)
	rejection_reason: Optional[str] = Field(default=None)


MAX_QUESTION_LENGTH = 500

_PROMPT_INJECTION_PATTERNS = [
	r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b",
	r"\byou\s+are\s+now\s+(a\s+)?different\s+(ai|assistant|model)\b",
	r"\bsystem\s*:\s*override\b",
	r"\bdisregard\s+(the\s+)?(rules|guardrails|instructions)\b",
	r"\bdeveloper\s+mode\b",
	r"\bjailbreak\b",
]

_SQL_COMMAND_PATTERNS = [
	r"\b(drop|truncate|alter|create|insert|update|delete|grant|revoke|commit|rollback)\b",
	r";\s*(select|insert|update|delete|drop|alter|create|with)\b",
	r"--",
	r"/\*|\*/",
]

_DATA_ANALYTICS_KEYWORDS = {
	"data",
	"analytics",
	"analysis",
	"metric",
	"metrics",
	"trend",
	"trends",
	"report",
	"dashboard",
	"revenue",
	"sales",
	"orders",
	"customers",
	"users",
	"growth",
	"conversion",
	"churn",
	"retention",
	"count",
	"average",
	"sum",
	"top",
	"compare",
	"breakdown",
	"cohort",
	"monthly",
	"weekly",
	"daily",
}

_OFF_TOPIC_PATTERNS = [
	r"\bwrite\s+(a\s+)?(poem|song|story|essay)\b",
	r"\btranslate\s+this\b",
	r"\bsolve\s+(this\s+)?(puzzle|riddle)\b",
	r"\bwho\s+won\s+(the\s+)?(game|match)\b",
	r"\bweather\b",
]


def sanitize_user_input(question: str) -> SanitizedInput:
	"""Clean and validate user input before it reaches the LLM.

	Returns SanitizedInput with:
	- cleaned_question: sanitized text
	- is_safe: whether input passed checks
	- rejection_reason: clear rejection reason when unsafe
	"""
	if not isinstance(question, str):
		return SanitizedInput(
			cleaned_question="",
			is_safe=False,
			rejection_reason="Input must be a string",
		)

	raw = question.strip()
	if not raw:
		return SanitizedInput(
			cleaned_question="",
			is_safe=False,
			rejection_reason="Question cannot be empty",
		)

	if len(raw) > MAX_QUESTION_LENGTH:
		return SanitizedInput(
			cleaned_question="",
			is_safe=False,
			rejection_reason=f"Question exceeds {MAX_QUESTION_LENGTH} character limit",
		)

	cleaned = _strip_html_and_scripts(raw)
	cleaned = _normalize_whitespace(cleaned)

	# Detect direct prompt injection attempts.
	inj_reason = _detect_prompt_injection(cleaned)
	if inj_reason:
		return SanitizedInput(cleaned_question="", is_safe=False, rejection_reason=inj_reason)

	# Detect obfuscated prompt injection attempts (base64 / hex encoded snippets).
	if _contains_obfuscated_instructions(cleaned):
		return SanitizedInput(
			cleaned_question="",
			is_safe=False,
			rejection_reason="Potentially obfuscated instruction payload detected",
		)

	# Remove SQL-like command fragments users may try to inject into prompts.
	cleaned = _strip_sql_like_commands(cleaned)
	cleaned = _normalize_whitespace(cleaned)

	if len(cleaned) < 3:
		return SanitizedInput(
			cleaned_question="",
			is_safe=False,
			rejection_reason="Question is too short after sanitization",
		)

	# Keep this strict only for clearly non-analytics prompts.
	off_topic_reason = _detect_off_topic(cleaned)
	if off_topic_reason:
		return SanitizedInput(cleaned_question="", is_safe=False, rejection_reason=off_topic_reason)

	return SanitizedInput(cleaned_question=cleaned, is_safe=True, rejection_reason=None)


def _strip_html_and_scripts(text: str) -> str:
	"""Remove HTML tags and script/style blocks."""
	text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
	text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
	text = re.sub(r"<[^>]+>", " ", text)
	return text


def _normalize_whitespace(text: str) -> str:
	"""Collapse repeated whitespace and trim."""
	return re.sub(r"\s+", " ", text).strip()


def _detect_prompt_injection(text: str) -> Optional[str]:
	"""Detect common direct prompt-injection attempts."""
	for pattern in _PROMPT_INJECTION_PATTERNS:
		if re.search(pattern, text, flags=re.IGNORECASE):
			return "Prompt injection attempt detected"
	return None


def _contains_obfuscated_instructions(text: str) -> bool:
	"""Detect encoded strings that decode to instruction override content."""
	# Base64-like tokens of meaningful length.
	for token in re.findall(r"\b[A-Za-z0-9+/]{24,}={0,2}\b", text):
		try:
			decoded = base64.b64decode(token, validate=True).decode("utf-8", errors="ignore")
			if _detect_prompt_injection(decoded):
				return True
		except (binascii.Error, ValueError):
			continue

	# Hex-encoded text chunks.
	for token in re.findall(r"\b(?:[0-9a-fA-F]{2}){12,}\b", text):
		try:
			decoded = bytes.fromhex(token).decode("utf-8", errors="ignore")
			if _detect_prompt_injection(decoded):
				return True
		except ValueError:
			continue

	return False


def _strip_sql_like_commands(text: str) -> str:
	"""Strip SQL-like command fragments without over-sanitizing legitimate questions."""
	sanitized = text
	for pattern in _SQL_COMMAND_PATTERNS:
		sanitized = re.sub(pattern, " ", sanitized, flags=re.IGNORECASE)
	return sanitized


def _detect_off_topic(text: str) -> Optional[str]:
	"""Reject only clearly non-analytics user requests."""
	lower_text = text.lower()

	# If it clearly mentions analytics/data intent, allow it.
	if any(keyword in lower_text for keyword in _DATA_ANALYTICS_KEYWORDS):
		return None

	# If it has question words commonly used in analytics queries, allow.
	if re.search(r"\b(what|which|how many|show|list|compare|find|calculate)\b", lower_text):
		return None

	for pattern in _OFF_TOPIC_PATTERNS:
		if re.search(pattern, lower_text, flags=re.IGNORECASE):
			return "Request appears off-topic for a data analytics assistant"

	# Be permissive by default when uncertain.
	return None
