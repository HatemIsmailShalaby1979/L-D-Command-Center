# engines/playground-bridge/test_connectors_figma.py
#
# WHAT: Contract tests for the Figma REST adapter (P7.10).
# WHY:  Token handling, export flow (two-leg: URL then bytes), and
#       failure-as-data rules must be pinned before a real token ever
#       exists; the transport fake proves the exact calls made.
# BREAKS IF DELETED: Token leaks into logs/errors or silent job crashes
#       would go unnoticed.

from __future__ import annotations

import pytest

from engines.playground_bridge.connectors_figma import (
    FIGMA_TOKEN_NAME,
    FakeResponse,
    FigmaConnector,
)


class RecordingTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers=None, params=None):
        self.calls.append({"method": method, "url": url,
                           "headers": dict(headers or {}),
                           "params": params})
        return self.responses.pop(0)


def make_connector(transport, token="tok"):
    return FigmaConnector(
        token_provider=lambda: token,
        transport=transport)


IMAGES_OK = {"images": {"1:2": "https://s3.example/frame.png"}}


class TestSend:
    def test_two_leg_export_returns_png_bytes(self):
        transport = RecordingTransport([
            FakeResponse(payload=IMAGES_OK),
            FakeResponse(content=b"PNGDATA"),
        ])
        connector = make_connector(transport)
        job = connector.send(None, {"file_key": "FK", "node_id": "1:2"})
        assert job.status == "done"
        result = connector.poll(job)
        assert result.ok and result.media_bytes == b"PNGDATA"

    def test_request_shape_token_header_and_params(self):
        transport = RecordingTransport([
            FakeResponse(payload=IMAGES_OK), FakeResponse(content=b"z"),
        ])
        connector = make_connector(transport)
        connector.send(None, {"file_key": "FK", "node_id": "1:2",
                        "format": "png", "scale": 2.0})
        first = transport.calls[0]
        assert first["method"] == "GET"
        assert first["url"].endswith("/images/FK")
        assert first["headers"] == {"X-Figma-Token": "tok"}
        assert first["params"] == {"ids": "1:2", "format": "png",
                                   "scale": 2.0}
        second = transport.calls[1]
        assert second["url"] == "https://s3.example/frame.png"

    def test_svg_export_omits_scale(self):
        transport = RecordingTransport([
            FakeResponse(payload={"images": {"1:2": "u"}}),
            FakeResponse(content=b"<svg/>"),
        ])
        connector = make_connector(transport)
        connector.send(None, {"file_key": "FK", "node_id": "1:2",
                        "format": "svg"})
        assert "scale" not in transport.calls[0]["params"]

    def test_missing_token_is_failed_job_with_setup_hint(self):
        connector = make_connector(RecordingTransport([]), token="")
        result = connector.poll(
            connector.send(None, {"file_key": "F", "node_id": "n"}))
        assert not result.ok
        assert "FIGMA_TOKEN" in result.error and "secrets" in result.error

    def test_missing_fields_fail_fast(self):
        transport = RecordingTransport([])
        connector = make_connector(transport)
        for op in ({}, {"file_key": "F"}, {"node_id": "n"}):
            assert connector.poll(connector.send(None, op)).ok is False
        assert transport.calls == []

    def test_bad_format_rejected_before_any_call(self):
        transport = RecordingTransport([])
        connector = make_connector(transport)
        result = connector.poll(connector.send(
            None, {"file_key": "F", "node_id": "n", "format": "pdf"}))
        assert not result.ok and "png or svg" in result.error
        assert transport.calls == []

    def test_api_error_maps_to_failed_job(self):
        transport = RecordingTransport([FakeResponse(status_code=403)])
        connector = make_connector(transport)
        result = connector.poll(
            connector.send(None, {"file_key": "F", "node_id": "n"}))
        assert not result.ok and "403" in result.error

    def test_node_not_in_images_map_is_actionable(self):
        transport = RecordingTransport([FakeResponse(payload={"images": {}})])
        connector = make_connector(transport)
        result = connector.poll(
            connector.send(None, {"file_key": "F", "node_id": "9:9"}))
        assert not result.ok and "not found" in result.error


class TestListFrames:
    FILE_JSON = {"document": {"children": [
        {"name": "Page 1", "children": [
            {"id": "1:1", "name": "Hero", "type": "FRAME"},
            {"id": "1:2", "name": "Card", "type": "FRAME"},
            {"id": "1:3", "name": "Rect", "type": "RECTANGLE"},
        ]},
        {"name": "Page 2", "children": [
            {"id": "2:1", "name": "Icon", "type": "FRAME"},
        ]},
    ]}}

    def test_walks_pages_and_keeps_only_frames(self):
        transport = RecordingTransport([FakeResponse(payload=self.FILE_JSON)])
        frames = make_connector(transport).list_frames("FK")
        assert [(f["id"], f["page"]) for f in frames] == \
            [("1:1", "Page 1"), ("1:2", "Page 1"), ("2:1", "Page 2")]

    def test_no_token_raises_valueerror_for_picker(self):
        with pytest.raises(ValueError, match=FIGMA_TOKEN_NAME):
            make_connector(RecordingTransport([]),
                           token="").list_frames("FK")


class TestCapabilitiesAndDefaults:
    def test_capabilities_declare_account_auth_and_quota_note(self):
        caps = FigmaConnector().capabilities()
        assert caps.connector == "figma" and caps.auth == "account"
        assert caps.items[0].kind == "design"
        assert "Free account" in caps.items[0].quota_note

    def test_default_token_provider_reads_secrets_seam(self, monkeypatch):
        import engines.playground_bridge.connectors_figma as mod
        monkeypatch.setattr(mod, "load_secret",
                            lambda name: "from-secrets" if name ==
                            FIGMA_TOKEN_NAME else None)
        assert FigmaConnector._secrets_token() == "from-secrets"
