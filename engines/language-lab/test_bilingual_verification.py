# engines/language-lab/test_bilingual_verification.py
#
# WHAT: Tests for the P3.2 translation-fidelity verification pass —
#       verdict validation, review rendering, and the
#       generate-verify-regenerate loop.
# WHY:  CONSTITUTION.md §3 treats translation accuracy as a correctness
#       problem; these tests pin the human-inspectable verdict contract
#       that satisfies it.
# BREAKS IF DELETED: The verification loop could silently stop checking,
#       or ship lessons whose reviewer said "unfaithful".

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import engines.language_lab.bilingual as bilingual_mod
from engines.language_lab.bilingual import (
    BilingualPair,
    BilingualSegment,
    VerificationVerdict,
    VerifiedBilingualPair,
    generate_bilingual_pair_verified,
    validate_verdict,
    verify_bilingual_pair,
)


def _pair():
    return BilingualPair(
        topic="Ordering food",
        target_language="es",
        known_language="en",
        segments=[BilingualSegment("Hola", "Hello")],
    )


def _client_returning(payload: dict):
    client = MagicMock()
    client.generate.return_value = SimpleNamespace(
        content=json.dumps(payload), model="local-model",
        finish_reason="stop", tool_calls=None, raw={},
    )
    return client


class TestValidateVerdict:
    def test_valid_payload(self):
        ok, errors = validate_verdict({"passed": True, "issues": []})
        assert ok and errors == []

    def test_missing_passed_flag(self):
        ok, errors = validate_verdict({"issues": []})
        assert not ok and any("passed" in e for e in errors)

    def test_issue_shape_enforced(self):
        ok, errors = validate_verdict({"passed": True, "issues": [{"problem": "x"}]})
        assert not ok and any("segment_index" in e for e in errors)

    def test_non_dict_rejected(self):
        assert not validate_verdict(["nope"])[0]


class TestVerifyBilingualPair:
    def test_passing_review(self):
        client = _client_returning({"passed": True, "issues": []})
        verdict = verify_bilingual_pair(_pair(), client=client)
        assert isinstance(verdict, VerificationVerdict)
        assert verdict.passed and verdict.issues == []
        # the rendered prompt carries numbered pairs + language names
        user = client.generate.call_args[0][0].messages[1]["content"]
        assert "0. [Hola] -> [Hello]" in user
        assert "Spanish" in user and "English" in user

    def test_failing_review_carries_issues(self):
        payload = {"passed": False,
                   "issues": [{"segment_index": 0, "problem": "omits greeting"}]}
        verdict = verify_bilingual_pair(_pair(), client=_client_returning(payload))
        assert not verdict.passed
        assert verdict.issues[0]["segment_index"] == 0
        assert bool(verdict) is False

    def test_malformed_review_raises(self):
        from model_layer.schema import SchemaValidationError
        with pytest.raises(SchemaValidationError):
            verify_bilingual_pair(_pair(), client=_client_returning({"nope": 1}))


class TestGenerateVerified:
    def test_passes_first_time_without_regeneration(self):
        gen = MagicMock(side_effect=[_pair()])
        ver = MagicMock(return_value=VerificationVerdict(True, []))
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bilingual_mod, "generate_bilingual_pair", gen)
            mp.setattr(bilingual_mod, "verify_bilingual_pair", ver)
            result = generate_bilingual_pair_verified("T", "es", "en")
        assert isinstance(result, VerifiedBilingualPair)
        assert result.passed
        assert len(result.verdicts) == 1
        assert gen.call_count == 1

    def test_failed_verdict_triggers_one_regeneration(self):
        good_pair = _pair()
        gen = MagicMock(side_effect=[_pair(), good_pair])
        ver = MagicMock(side_effect=[
            VerificationVerdict(False, [{"segment_index": 0, "problem": "off"}]),
            VerificationVerdict(True, []),
        ])
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bilingual_mod, "generate_bilingual_pair", gen)
            mp.setattr(bilingual_mod, "verify_bilingual_pair", ver)
            result = generate_bilingual_pair_verified("T", "es", "en")
        assert gen.call_count == 2          # regenerated exactly once
        assert len(result.verdicts) == 2    # full audit trail kept
        assert result.passed

    def test_still_failing_keeps_both_verdicts_and_last_pair(self):
        failing = VerificationVerdict(False, [])
        gen = MagicMock(side_effect=[_pair(), _pair()])
        ver = MagicMock(return_value=failing)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bilingual_mod, "generate_bilingual_pair", gen)
            mp.setattr(bilingual_mod, "verify_bilingual_pair", ver)
            result = generate_bilingual_pair_verified("T", "es", "en",
                                                      max_regenerations=1)
        assert not result.passed
        assert len(result.verdicts) == 2
