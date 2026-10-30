from app.dates import to_local


def test_bangkok():
	assert to_local("2026-01-01T17:30:00Z", "Asia/Bangkok") == "2026-01-02T00:30:00+07:00"
