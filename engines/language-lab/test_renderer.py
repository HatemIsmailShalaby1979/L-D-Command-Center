# engines/language-lab/test_renderer.py
#
# WHAT: Contract tests for the LanguageLabRenderer (P7.4).
# WHY:  The rendered pack is the learner-facing flagship surface: model
#       content must arrive escaped, grading in the browser must mirror
#       the deterministic graders, audio wiring must follow artifact
#       names exactly (P7.5 contract), and output must stay
#       deterministic. All proven headless.
# BREAKS IF DELETED: Injection via generated content, JS/Python grading
#       drift, or nondeterministic exports would go unnoticed.

from __future__ import annotations

import pytest

from engines.language_lab.renderer import render_lesson_pack_html


def good_pack():
    return {
        "topic": "Ordering coffee",
        "target_language": "es",
        "known_language": "en",
        "level": "beginner",
        "dialogue": [
            {"speaker": "Ana", "content": "Un cafe con leche, por favor."},
            {"speaker": "Luis", "content": "Algo mas?"},
            {"speaker": "Ana", "content": "Y un croissant."},
            {"speaker": "Luis", "content": "Son cuatro euros."},
        ],
        "vocab_cards": [
            {"term": "el cafe", "reading": "el ka-FE", "translation": "coffee",
             "example": "Un cafe, por favor."},
        ],
        "grammar_cards": [
            {"point": "tener", "explanation": "tener = to have (states).",
             "drills": [
                 {"prompt": "Yo ___ sed.", "answer": "tengo"},
                 {"prompt": "Articulo: ___ agua", "answer": "el / la"},
             ]},
        ],
        "evaluation": [
            {"type": "multiple_choice", "question": "'la cuenta' means?",
             "options": ["the bill", "the coffee"], "correct_index": 0},
            {"type": "fill_in_blank", "sentence_with_blank": "Cafe ___ leche.",
             "answer": "con"},
            {"type": "translation", "prompt": "See you later!",
             "answer": "Hasta luego"},
        ],
    }


@pytest.fixture
def html():
    return render_lesson_pack_html(good_pack())


class TestStructure:
    def test_renders_all_sections(self, html):
        for fragment in ("Ordering coffee", ">beginner<", "es &rarr; en",
                         "<h2>Dialogue</h2>", "<h2>Vocabulary</h2>",
                         ">tener<", "<h2>Evaluation</h2>",
                         "Show my score", "final-screen"):
            assert fragment in html, fragment

    def test_pack_content_present(self, html):
        for fragment in ("el cafe", "coffee", "el ka-FE",
                         "Un cafe con leche, por favor.", "Ana:", "Luis:",
                         "the bill", "Cafe ", "See you later!"):
            assert fragment in html, fragment

    def test_deterministic_output(self):
        first = render_lesson_pack_html(good_pack())
        second = render_lesson_pack_html(good_pack())
        assert first == second

    def test_incomplete_pack_rejected(self):
        pack = good_pack()
        del pack["vocab_cards"]
        with pytest.raises(ValueError, match="vocab_cards"):
            render_lesson_pack_html(pack)

    def test_empty_topic_rejected(self):
        pack = good_pack()
        pack["topic"] = "  "
        with pytest.raises(ValueError, match="topic"):
            render_lesson_pack_html(pack)


class TestEscaping:
    def test_model_content_cannot_inject_markup(self):
        pack = good_pack()
        pack["topic"] = '<script>alert("x")</script>'
        pack["vocab_cards"][0]["term"] = '<img src=x onerror=alert(1)>'
        pack["grammar_cards"][0]["drills"][0]["answer"] = '" onclick="evil()'
        html = render_lesson_pack_html(pack)
        assert '<script>alert' not in html
        assert '<img src=x' not in html
        assert "&lt;script&gt;" in html
        assert "&lt;img" in html

    def test_answer_attributes_are_quote_safe(self):
        pack = good_pack()
        pack["evaluation"][1]["answer"] = 'con" onmouseover="bad'
        html = render_lesson_pack_html(pack)
        assert 'onmouseover="bad"' not in html.split("data-answer")[1][:80]


class TestGradingWiringMirrorsGraders:
    def test_mc_embeds_correct_index(self, html):
        assert 'data-correct="0"' in html

    def test_drill_alternatives_pass_through_verbatim(self, html):
        # graders.accepted_answers splits on "/" — the embedded key must
        # carry it so browser-side grading agrees.
        assert 'data-answer="el / la"' in html

    def test_grading_js_matches_python_normalization_rules(self, html):
        # Both sides strip edge punctuation including opening marks,
        # casefold/lowercase, collapse spaces, then accent-fold.
        js = html.split("<script>")[1].split("</script>")[0]
        assert "\\u00bf\\u00a1" in js          # ¿¡ in the edge set
        assert "toLowerCase()" in js           # casefold counterpart
        assert "normalize('NFD')" in js        # accent folding
        assert "split('/')" in js              # slash alternatives

    def test_translation_items_expose_self_grade_not_fake_judgement(self, html):
        assert "I was right" in html and "I was wrong" in html
        assert "can't be auto-judged offline" in html


class TestAudioWiring:
    AUDIO = {
        "dialogue-0": "lesson-d0.wav",
        "dialogue-1": "lesson-d1.wav",
        "listening-3": "lesson-l3.wav",
    }

    def test_listening_block_absent_without_audio(self, html):
        assert "<h2>Listening</h2>" not in html
        assert "<audio" not in html

    def test_dialogue_turns_reference_their_artifacts(self):
        html = render_lesson_pack_html(good_pack(), audio_files=self.AUDIO)
        assert 'type="audio/wav"' in html
        assert "Play full dialogue" in html
        assert 'src="lesson-d0.wav"' in html
        assert 'src="lesson-d1.wav"' in html
        assert 'src="lesson-d2.wav"' not in html  # no mapping -> no tag

    def test_no_play_all_button_without_audio(self, html):
        assert "Play full dialogue" not in html

    def test_listening_rows_use_listening_key_then_dialogue_fallback(self):
        html = render_lesson_pack_html(good_pack(), audio_files=self.AUDIO)
        assert "<h2>Listening</h2>" in html
        assert 'src="lesson-l3.wav"' in html

    def test_listening_falls_back_to_dialogue_audio_when_only_that_exists(self):
        html = render_lesson_pack_html(
            good_pack(), audio_files={"dialogue-2": "seg2.mp3"})
        rows = html.split("<h2>Listening</h2>")[1]
        assert 'src="seg2.mp3"' in rows

    def test_no_listening_rows_when_keys_do_not_cover_any_turn(self):
        html = render_lesson_pack_html(
            good_pack(), audio_files={"dialogue-9": "missing.wav"})
        assert "<h2>Listening</h2>" not in html
