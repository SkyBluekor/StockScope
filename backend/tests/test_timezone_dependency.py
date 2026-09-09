from zoneinfo import ZoneInfo

import tzdata


def test_asia_seoul_timezone_is_available() -> None:
    assert tzdata.__version__
    assert ZoneInfo("Asia/Seoul").key == "Asia/Seoul"
