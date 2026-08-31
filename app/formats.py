from dataclasses import dataclass


@dataclass(frozen=True)
class FormatOption:
    format_id: str
    height: int
    fps: float | None
    ext: str
    has_audio: bool
    has_video: bool
    filesize: int | None
    label: str
    expression: str


def collect_formats(info: dict) -> list[FormatOption]:
    formats = info.get("formats") or []
    audio = [f for f in formats if f.get("acodec") not in (None, "none")]
    best_audio = max(audio, key=lambda f: (f.get("abr") or 0, f.get("tbr") or 0, f.get("filesize") or f.get("filesize_approx") or 0), default=None)
    best: dict[int, FormatOption] = {}
    for f in formats:
        height = f.get("height")
        if not isinstance(height, int) or height <= 0 or f.get("vcodec") in (None, "none"):
            continue
        has_audio = f.get("acodec") not in (None, "none")
        fid = str(f.get("format_id"))
        expression = fid if has_audio or best_audio is None else f"{fid}+{best_audio.get('format_id')}"
        size = f.get("filesize") or f.get("filesize_approx")
        option = FormatOption(fid, height, f.get("fps"), f.get("ext") or "", has_audio, True, size, f"{height}p", expression)
        score = (1 if has_audio else 0, f.get("tbr") or 0, size or 0, f.get("fps") or 0)
        old = best.get(height)
        old_score = (-1, 0, 0, 0) if old is None else (1 if old.has_audio else 0, 0, old.filesize or 0, old.fps or 0)
        if old is None or score > old_score:
            best[height] = option
    return sorted(best.values(), key=lambda x: x.height)
