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

def collect_formats(info: dict) -> list[FormatOption]:
    best = {}
    for f in info.get("formats", []):
        h = f.get("height")
        if not f.get("vcodec") or f.get("vcodec") == "none":
            continue
        audio = bool(f.get("acodec") and f.get("acodec") != "none")
        key = h or 0
        candidate = FormatOption(str(f["format_id"]), h, f.get("fps"), f.get("ext", ""), audio, True, f.get("filesize") or f.get("filesize_approx"), f.get("format_note") or (f"{h}p" if h else f.get("ext", "video")))
        current = best.get(key)
        if current is None or (candidate.has_audio and not current.has_audio) or (candidate.filesize or 0) > (current.filesize or 0):
            best[key] = candidate
    return sorted(best.values(), key=lambda x: x.height or 0)
