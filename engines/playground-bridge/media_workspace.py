# engines/playground-bridge/media_workspace.py
#
# WHAT: The Media Workspace core — local editing of ANY media via
#       ffmpeg, built as pure plan functions (MediaSpec argv builders)
#       plus one thin executor. Ingest/probe, trim, concat, overlay,
#       mix, volume, scale/pad, convert (P7.7).
# WHY:  Plan B1 of docs/PLAYGROUND_AND_LANGUAGE_LAB_PLAN.md: editing is
#       local, always. Planners are pure functions returning exact
#       command specifications — fully testable without a display or
#       even an ffmpeg binary — while execution is one injectable
#       runner call away. No UI, no cloud, no surprises.
# BREAKS IF DELETED: The Playground has no local editing core; every
#       later op (UI, connectors) would hand-roll ffmpeg invocations.

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "MediaSpec", "MediaToolError", "ProbeResult",
    "plan_convert", "plan_trim", "plan_scale", "plan_pad",
    "plan_volume", "plan_mix", "plan_concat", "plan_overlay",
    "execute", "probe", "ingest",
]

FFMPEG_PATH = "ffmpeg"
FFPROBE_PATH = "ffprobe"


class MediaToolError(RuntimeError):
    """ffmpeg/ffprobe failed or is missing; carries the stderr tail."""


# ---------------------------------------------------------------------------
# Command specification (the plan)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MediaSpec:
    """One planned ffmpeg invocation. `args` sits between inputs and
    output. `side_files` are written next to execution (e.g. concat
    lists). Everything is plain data — hashable, printable, testable."""
    input_paths: tuple[str, ...]
    output_path: str
    args: tuple[str, ...] = ()
    side_files: tuple[tuple[str, str], ...] = ()  # (path, content)

    def argv(self, binary: str = FFMPEG_PATH,
             *, overwrite: bool = True) -> list[str]:
        cmd = [binary]
        if overwrite:
            cmd.append("-y")
        for path in self.input_paths:
            cmd += ["-i", path]
        cmd += list(self.args)
        cmd.append(self.output_path)
        return cmd


Runner = Callable[..., Any]  # subprocess.run-compatible


def _require_parent(output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)


def plan_convert(src: str, dst: str, *,
                 video_codec: Optional[str] = None,
                 audio_codec: Optional[str] = None,
                 audio_rate: Optional[int] = None,
                 format: Optional[str] = None) -> MediaSpec:
    """Container/format conversion; also THE normalize primitive."""
    args: list[str] = []
    if video_codec:
        args += ["-vcodec", video_codec]
    if audio_codec:
        args += ["-acodec", audio_codec]
    if audio_rate:
        args += ["-ar", str(audio_rate)]
    if format:
        args += ["-f", format]
    return MediaSpec((src,), dst, tuple(args))


def plan_trim(src: str, dst: str, *, start: float, end: float) -> MediaSpec:
    """Cut [start, end] seconds. Output-side seeking keeps cuts frame-
    accurate at the cost of a little speed."""
    if end <= start:
        raise ValueError("trim end must be after start")
    return MediaSpec((src,), dst,
                     ("-ss", f"{start:.3f}", "-to", f"{end:.3f}"))


def plan_scale(src: str, dst: str, *, width: int, height: int) -> MediaSpec:
    return MediaSpec((src,), dst,
                     ("-vf", f"scale={int(width)}:{int(height)}"))


