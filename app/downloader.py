from pathlib import Path
import yt_dlp
from app.formats import collect_formats


class Downloader:
    def __init__(self, download_dir: Path, temp_dir: Path):
        self.download_dir = download_dir
        self.temp_dir = temp_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def inspect(self, url: str) -> dict:
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {"title": info.get("title") or "Untitled", "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"), "extractor": info.get("extractor_key") or info.get("extractor"),
                "webpage_url": info.get("webpage_url") or url, "formats": collect_formats(info)}

    def download(self, url: str, format_expression: str, job_id: int, progress_hook=None) -> Path:
        template = str(self.download_dir / f"{job_id}-%(title).120s.%(ext)s")
        opts = {"format": format_expression, "outtmpl": template, "noplaylist": True,
                "restrictfilenames": True, "merge_output_format": "mp4",
                "paths": {"home": str(self.download_dir), "temp": str(self.temp_dir)},
                "retries": 3, "fragment_retries": 3, "continuedl": True,
                "overwrites": False, "quiet": True, "no_warnings": True}
        if progress_hook:
            opts["progress_hooks"] = [progress_hook]
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        matches = sorted(self.download_dir.glob(f"{job_id}-*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not matches:
            raise RuntimeError("Download completed but output file was not found")
        return matches[0]
