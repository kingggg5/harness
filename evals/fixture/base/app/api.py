from app.store import ORDERS


def list_orders(status=None):
	"""Return orders, optionally filtered by status, ordered by id."""
	rows = [o for o in ORDERS if status is None or o["status"] == status]
	return sorted(rows, key=lambda o: o["id"])
