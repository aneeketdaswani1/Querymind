"""Safety checker module for QueryMind.

Validates generated SQL queries to ensure safety, preventing dangerous operations like
INSERT, UPDATE, DELETE commands and enforcing read-only access patterns.
"""
