# model-layer/test_extraction.py
#
# WHAT: Contract tests for the hardened JSON extractor — noise stripping,
#       fence removal, reasoning blocks, Python literals, string-aware
#       span scanning, and truncation repair.
# WHY:  Live 12B/14B models (qwen, deepseek-r1, gemma) wrap JSON in
#       fences and MMdd blocks, emit Python booleans, and run into the
#       token limit mid-object. The old extractor failed all four shapes
#       and surfaced as "model kept producing invalid content".
# BREAKS IF DELETED: The Guardrail Loop's tolerance for real model output
#       regresses silently; the 12B/14B format errors return.

from __future__ import annotations

from model_layer.schema import (
    extract_json_from_text,
    repair_truncated_json,
)

PACK = {
    "topic": "clocks",
    "level": "beginner",
    "cards": [{"id": "c1", "title": "T", "content": "C",
               "question": "Q", "options": ["a", "b"],
               "correct_option": "a", "explanation": "E"}],
}


class TestStripNoise:
    def test_plain_json_still_parses(self):
        import json
        assert extract_json_from_text(json.dumps(PACK)) == PACK

    def test_json_wrapped_in_prose(self):
        text = f'Sure! Here is your journey:\n{PACK!r}\nHope that helps.'
        # repr() uses single quotes — craft with json instead
        import json
        text = f"Sure! Here it is:\n{json.dumps(PACK)}\nEnjoy!"
        assert extract_json_from_text(text) == PACK

    def test_markdown_fences_stripped(self):
        import json
        fenced = f"```json\n{json.dumps(PACK)}\n```"
        assert extract_json_from_text(fenced) == PACK

    def test_fence_without_language_tag(self):
        import json
        fenced = f"```\n{json.dumps(PACK)}\n```"
        assert extract_json_from_text(fenced) == PACK

    def test_think_block_removed(self):
        import json
        text = ("<think>doing chain-of-thought reasoning</think>"
                + json.dumps(PACK))
        assert extract_json_from_text(text) == PACK

    def test_thinking_tag_variant_removed(self):
        import json
        text = ("<thinking>internal chain</thinking>"
                + json.dumps(PACK))
        assert extract_json_from_text(text) == PACK

    def test_unclosed_think_block_removed(self):
        import json
        text = "<think>truncated reasoning, output cut off before " \
               "closing the tag" + json.dumps(PACK)
        assert extract_json_from_text(text) == PACK

    def test_bom_and_zero_width_stripped(self):
        assert extract_json_from_text("﻿" + '{"a": 1}') == {"a": 1}

    def test_smart_quotes_wrapping_json(self):
        assert extract_json_from_text('“{"a": 1}”') == {"a": 1}


class TestPythonLiterals:
    def test_true_false_none_fixed(self):
        text = '{"ok": True, "off": False, "gap": None}'
        assert extract_json_from_text(text) == {
            "ok": True, "off": False, "gap": None}

    def test_literals_inside_strings_untouched(self):
        text = '{"note": "None of this True/False is code"}'
        assert extract_json_from_text(text) == {
            "note": "None of this True/False is code"}

    def test_word_boundaries_respected(self):
        # 'Truest' is a word, not a literal
        text = '{"word": "Truest"}'
        assert extract_json_from_text(text) == {"word": "Truest"}


class TestStringAwareScanning:
    def test_braces_inside_strings_do_not_break_extraction(self):
        # the old depth counter stopped at the } inside the string
        text = '{"topic": "use {braces} here", "level": "beginner"}'
        assert extract_json_from_text(text) == {
            "topic": "use {braces} here", "level": "beginner"}

    def test_unbalanced_junk_after_json_ignored(self):
        import json
        text = json.dumps(PACK) + " trailing {broken"
        assert extract_json_from_text(text) == PACK

    def test_first_balanced_span_wins(self):
        import json
        text = json.dumps(PACK) + "\nand also " + json.dumps(
            {"topic": "other"})
        assert extract_json_from_text(text)["topic"] == "clocks"


class TestTruncationRepair:
    def test_cut_mid_string_value(self):
        truncated = '{"topic": "clocks", "content": "The long answer got '
        result = repair_truncated_json(truncated)
        assert result == {"topic": "clocks"}

    def test_cut_after_open_object(self):
        truncated = '{"topic": "clocks", "cards": [{"id": "c1"'
        result = repair_truncated_json(truncated)
        # every COMPLETE member is salvaged, including the partial
        # trailing {"id": "c1"} element — keep what exists, never invent
        assert result == {"topic": "clocks", "cards": [{"id": "c1"}]}

    def test_cut_mid_array_element(self):
        truncated = ('{"cards": [{"id": "c1", "title": "T"}, '
                     '{"id": "c2", "ti')
        result = repair_truncated_json(truncated)
        assert result == {"cards": [{"id": "c1", "title": "T"},
                                     {"id": "c2"}]}

    def test_cut_with_fences_and_think(self):
        truncated = ("<think>planning</think>```json\n"
                     '{"topic": "clocks", "question": "What ')
        result = repair_truncated_json(truncated)
        assert result == {"topic": "clocks"}

    def test_completes_valid_json_returns_none_or_full(self):
        # a balanced object is not a truncation candidate
        assert repair_truncated_json('{"a": 1}') is None

    def test_braces_inside_strings_do_not_confuse_repair(self):
        truncated = '{"topic": "use {braces}", "next": "still going'
        result = repair_truncated_json(truncated)
        assert result == {"topic": "use {braces}"}

    def test_no_json_at_all(self):
        assert repair_truncated_json("no json here") is None
        assert repair_truncated_json("") is None
