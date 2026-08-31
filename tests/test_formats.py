from app.formats import collect_formats


def test_collect_formats_deduplicates_by_height():
    info = {
        "formats": [
            {"format_id": "1", "height": 360, "vcodec": "avc", "acodec": "none", "ext": "mp4"},
            {"format_id": "2", "height": 360, "vcodec": "avc", "acodec": "aac", "ext": "mp4"},
            {"format_id": "3", "height": 720, "vcodec": "avc", "acodec": "aac", "ext": "mp4"},
            {"format_id": "4", "height": None, "vcodec": "none", "acodec": "aac", "ext": "m4a"},
        ]
    }
    result = collect_formats(info)
    assert [x.height for x in result] == [360, 720]
    assert result[0].has_audio
