# storage/test_persistence.py
#
# WHAT: Contract tests for file-backed artifact persistence and
#       preferences.
# WHY:  P5.1 — the desktop shell's revisit/extend flows depend on
#       roundtrips, listing, deletion, kind isolation, and preference
#       defaults behaving exactly as specified.
# BREAKS IF DELETED: Data-loss or typo-kind bugs in storage go unnoticed.

from __future__ import annotations

import pytest

from storage.persistence import ALLOWED_KINDS, Storage


@pytest.fixture
def store(tmp_path):
    return Storage(root=tmp_path)


class TestArtifacts:
    def test_dict_roundtrip(self, store):
        store.save_artifact("journeys", "python.json", {"topic": "Python"})
        assert store.load_artifact("journeys", "python.json") == {"topic": "Python"}

    def test_bytes_roundtrip_is_raw(self, store):
        payload = b"%PDF-fake\x89\x50"
        store.save_artifact("exports", "out.pdf", payload)
        loaded = store.load_artifact("exports", "out.pdf")
        assert isinstance(loaded, bytes) and loaded == payload

    def test_untagged_legacy_file_loads_as_bytes(self, store):
        # Files written before the tagged container must still load.
        f = store._kind_dir("exports") / "legacy.pdf"
        f.write_bytes(b"%PDF-raw-legacy")
        loaded = store.load_artifact("exports", "legacy.pdf")
        assert loaded == b"%PDF-raw-legacy"

    def test_str_roundtrip(self, store):
        store.save_artifact("narrations", "note.txt", "hello")
        assert store.load_artifact("narrations", "note.txt") == "hello"

    def test_overwrite_replaces(self, store):
        store.save_artifact("resumes", "r.json", {"v": 1})
        store.save_artifact("resumes", "r.json", {"v": 2})
        assert store.load_artifact("resumes", "r.json") == {"v": 2}

    def test_list_sorted_and_delete(self, store):
        for n in ("b.json", "a.json"):
            store.save_artifact("podcast_scripts", n, {"n": n})
        store.delete_artifact("podcast_scripts", "b.json")
        assert store.list_artifacts("podcast_scripts") == ["a.json"]

    def test_delete_missing_is_noop(self, store):
        store.delete_artifact("journeys", "ghost.json")  # must not raise

    def test_load_missing_raises_filenotfound(self, store):
        with pytest.raises(FileNotFoundError):
            store.load_artifact("journeys", "ghost.json")

    def test_kinds_are_isolated(self, store):
        store.save_artifact("journeys", "same.json", {"k": "j"})
        store.save_artifact("resumes", "same.json", {"k": "r"})
        assert store.load_artifact("journeys", "same.json")["k"] == "j"
        assert store.load_artifact("resumes", "same.json")["k"] == "r"

    def test_unknown_kind_rejected(self, store):
        with pytest.raises(ValueError, match="Unknown artifact kind"):
            store.save_artifact("journies", "typo.json", {})  # deliberate

    def test_invalid_names_rejected(self, store):
        for bad in ("", "..", "a/b", "a\\b", "."):
            with pytest.raises(ValueError, match="Invalid artifact name"):
                store.save_artifact("journeys", bad, {})


class TestPreferences:
    def test_default_when_unset(self, store):
        assert store.get_preference("theme", default="dark") == "dark"

    def test_set_then_get(self, store):
        store.set_preference("theme", "light")
        assert store.get_preference("theme") == "light"

    def test_persists_across_instances(self, tmp_path):
        s1 = Storage(root=tmp_path)
        s1.set_preference("last_topic", "Pandas")
        s2 = Storage(root=tmp_path)
        assert s2.get_preference("last_topic") == "Pandas"

    def test_allowed_kinds_covers_preferences(self):
        assert "preferences" in ALLOWED_KINDS

    def test_capability_verdict_roundtrip(self, store):
        doc = {"model_id": "gemma-4-12B-it-QAT-GGUF", "overall": "ready"}
        store.save_artifact("capabilities", "gemma.json", doc)
        assert "capabilities" in ALLOWED_KINDS
        assert store.load_artifact("capabilities", "gemma.json") == doc
