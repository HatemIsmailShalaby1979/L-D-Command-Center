# engines/language-lab/test_flagship_batch.py
#
# WHAT: Contract tests for the flagship batch generator — the tool that
#       produces the 30 marketing artifacts.
# WHY:  The batch must be idempotent (stable marketing links), isolate
#       per-topic failures, respect --limit for smoke tests, and skip
#       honestly. A tool that regenerates on every run would silently
#       invalidate every shared link (PROFIT_PLAN §3.1).
# BREAKS IF DELETED: The batch tool's contract is unprotected; a
#       regression re-generates packs and breaks shared links.

from __future__ import annotations

from pathlib import Path

import pytest

from engines.language_lab.flagship_batch import (
    batch_report, generate_flagship_batch,
)


class FakeClient:
    def __init__(self):
        self.calls = 0

    def list_models(self):
        return ["qwen-2.5-7b-instruct"]


@pytest.fixture
def pack(monkeypatch):
    """A minimal valid pack the generator can return."""
    def make(topic, target, known, level, **kw):
        return {
            "topic": topic, "target_language": target,
            "known_language": known, "level": level,
            "dialogue": [{"speaker": "A", "content": "hola"},
                         {"speaker": "B", "content": "adios"}],
            "vocab_cards": [{"term": "t", "reading": "r",
                              "translation": "x", "example": "e"}],
            "grammar_cards": [{"point": "p", "explanation": "e",
                               "drills": [{"prompt": "q", "answer": "a"},
                                          {"prompt": "q2", "answer": "a2"}]}],
            "evaluation": [{"type": "translation", "prompt": "p",
                            "answer": "a"}],
        }
    import engines.language_lab.lesson_pack as lp
    monkeypatch.setattr(lp, "generate_lesson_pack", make)
    return make


class TestFlagshipBatch:
    def test_generates_renders_and_foots_every_topic(self, tmp_path,
                                                      monkeypatch, pack):
        from storage.persistence import Storage
        storage = Storage(root=tmp_path)
        monkeypatch.setattr(
            "engines.language_lab.flagship_batch.default_storage",
            lambda: storage)
        report = generate_flagship_batch(languages=["es"],
                                         client=FakeClient(),
                                         storage=storage)
        assert len(report["generated"]) == 10
        assert not report["failed"]
        # every generated pack is footed (the marketing loop)
        for row in report["generated"]:
            document = Path(row["path"]).read_text(encoding="utf-8")
            assert "ldcc-footer" in document
            assert "L&amp;D Command Center" in document
        # lesson pack data + rendered html both stored
        assert len(storage.list_artifacts("lesson_packs")) == 10
        assert len(storage.list_artifacts("exports")) == 10

    def test_idempotent_rerun_skips_everything(self, tmp_path, monkeypatch,
                                               pack):
        from storage.persistence import Storage
        storage = Storage(root=tmp_path)
        monkeypatch.setattr(
            "engines.language_lab.flagship_batch.default_storage",
            lambda: storage)
        first = generate_flagship_batch(languages=["de"],
                                       client=FakeClient(),
                                       storage=storage)
        assert len(first["generated"]) == 10
        second = generate_flagship_batch(languages=["de"],
                                         client=FakeClient(),
                                         storage=storage)
        assert not second["generated"]
        assert len(second["skipped"]) == 10
        # and nothing was overwritten (same files, same report shape)
        assert all(r["reason"] == "already generated"
                   for r in second["skipped"])

    def test_limit_caps_the_batch_for_smoke_tests(self, tmp_path,
                                                  monkeypatch, pack):
        from storage.persistence import Storage
        storage = Storage(root=tmp_path)
        monkeypatch.setattr(
            "engines.language_lab.flagship_batch.default_storage",
            lambda: storage)
        report = generate_flagship_batch(languages=["ja"], limit=2,
                                         client=FakeClient(),
                                         storage=storage)
        assert len(report["generated"]) == 2
        assert len(report["skipped"]) == 8

    def test_one_failure_does_not_kill_the_batch(self, tmp_path,
                                                 monkeypatch):
        from storage.persistence import Storage
        storage = Storage(root=tmp_path)
        monkeypatch.setattr(
            "engines.language_lab.flagship_batch.default_storage",
            lambda: storage)
        calls = {"n": 0}

        def flaky(topic, target, known, level, **kw):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("model hiccup")
            return {"topic": topic, "target_language": target,
                    "known_language": known, "level": level,
                    "dialogue": [{"speaker": "A", "content": "1"},
                                 {"speaker": "B", "content": "2"}],
                    "vocab_cards": [{"term": "t", "reading": "r",
                                     "translation": "x",
                                     "example": "e"}],
                    "grammar_cards": [{"point": "p", "explanation": "e",
                                       "drills": [{"prompt": "q",
                                                   "answer": "a"},
                                                  {"prompt": "q2",
                                                   "answer": "a2"}]}],
                    "evaluation": [{"type": "translation",
                                    "prompt": "p", "answer": "a"}]}

        import engines.language_lab.lesson_pack as lp
        monkeypatch.setattr(lp, "generate_lesson_pack", flaky)
        report = generate_flagship_batch(languages=["es"],
                                         client=FakeClient(),
                                         storage=storage)
        assert len(report["failed"]) == 1
        assert len(report["generated"]) == 9

    def test_report_is_human_readable(self, pack, tmp_path, monkeypatch):
        from storage.persistence import Storage
        storage = Storage(root=tmp_path)
        monkeypatch.setattr(
            "engines.language_lab.flagship_batch.default_storage",
            lambda: storage)
        report = generate_flagship_batch(languages=["es"], limit=1,
                                         client=FakeClient(),
                                         storage=storage)
        text = batch_report(report)
        assert "Generated 1" in text
        assert "es/renting-apartment" in text
