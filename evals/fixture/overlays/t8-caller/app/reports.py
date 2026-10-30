from app.api import list_orders


def shipped_revenue():
	"""Total value of every shipped order."""
	return round(sum(o["total"] for o in list_orders("shipped")), 2)
