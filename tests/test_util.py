from awstui.util import human_bytes


def test_human_bytes_bytes():
    assert human_bytes(0) == "0 B"
    assert human_bytes(512) == "512 B"


def test_human_bytes_kilobytes():
    assert human_bytes(1024) == "1.0 KB"
    assert human_bytes(1536) == "1.5 KB"


def test_human_bytes_megabytes():
    assert human_bytes(1024 * 1024) == "1.0 MB"


def test_human_bytes_gigabytes():
    assert human_bytes(1024**3) == "1.0 GB"


def test_human_bytes_terabytes_and_above_clamp_to_tb():
    assert human_bytes(1024**4) == "1.0 TB"
    # Petabyte-scale still reports in TB (no PB unit).
    assert human_bytes(1024**5).endswith(" TB")
