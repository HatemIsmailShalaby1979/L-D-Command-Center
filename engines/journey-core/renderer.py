# engines/journey-core/renderer.py
#
# WHAT: HTML rendering module for journey-core — converts a validated
#       Journey dict into an interactive HTML learning experience.
# WHY:  Separating rendering from generation keeps the two concerns
#       independent. The generator produces data; the renderer produces
#       the presentation. This lets each be tested, swapped, and reused
#       without coupling to LM Studio or to each other.
# BREAKS IF DELETED: The journey-core engine loses its ability to
#       produce interactive HTML learning experiences; the export and
#       other engines lose the primary output format.

from __future__ import annotations

import html
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTML template strings
# ---------------------------------------------------------------------------

_HTML_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<style>
  :root {{
    --bg: #f8f9fa;
    --card-bg: #ffffff;
    --text: #1a1a2e;
    --muted: #6c757d;
    --accent: #4361ee;
    --accent-light: #eef2ff;
    --success: #2ec4b6;
    --error: #e63946;
    --border: #dee2e6;
    --radius: 8px;
    --shadow: 0 2px 8px rgba(0,0,0,.08);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 2rem;
  }}
  h1 {{ font-size: 1.75rem; margin-bottom: .25rem; }}
  .level-badge {{
    display: inline-block;
    background: var(--accent-light);
    color: var(--accent);
    font-size: .8rem;
    font-weight: 600;
    padding: .2em .6em;
    border-radius: 4px;
    text-transform: capitalize;
    margin-bottom: 1.5rem;
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    max-width: 720px;
  }}
  .card h2 {{ font-size: 1.2rem; margin-bottom: .75rem; }}
  .card .content {{ margin-bottom: 1rem; color: var(--text); }}
  .quiz-label {{
    font-weight: 600;
    margin-bottom: .5rem;
    display: block;
  }}
  .options {{ list-style: none; display: flex; flex-direction: column; gap: .5rem; }}
  .options li button {{
    width: 100%;
    text-align: left;
    padding: .75rem 1rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--card-bg);
    cursor: pointer;
    font-size: .95rem;
    transition: background .15s, border-color .15s;
  }}
  .options li button:hover:not(:disabled) {{
    background: var(--accent-light);
    border-color: var(--accent);
  }}
  .options li button:disabled {{ cursor: default; }}
  .options li button.selected-correct {{
    background: #d1fae5;
    border-color: var(--success);
    color: #065f46;
  }}
  .options li button.selected-wrong {{
    background: #fee2e2;
    border-color: var(--error);
    color: #7f1d1d;
  }}
  .evaluation {{
    margin-top: 1rem;
    padding: 1rem;
    border-radius: var(--radius);
    display: none;
  }}
  .evaluation.show {{ display: block; }}
  .evaluation.correct {{ background: #d1fae5; border-left: 4px solid var(--success); }}
  .evaluation.wrong {{ background: #fee2e2; border-left: 4px solid var(--error); }}
  .evaluation .verdict {{
    font-weight: 700;
    font-size: 1rem;
    margin-bottom: .25rem;
  }}
  .evaluation .explanation {{ font-size: .9rem; color: var(--text); }}
  .progress {{
    max-width: 720px;
    margin-bottom: 1.5rem;
    font-size: .9rem;
    color: var(--muted);
  }}
</style>
</head>
<body>
"""

_HTML_BODY_HEADER = """\
<h1>{title}</h1>
<span class="level-badge">{level}</span>
<div class="progress">Card {current} of {total}</div>
"""

_CARD_TEMPLATE = """\
<div>
  <h2>{card_title}</h2>
  <div class="content">{content}</div>
  <span class="quiz-label">Quiz:</span>
  <p><strong>{question}</strong></p>
  <ul class="options" id="options-{card_id}">
{options_html}
  </ul>
  <div class="evaluation" id="eval-{card_id}">
    <div class="verdict" id="verdict-{card_id}"></div>
    <div class="explanation">{explanation}</div>
  </div>
</div>
"""

_OPTION_BUTTON = (
    '    <li>'
    '<button data-card="{card_id}" '
    'data-option="{option_index}" '
    'data-correct="{correct_idx}" '
    'onclick="handleAnswer(this)">'
    '{option_text}</button>'
    '</li>\n'
)

_NEXT_CARD_TRIGGER = """\
<div style="display:none" id="next-{card_id}">
  <button onclick="showNextCard('{card_id}')"
    style="padding:.5rem 1rem;border:1px solid var(--border);
           border-radius:var(--radius);background:var(--accent-light);
           color:var(--accent);cursor:pointer;font-size:.9rem">
    Next Card &rarr;
  </button>
</div>
"""

_JS = """\
<script>
function handleAnswer(btn) {
  var cardId = btn.dataset.card;
  var selectedIdx = parseInt(btn.dataset.option, 10);
  var correctIdx = parseInt(btn.dataset.correct, 10);
  var options = document.querySelectorAll('#options-' + cardId + ' button');
  var evalDiv = document.getElementById('eval-' + cardId);
  var verdict = document.getElementById('verdict-' + cardId);

  options.forEach(function(b) { b.disabled = true; });

  if (selectedIdx === correctIdx) {
    btn.classList.add('selected-correct');
    evalDiv.className = 'evaluation show correct';
    verdict.textContent = 'Correct!';
    verdict.style.color = '#065f46';
  } else {
    btn.classList.add('selected-wrong');
    options[correctIdx].classList.add('selected-correct');
    evalDiv.className = 'evaluation show wrong';
    verdict.textContent = 'Incorrect';
    verdict.style.color = '#7f1d1d';
  }

  var nextBtn = document.getElementById('next-' + cardId);
  if (nextBtn) nextBtn.style.display = 'block';
}

function showNextCard(cardId) {
  var next = document.getElementById('next-' + cardId);
  if (next) next.remove();
  var card = document.getElementById('card-' + cardId);
  if (card) {
    card.style.display = 'none';
    var nextCard = card.nextElementSibling;
    while (nextCard) {
      if (nextCard.classList &&
          nextCard.classList.contains('card') &&
          nextCard.id !== 'end-card') {
        nextCard.style.display = 'block';
        break;
      }
      nextCard = nextCard.nextElementSibling;
    }
  }
}
</script>
"""

_HTML_FOOTER = """\
<div class="card" id="end-card" style="margin-top:2rem;text-align:center;">
  <h2>Journey Complete!</h2>
  <p>You've finished all cards. Great work.</p>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Renderer class
# ---------------------------------------------------------------------------

class JourneyRenderer:
    """
    Contract: converts a validated Journey dict into an interactive
    HTML learning experience. Does NOT call any model — it only renders
    data given to it.

    Structure of the returned HTML:
      - <head> with embedded CSS and a <script> for interactivity
      - A title, level badge, and progress indicator
      - One card per journey card, each with:
          - learning content
          - a quiz question with multiple-choice options
          - an evaluation panel that appears after answering
      - A completion message at the end

    Each card is hidden after the user answers and clicks "Next Card".
    The first card is visible on load; subsequent cards appear on demand.
    """

    def __init__(self) -> None:
        pass

    def render(self, journey: dict[str, Any]) -> str:
        """
        Contract: render a Journey dict to a complete HTML string.

        Args:
            journey: a dict with keys 'topic', 'level', 'cards'.
                     'cards' is a list of dicts with keys 'id',
                     'title', 'content', 'question', 'options',
                     'correct_option', 'explanation'.

        Returns:
            A complete HTML string ready to be saved to disk or served.

        Raises:
            ValueError: if the journey dict is missing required fields.
        """
        topic = journey.get("topic", "Untitled Journey")
        level = journey.get("level", "beginner")
        cards = journey.get("cards", [])

        if not cards:
            raise ValueError("Journey must contain at least one card")

        title = f"{topic} — {level} Learning Journey"
        body_parts = [
            _HTML_BODY_HEADER.format(
                title=html.escape(topic),
                level=level,
                current=1,
                total=len(cards),
            )
        ]

        for idx, card in enumerate(cards):
            card_html = self._render_card(card, idx + 1, len(cards))
            body_parts.append(card_html)

            # Add "next card" trigger after each card except the last
            if idx < len(cards) - 1:
                body_parts.append(
                    _NEXT_CARD_TRIGGER.format(card_id=card["id"])
                )

        # Hide all cards after the first
        js_card_hiders = "\n".join(
            f"document.getElementById('card-{c['id']}').style.display='none';"
            for c in cards[1:]
        )

        full_html = (
            _HTML_HEAD.format(title=html.escape(title))
            + "\n"
            + "\n".join(body_parts)
            + "\n"
            + _JS
            + f"\n<script>\n{js_card_hiders}\n</script>\n"
            + _HTML_FOOTER
        )

        logger.info("Rendered HTML for journey: %s (%d cards)", topic, len(cards))
        return full_html

    def _render_card(self, card: dict[str, Any], current: int, total: int) -> str:
        """
        Render a single card with its quiz options and evaluation panel.
        """
        card_id = html.escape(str(card.get("id", f"card-{current}")))
        card_title = html.escape(str(card.get("title", "")))
        content = html.escape(str(card.get("content", "")))
        question = html.escape(str(card.get("question", "")))
        explanation = html.escape(str(card.get("explanation", "")))

        options = card.get("options", [])
        correct_option = card.get("correct_option", "")

        # Find the index of the correct option (case-insensitive)
        correct_idx = 0
        for i, opt in enumerate(options):
            if str(opt).strip().lower() == str(correct_option).strip().lower():
                correct_idx = i
                break

        options_html = ""
        for i, opt in enumerate(options):
            opt_text = html.escape(str(opt))
            options_html += _OPTION_BUTTON.format(
                card_id=card_id,
                option_index=i,
                correct_idx=correct_idx,
                option_text=opt_text,
            )

        card_html = _CARD_TEMPLATE.format(
            card_id=card_id,
            card_title=card_title,
            content=content,
            question=question,
            options_html=options_html.rstrip(),
            explanation=explanation,
        )

        return f'<div id="card-{card_id}" class="card">{card_html}</div>'


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def render_journey_html(journey: dict[str, Any]) -> str:
    """
    Contract: thin wrapper around JourneyRenderer.render() for callers
    that don't need to keep a renderer instance.

    Args:
        journey: a validated Journey dict.

    Returns:
        Complete HTML string.
    """
    return JourneyRenderer().render(journey)
