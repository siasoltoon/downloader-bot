from app.bot import valid_url


def test_valid_url():
    assert valid_url("https://example.com/video")
    assert valid_url("http://example.com/x")


def test_invalid_url():
    assert not valid_url("example.com/video")
    assert not valid_url("ftp://example.com/video")
    assert not valid_url("https://")
