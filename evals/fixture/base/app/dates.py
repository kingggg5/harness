from datetime import datetime, timedelta, timezone

OFFSETS = {"UTC": 0, "Asia/Bangkok": 7, "Europe/London": 0, "America/New_York": -5}


def to_local(ts_utc, tz_name):
	"""Convert an ISO-8601 UTC timestamp like '2026-07-01T12:00:00Z' to ISO local time."""
	dt = datetime.strptime(ts_utc, "%Y-%m-%dT%H:%M:%SZ")
	offset = timedelta(hours=OFFSETS[tz_name])
	return (dt + offset).replace(tzinfo=timezone(offset)).isoformat()
