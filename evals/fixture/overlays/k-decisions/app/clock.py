from datetime import datetime, timezone


def now():
	"""Current UTC time."""
	return datetime.now(timezone.utc)
