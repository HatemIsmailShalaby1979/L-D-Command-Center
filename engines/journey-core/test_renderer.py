# engines/journey-core/test_renderer.py
#
# WHAT: Tests for the journey-core HTML renderer module.
# WHY:  Ensures render_journey_html() produces valid HTML containing
#       all journey data (topic, level, cards, questions, options,
#       explanations) and that it rejects empty journeys. Tests are
#       deterministic — no model calls, no network.
# BREAKS IF DELETED: No regression protection for the HTML output
#       contract; broken rendering would go undetected.

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent

from engines.journey_core.renderer import JourneyRenderer, render_journey_html


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_JOURNEY = {
    "topic": "Python Basics",
    "level": "beginner",
    "cards": [
        {
            "id": "card-1",
            "title": "What is Python?",
            "content": "Python is a high-level programming language.",
            "question": "What type of language is Python?",
            "options": ["Low-level", "High-level", "Assembly", "Machine code"],
            "correct_option": "High-level",
            "explanation": "Python abstracts away memory management.",
        },
        {
            "id": "card-2",
            "title": "Variables",
            "content": "Variables store data values.",
            "question": "What does a variable do?",
            "options": ["Compiles code", "Stores data", "Runs loops", "Connects to DB"],
            "correct_option": "Stores data",
            "explanation": "Variables hold references to values in memory.",
        },
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestJourneyRenderer:
    """Tests for JourneyRenderer.render()."""

    def test_render_returns_valid_html(self):
        """The output must be a complete HTML document."""
        html = JourneyRenderer().render(_SAMPLE_JOURNEY)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "<head>" in html
        assert "</head>" in html
        assert "<body>" in html
        assert "</body>" in html

    def test_render_includes_topic_and_level(self):
        """The topic and level must appear in the rendered HTML."""
        html = JourneyRenderer().render(_SAMPLE_JOURNEY)
        assert "Python Basics" in html
        assert "beginner" in html

    def test_render_includes_all_cards(self):
        """Each card's title and content must appear in the HTML."""
        html = JourneyRenderer().render(_SAMPLE_JOURNEY)
        assert "What is Python?" in html
        assert "Variables" in html
        assert "high-level programming language" in html
        assert "Variables store data values." in html

    def test_render_includes_questions_and_options(self):
        """Quiz questions and all options must be present."""
        html = JourneyRenderer().render(_SAMPLE_JOURNEY)
        assert "What type of language is Python?" in html
        for opt in ["Low-level", "High-level", "Assembly", "Machine code"]:
            assert opt in html

    def test_render_includes_explanations(self):
        """Each card's explanation must appear in the HTML."""
        html = JourneyRenderer().render(_SAMPLE_JOURNEY)
        assert "Python abstracts away memory management." in html
        assert "Variables hold references to values in memory." in html

    def test_render_includes_interactive_js(self):
        """The HTML must include the interactivity script."""
        html = JourneyRenderer().render(_SAMPLE_JOURNEY)
        assert "handleAnswer" in html
        assert "showNextCard" in html
        assert "<script>" in html

    def test_render_includes_evaluation_panels(self):
        """Each card must have an evaluation div for correct/wrong feedback."""
        html = JourneyRenderer().render(_SAMPLE_JOURNEY)
        assert 'id="eval-card-1"' in html
        assert 'id="eval-card-2"' in html
        assert "Correct!" in html
        assert "Incorrect" in html

    def test_empty_cards_raises(self):
        """A journey with no cards must raise ValueError."""
        bad = dict(_SAMPLE_JOURNEY, cards=[])
        try:
            JourneyRenderer().render(bad)
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "at least one card" in str(e)

    def test_missing_cards_key_raises(self):
        """A journey without a 'cards' key must raise ValueError."""
        bad = {k: v for k, v in _SAMPLE_JOURNEY.items() if k != "cards"}
        try:
            JourneyRenderer().render(bad)
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "at least one card" in str(e)

    def test_convenience_function(self):
        """render_journey_html() is a thin wrapper around JourneyRenderer."""
        html = render_journey_html(_SAMPLE_JOURNEY)
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html
        assert "Python Basics" in html


class TestHtmlEscaping:
    """Tests that user-supplied content is safely escaped."""

    def test_html_entities_in_content_are_escaped(self):
        """Angle brackets in journey content must not break HTML structure."""
        journey = dict(_SAMPLE_JOURNEY)
        journey["cards"] = [
            {
                "id": "x",
                "title": "<script>alert('xss')</script>",
                "content": "a < b and c > d",
                "question": "What is & why?",
                "options": ["A", "B"],
                "correct_option": "A",
                "explanation": "x & y",
            }
        ]
        html = JourneyRenderer().render(journey)
        # Raw HTML tags should be escaped, not rendered
        assert "&lt;script&gt;" in html
        assert "a &lt; b and c &gt; d" in html  # angle brackets escaped
        # The script should not be executable
        assert "<script>alert" not in html

    def test_special_chars_in_options(self):
        """Options containing quotes and ampersands must be safe."""
        journey = dict(_SAMPLE_JOURNEY)
        journey["cards"] = [
            {
                "id": "y",
                "title": "Special chars",
                "content": "Test",
                "question": "Pick one",
                "options": ['A "quoted"', "B & more", "C <tag>"],
                "correct_option": "A \"quoted\"",
                "explanation": "Escaping test",
            }
        ]
        html = JourneyRenderer().render(journey)
        assert 'A &quot;quoted&quot;' in html
        assert "B &amp; more" in html
        assert "C &lt;tag&gt;" in html