def plan_pad(src: str, dst: str, *, width: int, height: int) -> MediaSpec:
    w, h = int(width), int(height)
    return MediaSpec((src,), dst,
                     ("-vf", f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"))


def plan_volume(src: str, dst: str, *, db: float) -> MediaSpec:
    return MediaSpec((src,), dst, ("-af", f"volume={float(db)}dB"))


def plan_mix(sources: tuple[str, ...] | list[str], dst: str,
             *, duration: Optional[str] = None) -> MediaSpec:
    """Mix N audio inputs with amix (mean of inputs)."""
    sources = tuple(sources)
    if len(sources) < 2:
        raise ValueError("mix needs at least two inputs")
    n = len(sources)
    dur = duration or "longest"
    args = ("-filter_complex",
            f"amix=inputs={n}:duration={dur}:dropout_transition=2")
    return MediaSpec(sources, dst, args)


def plan_concat(sources: tuple[str, ...] | list[str], dst: str) -> MediaSpec:
    """Concatenate via the concat demuxer: inputs must share codec
    parameters (normalize first when they don't)."""
    sources = tuple(sources)
    if len(sources) < 2:
        raise ValueError("concat needs at least two inputs")
    listing = "".join(f"file '{p}'\n" for p in sources)
    list_path = str(Path(dst).with_suffix(".concat.txt"))
    spec = MediaSpec(
        (list_path,), dst,
        ("-f", "concat", "-safe", "0", "-copyts"),
        ((list_path, listing),),
    )
    return spec


def plan_overlay(base: str, overlay_path: str, dst: str, *,
                 x: int = 0, y: int = 0) -> MediaSpec:
    x, y = int(x), int(y)
    return MediaSpec((base, overlay_path), dst,
                     ("-filter_complex", f"overlay={x}:{y}"))


# ---------------------------------------------------------------------------
# Execution + probing
# ---------------------------------------------------------------------------

def execute(spec: MediaSpec, *,
            runner: Optional[Runner] = None,
            binary: str = FFMPEG_PATH) -> None:
    """
    Contract: run one planned command. Writes any side files first
    (parents created), then invokes the binary.

    Raises:
        MediaToolError: nonzero exit (includes stderr tail) or binary
            not found.
    """
    run = runner if runner is not None else subprocess.run
    _require_parent(spec.output_path)
    for path, content in spec.side_files:
        _require_parent(path)
        Path(path).write_text(content, encoding="utf-8")
    argv = spec.argv(binary)
    logger.info("media workspace exec: %s", " ".join(argv))
    try:
        completed = run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise MediaToolError(
            f"{binary!r} not found in PATH — install ffmpeg "
            "(see root README fresh-machine guide).") from exc
    stderr = b"" if completed.stderr is None else completed.stderr
    if getattr(completed, "returncode", 1) != 0:
        tail = stderr.decode(errors="replace")[-400:]
        raise MediaToolError(f"{binary} exited "
                             f"{completed.returncode}: {tail}")


def probe(path: str, *,
          runner: Optional[Runner] = None,
          binary: str = FFPROBE_PATH) -> "ProbeResult":
    """Contract: ffprobe a media file into typed metadata."""
    run = runner if runner is not None else subprocess.run
    argv = [binary, "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", path]
    try:
        completed = run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise MediaToolError(
            f"{binary!r} not found in PATH — install ffmpeg.") from exc
    if getattr(completed, "returncode", 1) != 0:
        tail = (completed.stderr or b"").decode(errors="replace")[-400:]
        raise MediaToolError(f"ffprobe failed for {path}: {tail}")
    data = json.loads(completed.stdout.decode())
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    return ProbeResult(
        path=str(path),
        container=fmt.get("format_name", ""),
        duration_seconds=float(fmt["duration"]) if "duration" in fmt else None,
        size_bytes=int(fmt["size"]) if "size" in fmt else None,
        has_video=any(s.get("codec_type") == "video" for s in streams),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        width=next((s.get("width") for s in streams
                    if s.get("codec_type") == "video"), None),
        height=next((s.get("height") for s in streams
                     if s.get("codec_type") == "video"), None),
        raw=data,
    )


@dataclass(frozen=True)
class ProbeResult:
    path: str
    container: str
    duration_seconds: Optional[float]
    size_bytes: Optional[int]
    has_video: bool
    has_audio: bool
    width: Optional[int]
    height: Optional[int]
    raw: dict = field(repr=False, default_factory=dict)


def ingest(src: str, workspace_dir: str, *,
           runner: Optional[Runner] = None) -> ProbeResult:
    """
    Contract: copy any file into the workspace (collision-safe name)
    and probe it. Ingest never transcodes — normalization is an explicit
    plan_convert step so users keep originals.
    """
    src_path = Path(src)
    if not src_path.is_file():
        raise FileNotFoundError(f"cannot ingest missing file: {src}")
    dest_dir = Path(workspace_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src_path.name
    stem, suffix = dest.stem, dest.suffix
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{stem}-{counter}{suffix}"
        counter += 1
    shutil.copy2(src_path, dest)
    result = probe(str(dest), runner=runner)
    logger.info("Ingested %s -> %s (%s)", src, dest, result.container)
    return result
