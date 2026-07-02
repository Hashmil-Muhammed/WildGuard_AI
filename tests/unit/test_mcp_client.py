"""
Unit tests for app.mcp_client -- MCP Client Helper (Day 5).

Tests the synchronous query_wildlife_advice wrapper. Uses the real MCP server
subprocess for integration-style tests, and mocking for failure scenarios.
"""

from unittest.mock import patch

import pytest

from app.mcp_client import query_wildlife_advice, _FALLBACK_ADVICE


class TestQueryWildlifeAdvice:
    """Tests for the synchronous query_wildlife_advice wrapper."""

    def test_known_animal_elephant(self):
        """End-to-end: spawn MCP server, query by animal name, parse response."""
        result = query_wildlife_advice("elephant")
        assert result["animal"] == "elephant"
        assert "flash photography" in result["avoid"]
        assert isinstance(result["action"], str)
        assert isinstance(result["emergency_tips"], list)

    def test_known_animal_tiger(self):
        result = query_wildlife_advice("tiger")
        assert result["animal"] == "tiger"

    def test_unknown_animal_returns_generic(self):
        result = query_wildlife_advice("unicorn")
        assert result["animal"] == "unknown"

    def test_returns_dict(self):
        result = query_wildlife_advice("snake")
        assert isinstance(result, dict)

    def test_fallback_on_exception(self):
        """If the MCP server subprocess fails, fallback advice is returned."""
        with patch(
            "app.mcp_client._query_async",
            side_effect=RuntimeError("MCP server crashed"),
        ):
            result = query_wildlife_advice("elephant")
            assert result == _FALLBACK_ADVICE

    def test_fallback_has_required_keys(self):
        """The fallback advice has the same shape as real advice."""
        assert "animal" in _FALLBACK_ADVICE
        assert "avoid" in _FALLBACK_ADVICE
        assert "action" in _FALLBACK_ADVICE
        assert "emergency_tips" in _FALLBACK_ADVICE
