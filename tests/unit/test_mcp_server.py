"""
Unit tests for app.mcp_server — Simplified Wildlife Advice (Day 5, updated Day 7).

Tests the plain get_wildlife_advice(animal) function that review_agent
calls synchronously during the high-risk workflow path.
"""

from app.mcp_server import get_wildlife_advice


class TestGetWildlifeAdvice:
    """Tests for the simplified get_wildlife_advice function."""

    def test_elephant_returns_specific_advice(self):
        result = get_wildlife_advice("elephant")
        assert "flash photography" in result.lower()
        assert "50m" in result

    def test_elephant_case_insensitive(self):
        result = get_wildlife_advice("ELEPHANT")
        assert "50m" in result

    def test_elephant_substring_match(self):
        """Animal field may contain extra text around the keyword."""
        result = get_wildlife_advice("an elephant near the river")
        assert "50m" in result

    def test_non_elephant_returns_generic(self):
        result = get_wildlife_advice("tiger")
        assert "safe distance" in result.lower()

    def test_unknown_animal_returns_generic(self):
        result = get_wildlife_advice("unicorn")
        assert "safe distance" in result.lower()

    def test_empty_string_returns_generic(self):
        result = get_wildlife_advice("")
        assert "safe distance" in result.lower()

    def test_return_type_is_str(self):
        assert isinstance(get_wildlife_advice("monkey"), str)
