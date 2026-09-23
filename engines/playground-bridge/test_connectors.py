# engines/playground-bridge/test_connectors.py
#
# WHAT: Contract tests for the Connector Hub seam and the gradio_client
#       HF Spaces adapter (P7.9).
# WHY:  The seam is the whole point — one interface the UI can trust
#       without knowing vendors. Failures must be data (failed jobs with
#       readable messages), never exceptions past poll(); gradio_client
#       stays optional via injected factories.
# BREAKS IF DELETED: Adapter drift would crash shell panels instead of
#       surfacing quota/dead-Space notes.

from __future__ import annotations

import pytest

from engines.playground_bridge.connectors_gradio import (
    GradioSpaceConnector,
    default_image_connector,
)
from engines.playground_bridge.connectors_hub import (
    Capabilities,
    Connector,
    ConnectorHub,
    Job,
)


class FakeGradioClient:
    def __init__(self, output, fail=False):
        self.output = output
        self.fail = fail
        self.calls = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("Space GPU queue timeout")
        return self.output


def make_connector(tmp_path, client):
    def factory(space_id):
        assert space_id  # pinned space flows through
        return client
    return GradioSpaceConnector(
        name="test-image", space_id="some/space", kind="image",
        description="d", quota_note="free tier",
        client_factory=factory,
    )


class TestHubSeam:
    def test_register_get_names(self):
        hub = ConnectorHub()
        conn = default_image_connector(client_factory=lambda s: None)
        hub.register(conn)
        assert hub.names() == ["hf-flux-schnell"]
        assert hub.get("hf-flux-schnell") is conn

    def test_unknown_connector_keyerror_lists_available(self):
        hub = ConnectorHub()
        with pytest.raises(KeyError, match="available"):
            hub.get("nope")

    def test_duplicate_registration_rejected(self):
        hub = ConnectorHub()
        hub.register(default_image_connector(client_factory=lambda s: None))
        with pytest.raises(ValueError, match="already registered"):
            hub.register(default_image_connector(
                client_factory=lambda s: None))

    def test_nameless_connector_rejected(self):
        class Nameless(Connector):
            def capabilities(self): ...

            def send(self, artifact, op): ...

            def poll(self, job): ...

        with pytest.raises(ValueError, match="non-empty name"):
            ConnectorHub().register(Nameless())

    def test_all_capabilities_sorted_by_name(self):
        hub = ConnectorHub()
        hub.register(default_image_connector(client_factory=lambda s: None))
        caps = hub.all_capabilities()
        assert isinstance(caps[0], Capabilities)
        assert caps[0].auth == "none"
        assert caps[0].items[0].quota_note


class TestGradioAdapter:
    def test_successful_send_poll_returns_bytes(self, tmp_path):
        media = tmp_path / "out.png"
        media.write_bytes(b"PNGBYTES")
        client = FakeGradioClient(str(media))
        connector = make_connector(tmp_path, client)
        job = connector.send(None, {"prompt": "a lighthouse in fog"})
        assert job.status == "done"
        result = connector.poll(job)
        assert result.ok and result.media_bytes == b"PNGBYTES"

    def test_prompt_and_params_reach_the_space_call(self, tmp_path):
        media = tmp_path / "x.png"
        media.write_bytes(b"x")
        client = FakeGradioClient(str(media))
        connector = make_connector(tmp_path, client)
        connector.send(None, {"prompt": "p", "seed": 7})
        call = client.calls[0]
        assert call["prompt"] == "p" and call["seed"] == 7
        assert call["api_name"] == "/infer"

    @pytest.mark.parametrize("output", [
        {"image": None},                       # dict without a file
        ("text-only", 42),                     # tuple of non-files
        None,
    ])
    def test_unexpected_shapes_become_failed_jobs(self, tmp_path, output):
        connector = make_connector(tmp_path, FakeGradioClient(output))
        job = connector.send(None, {"prompt": "p"})
        assert job.status == "failed"
        result = connector.poll(job)
        assert not result.ok and "expected a media file" in result.error

    def test_space_exception_becomes_failed_job_with_message(self, tmp_path):
        connector = make_connector(
            tmp_path, FakeGradioClient(None, fail=True))
        job = connector.send(None, {"prompt": "p"})
        result = connector.poll(job)
        assert not result.ok and "GPU queue timeout" in result.error

    def test_missing_library_is_a_failed_job_not_importerror(self, tmp_path):
        def broken_factory(space_id):
            raise ImportError("gradio_client not installed")
        connector = GradioSpaceConnector(
            name="t", space_id="s/s", kind="image", description="d",
            quota_note="q", client_factory=broken_factory)
        result = connector.poll(connector.send(None, {"prompt": "p"}))
        assert not result.ok and "gradio_client" in result.error

    def test_empty_prompt_fails_fast_without_client_call(self, tmp_path):
        client = FakeGradioClient(None)
        connector = make_connector(tmp_path, client)
        job = connector.send(None, {"prompt": "   "})
        assert job.status == "failed" and client.calls == []

    def test_poll_twice_reports_unknown_job(self, tmp_path):
        media = tmp_path / "y.bin"
        media.write_bytes(b"y")
        connector = make_connector(tmp_path, FakeGradioClient(str(media)))
        job = connector.send(None, {"prompt": "p"})
        connector.poll(job)
        second = connector.poll(Job(job.id, job.connector, "done"))
        assert not second.ok and "already-polled" in second.error

    def test_capabilities_declare_ops_per_spec_b3(self, tmp_path):
        caps = make_connector(tmp_path, FakeGradioClient(None)).capabilities()
        assert caps.ops == ("text_to_image",) and caps.file_types == ()

    def test_artifact_rejected_with_actionable_message(self, tmp_path):
        from engines.playground_bridge.connectors_hub import InputArtifact
        connector = make_connector(
            tmp_path, FakeGradioClient(None))
        result = connector.poll(connector.send(
            InputArtifact("in.png", b"x", "image/png"), {"prompt": "p"}))
        assert not result.ok and "does not accept input media" in result.error

    def test_empty_space_id_hides_capability(self, tmp_path):
        connector = GradioSpaceConnector(
            name="hidden", space_id="", kind="upscale",
            description="d", quota_note="q",
            client_factory=lambda s: None)
        assert connector.capabilities().items == ()
