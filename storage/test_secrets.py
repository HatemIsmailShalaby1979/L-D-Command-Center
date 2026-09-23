# storage/test_secrets.py
#
# WHAT: Contract tests for the one secrets-file adapter.
# WHY:  P5.1 consolidation — parsing rules (comments, first-'=' split,
#       scan order, explicit-path precedence) are pinned here so the
#       integrations can trust load_secret blindly.
# BREAKS IF DELETED: Credential resolution behavior is unprotected;
#       integrations would drift again.

from __future__ import annotations

from pathlib import Path

import pytest

from storage.secrets import load_secret, parse_secrets_file


@pytest.fixture
def secrets_dir(tmp_path):
    def _write(fname: str, content: str) -> Path:
        f = tmp_path / fname
        f.write_text(content, encoding="utf-8")
        return f
    return tmp_path, _write


class TestParseSecretsFile:
    def test_basic_pairs(self, secrets_dir):
        _, write = secrets_dir
        f = write("a.secrets", "TOKEN=abc123\nOTHER=x y z\n")
        assert parse_secrets_file(f) == {"TOKEN": "abc123", "OTHER": "x y z"}

    def test_comments_and_blank_lines_skipped(self, secrets_dir):
        _, write = secrets_dir
        f = write("c.secrets", "# header comment\n\nKEY=val\n  # indented comment\n")
        assert parse_secrets_file(f) == {"KEY": "val"}

    def test_value_may_contain_equals(self, secrets_dir):
        _, write = secrets_dir
        f = write("e.secrets", "CONN=a=b=c\n")
        assert parse_secrets_file(f) == {"CONN": "a=b=c"}

    def test_missing_file_returns_empty(self, tmp_path):
        assert parse_secrets_file(tmp_path / "nope.secrets") == {}


class TestLoadSecret:
    def test_explicit_path_wins(self, secrets_dir):
        _, write = secrets_dir
        write("z_first.secrets", "TOK=wrong\n")
        explicit = write("explicit.secrets", "TOK=right\n")
        assert load_secret("TOK", secrets_path=explicit) == "right"

    def test_scan_order_is_filename_sorted(self, secrets_dir):
        d, write = secrets_dir
        write("b_beta.secrets", "TOK=beta\n")
        write("a_alpha.secrets", "TOK=alpha\n")
        assert load_secret("TOK", secrets_dir=d) == "alpha"

    def test_missing_name_returns_none(self, secrets_dir):
        d, write = secrets_dir
        write("a.secrets", "OTHER=1\n")
        assert load_secret("MISSING", secrets_dir=d) is None

    def test_missing_dir_returns_none(self, tmp_path):
        assert load_secret("ANY", secrets_dir=tmp_path / void()) is None

    def test_empty_value_treated_as_missing(self, secrets_dir):
        d, write = secrets_dir
        write("a.secrets", "EMPTY=\n")
        assert load_secret("EMPTY", secrets_dir=d) is None

    def test_blank_name_returns_none(self):
        assert load_secret("") is None


def void() -> str:
    return "definitely-not-here"
