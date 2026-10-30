FREE_SHIPPING_FROM = 50


def shipping_fee(subtotal, country):
	"""Flat fee by country; Thai orders from FREE_SHIPPING_FROM are free."""
	if country == "TH":
		return 0.0 if subtotal >= FREE_SHIPPING_FROM else 5.0
	return 15.0
