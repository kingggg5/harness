from app.pricing import order_total


def checkout(payload):
	"""Price a cart sent by the iOS, Android and web clients as decoded JSON."""
	items = payload.get("items", [])
	shipping = float(payload.get("shipping", 0))
	return order_total(items, shipping)
