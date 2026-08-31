from dataclasses import dataclass


@dataclass(frozen=True)
class FormatOption:
    format_id: str
    height: int | None
    fps: float | None
    ext: str
    has_audio: bool
    has_video: bool
    filesize: int | None
    label: str
    expression: str


def collect_formats(info: dict) -> list[FormatOption]:
    """Build a clean, deduplicated list of practical video choices."""
    formats = info.get("formats", [])
    audio_formats = [f for f in formats if f.get("acodec") not in (None, "none")]
    best_audio = max(audio_formats, key=lambda f: (f.get("abr") or 0, f.get("tbr") or 0), default=None)
    best: dict[int, tuple[tuple, FormatOption]] = {}

    for raw in formats:
        height = raw.get("height")
        if not raw.get("vcodec") or raw.get("vcodec") == "none" or not height:
            continue
        if height < 1 or height > 4320:
            continue
        has_audio = raw.get("acodec") not in (None, "none")
        expression = str(raw["format_id"])
        if not has_audio and best_audio:
            expression = f"{raw['format_id']}+{best_audio['format_id']}"
        size = raw.get("filesize") or raw.get("filesize_approx")
        option = FormatOption(
            str(raw["format_id"]), height, raw.get("fps"), raw.get("ext", ""),
            has_audio, True, size, f"{height}p", expression,
        )
        score = (1 if has_audio else 0, raw.get("fps") or 0, raw.get("tbr") or 0, size or 0)
        if height not in best or score > best[height][0]:
            best[height] = (score, option)

    return [item[1] for item in sorted(best.values(), key=lambda x: x[1].height or 0)]
