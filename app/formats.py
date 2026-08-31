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
    formats = info.get("formats", [])
    best_audio = next((f for f in reversed(formats) if f.get("acodec") not in (None, "none")), None)
    best = {}
    for f in formats:
        h = f.get("height")
        if not f.get("vcodec") or f.get("vcodec") == "none" or not h:
            continue
        audio = f.get("acodec") not in (None, "none")
        expression = str(f["format_id"]) if audio or not best_audio else f"{f['format_id']}+{best_audio['format_id']}"
        candidate = FormatOption(str(f["format_id"]), h, f.get("fps"), f.get("ext", ""), audio, True, f.get("filesize") or f.get("filesize_approx"), f"{h}p", expression)
        current = best.get(h)
        score = (1 if audio else 0, f.get("tbr") or 0, f.get("filesize") or f.get("filesize_approx") or 0)
        old_score = (-1, 0, 0) if current is None else (1 if current.has_audio else 0, 0, current.filesize or 0)
        if current is None or score > old_score:
            best[h] = candidate
    return sorted(best.values(), key=lambda x: x.height or 0)
