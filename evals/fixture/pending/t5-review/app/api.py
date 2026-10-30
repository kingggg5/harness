import os

from app.store import ORDERS


def list_orders(status=None):
	"""Return orders, optionally filtered by status, ordered by id."""
	rows = [o for o in ORDERS if status is None or o["status"] == status]
	return sorted(rows, key=lambda o: o["id"])


def export_orders(filename, status=None):
	"""Write matching orders as CSV under exports/ and return the path."""
	path = os.path.join("exports", filename)
	with open(path, "w") as fh:
		for o in list_orders(status):
			fh.write(f"{o['id']},{o['customer']},{o['total']}\n")
	return path


def recent_orders(n):
	"""Return the n most recently created orders."""
	return sorted(ORDERS, key=lambda o: o["created"])[-n - 1:]
