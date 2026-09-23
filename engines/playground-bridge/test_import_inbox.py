# engines/playground-bridge/test_import_inbox.py
#
# WHAT: Contract tests for the media/* storage namespace and the Import
#       Inbox watch-folder (P7.8).
# WHY:  The inbox is a data-loss surface by design (it deletes after
#       import) — so deletion rules, collision safety, filter behavior,
#       and per-file failure isolation must all be pinned here.
# BREAKS IF DELETED: Dropped files could vanish without landing in the
#       library, or collide silently.

from __future__ import annotations

import pytest

from engines.playground_bridge.import_inbox import (
    ImportRecord,
    scan_inbox,
    unique_artifact_name,
)
from storage.persistence import Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(root=tmp_path)


@pytest.fixture
def inbox(tmp_path):
    d = tmp_path / "drop-here"
    d.mkdir()
    return d


class TestStorageMediaKinds:
    def test_media_subkind_roundtrip(self, storage):
        storage.save_artifact("media/library", "clip.wav", b"RIFF....")
        assert storage.load_artifact("media/library", "clip.wav") == b"RIFF...."
        assert storage.list_artifacts("media/library") == ["clip.wav"]

    @pytest.mark.parametrize("bad", [
        "media/", "media/Bad Dir", "media/..", "media/a/b",
        "media/" + "x" * 65,
    ])
    def test_invalid_subkinds_rejected(self, storage, bad):
        with pytest.raises(ValueError, match="subkind"):
            storage.save_artifact(bad, "f.bin", b"x")

    def test_plain_unknown_kinds_still_rejected(self, storage):
        with pytest.raises(ValueError, match="Unknown artifact kind"):
            storage.save_artifact("not-a-kind", "f.bin", b"x")


class TestUniqueNames:
    def test_first_fit(self):
        assert unique_artifact_name(set(), "song.wav") == "song.wav"

    def test_collision_gets_numeric_suffix(self):
        files = {"song.wav", "song-1.wav"}
        assert unique_artifact_name(files, "song.wav") == "song-2.wav"

    def test_extensionless_names(self):
        files = {"README"}
        assert unique_artifact_name(files, "README") == "README-1"


class TestScanInbox:
    def test_imports_files_and_deletes_source(self, storage, inbox):
        (inbox / "beat.wav").write_bytes(b"WAVDATA")
        records = scan_inbox(inbox, storage)
        assert len(records) == 1 and records[0].ok
        assert records[0].artifact_kind == "media/inbox"
        assert records[0].artifact_name == "beat.wav"
        assert not (inbox / "beat.wav").exists()
        assert storage.load_artifact("media/inbox", "beat.wav") == b"WAVDATA"

    def test_extension_filter_leaves_rejected_files_in_place(self, storage, inbox):
        (inbox / "keep.mp3").write_bytes(b"mp3")
        (inbox / "skip.txt").write_bytes(b"text")
        records = scan_inbox(inbox, storage,
                             allowed_extensions=[".wav", ".mp3"])
        kept = [r for r in records if not r.ok]
        imported = [r for r in records if r.ok]
        assert [r.source_name for r in imported] == ["keep.mp3"]
        assert [r.source_name for r in kept] == ["skip.txt"]
        assert (inbox / "skip.txt").exists()
        assert not (inbox / "keep.mp3").exists()

    def test_case_insensitive_extensions(self, storage, inbox):
        (inbox / "B.WAV").write_bytes(b"x")
        records = scan_inbox(inbox, storage, allowed_extensions=[".wav"])
        assert records[0].ok

    def test_collisions_renamed_not_overwritten(self, storage, inbox):
        storage.save_artifact("media/inbox", "song.wav", b"old")
        (inbox / "song.wav").write_bytes(b"new")
        records = scan_inbox(inbox, storage)
        assert records[0].artifact_name == "song-1.wav"
        assert storage.load_artifact("media/inbox", "song.wav") == b"old"
        assert storage.load_artifact("media/inbox", "song-1.wav") == b"new"

    def test_delete_after_false_keeps_sources(self, storage, inbox):
        (inbox / "a.wav").write_bytes(b"a")
        scan_inbox(inbox, storage, delete_after=False)
        assert (inbox / "a.wav").exists()

    def test_directories_ignored(self, storage, inbox):
        (inbox / "subdir").mkdir()
        records = scan_inbox(inbox, storage)
        assert records == []

    def test_absent_inbox_is_empty_scan_not_error(self, storage, tmp_path):
        assert scan_inbox(tmp_path / "nope", storage) == []

    def test_custom_media_subkind(self, storage, inbox):
        (inbox / "v.mp4").write_bytes(b"v")
        records = scan_inbox(inbox, storage, media_subkind="video")
        assert records[0].artifact_kind == "media/video"
        assert storage.list_artifacts("media/video") == ["v.mp4"]

    def test_import_record_shape(self):
        record = ImportRecord("s.wav", "media/inbox", "s.wav", 5)
        assert record.ok
        failed = ImportRecord("s.wav", "media/inbox", None, 0, error="x")
        assert not failed.ok
