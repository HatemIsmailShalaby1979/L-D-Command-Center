# engines/playground-bridge/test_media_workspace.py
#
# WHAT: Contract tests for the Media Workspace core (P7.7).
# WHY:  Planners are pure — their exact argv IS the contract, asserted
#       verbatim here. Execution and probing run against fake runners,
#       so no ffmpeg binary is required to prove behavior.
# BREAKS IF DELETED: Command-shape regressions (wrong filter strings,
#       lost -y, broken concat lists) would only surface on real media.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engines.playground_bridge.media_workspace import (
    MediaSpec,
    MediaToolError,
    execute,
    ingest,
    plan_concat,
    plan_convert,
    plan_mix,
    plan_overlay,
    plan_pad,
    plan_scale,
    plan_trim,
    plan_volume,
    probe,
)


class FakeRunner:
    def __init__(self, returncode=0, stderr=b"", stdout=b""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        import subprocess as _sp

        class Completed:
            pass

        c = Completed()
        c.returncode = self.returncode
        c.stderr = self.stderr
        c.stdout = self.stdout
        return c


@pytest.fixture
def runner():
    return FakeRunner()


class TestPlannersArePureAndExact:
    def test_convert(self):
        spec = plan_convert("a.mkv", "a.mp4", video_codec="libx264",
                            audio_codec="aac", audio_rate=44100)
        assert spec.argv() == ["ffmpeg", "-y", "-i", "a.mkv",
                               "-vcodec", "libx264", "-acodec", "aac",
                               "-ar", "44100", "a.mp4"]

    def test_trim_rejects_inverted_range(self):
        with pytest.raises(ValueError):
            plan_trim("in.wav", "out.wav", start=5, end=5)

    def test_trim(self):
        assert plan_trim("in.wav", "out.wav", start=1.5, end=4).args == (
            "-ss", "1.500", "-to", "4.000")

    def test_scale_and_pad(self):
        assert plan_scale("i", "o", width=640, height=360).args == (
            "-vf", "scale=640:360")
        assert plan_pad("i", "o", width=1920, height=1080).args == (
            "-vf", "pad=1920:1080:(ow-iw)/2:(oh-ih)/2")

    def test_volume(self):
        assert plan_volume("i", "o", db=-3.5).args == ("-af", "volume=-3.5dB")

    def test_mix_needs_two_inputs_and_builds_amix(self):
        with pytest.raises(ValueError):
            plan_mix(["only.wav"], "o.wav")
        spec = plan_mix(["a.wav", "b.wav", "c.wav"], "mix.wav")
        assert spec.args == ("-filter_complex",
                             "amix=inputs=3:duration=longest:dropout_transition=2")
        assert spec.input_paths == ("a.wav", "b.wav", "c.wav")

    def test_concat_writes_demuxer_listing_as_side_file(self):
        spec = plan_concat(["p1.wav", "p2.wav"], "joined.wav")
        list_path = spec.side_files[0][0]
        assert list_path.endswith("joined.concat.txt")
        assert spec.side_files[0][1] == "file 'p1.wav'\nfile 'p2.wav'\n"
        assert spec.args[:4] == ("-f", "concat", "-safe", "0")
        assert spec.input_paths == (list_path,)
        with pytest.raises(ValueError):
            plan_concat(["solo.wav"], "x.wav")

    def test_overlay(self):
        spec = plan_overlay("vid.mp4", "logo.png", "out.mp4", x=10, y=20)
        assert spec.input_paths == ("vid.mp4", "logo.png")
        assert spec.args == ("-filter_complex", "overlay=10:20")

    def test_specs_are_plain_data_and_deterministic(self):
        one = plan_trim("a", "b", start=0, end=1)
        two = plan_trim("a", "b", start=0, end=1)
        assert one == two and hash(one) == hash(two)


class TestExecute:
    def test_success_invokes_binary_with_full_argv(self, tmp_path, runner):
        spec = plan_volume(str(tmp_path / "in.wav"),
                           str(tmp_path / "out.wav"), db=-2)
        execute(spec, runner=runner)
        argv = runner.calls[0]
        assert argv[0] == "ffmpeg" and argv[1] == "-y"
        assert argv[-1].endswith("out.wav")

    def test_side_files_materialize_before_run(self, tmp_path, runner):
        dst = str(tmp_path / "joined.wav")
        spec = plan_concat([str(tmp_path / "a.wav"), str(tmp_path / "b.wav")],
                           dst)
        execute(spec, runner=runner)
        list_file = Path(spec.input_paths[0])
        assert list_file.exists()
        assert "file '" in list_file.read_text()

    def test_failure_raises_media_tool_error_with_stderr_tail(self, tmp_path):
        bad = FakeRunner(returncode=1,
                         stderr=b"error blob".ljust(600, b"!"))
        spec = plan_volume("in.wav", str(tmp_path / "o.wav"), db=-2)
        with pytest.raises(MediaToolError, match="exited 1"):
            execute(spec, runner=bad)

    def test_missing_binary_maps_to_install_hint(self, tmp_path):
        def missing(argv, **kwargs):
            raise FileNotFoundError("ffmpeg")
        spec = plan_volume("in.wav", str(tmp_path / "o.wav"), db=-2)
        with pytest.raises(MediaToolError, match="install ffmpeg"):
            execute(spec, runner=missing)

    def test_creates_missing_output_parent(self, tmp_path, runner):
        out = tmp_path / "deep" / "nested" / "o.wav"
        execute(plan_volume("in.wav", str(out), db=-2), runner=runner)
        assert (tmp_path / "deep" / "nested").is_dir()


FFPROBE_JSON = json.dumps({
    "format": {"format_name": "mov,mp4", "duration": "12.5", "size": "96000"},
    "streams": [
        {"codec_type": "video", "width": 1280, "height": 720},
        {"codec_type": "audio"},
    ],
}).encode()


class TestProbeAndIngest:
    def test_probe_parses_canned_ffprobe_output(self, runner):
        runner.stdout = FFPROBE_JSON
        result = probe("/media/clip.mp4", runner=runner)
        assert result.container == "mov,mp4"
        assert result.duration_seconds == 12.5
        assert result.has_video and result.has_audio
        assert (result.width, result.height) == (1280, 720)
        assert runner.calls[0][:3] == ["ffprobe", "-v", "quiet"]

    def test_probe_failure_raises(self):
        with pytest.raises(MediaToolError, match="ffprobe failed"):
            probe("x.mp4", runner=FakeRunner(returncode=1))

    def test_ingest_copies_then_probes_collision_safe(self, tmp_path, runner):
        src = tmp_path / "song.wav"
        src.write_bytes(b"data")
        runner.stdout = FFPROBE_JSON
        dest_dir = tmp_path / "library"
        first = ingest(str(src), str(dest_dir), runner=runner)
        second_src = tmp_path / "sub" / "song.wav"
        second_src.parent.mkdir()
        second_src.write_bytes(b"x")
        ingest(str(second_src), str(dest_dir), runner=runner)
        assert (dest_dir / "song.wav").read_bytes() == b"data"
        assert (dest_dir / "song-1.wav").exists()
        assert first.path.endswith("song.wav")

    def test_ingest_rejects_missing_source(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ingest(str(tmp_path / "nope.wav"), str(tmp_path))
