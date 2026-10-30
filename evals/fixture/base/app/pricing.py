DISCOUNT_THRESHOLD = 100
DISCOUNT_RATE = 0.10


def subtotal(items):
	return sum(item["price"] * item["qty"] for item in items)


def apply_discount(amount):
	if amount > DISCOUNT_THRESHOLD:
		return amount * (1 - DISCOUNT_RATE)
	return amount


def order_total(items, shipping=0.0):
	discounted = apply_discount(subtotal(items))
	total = apply_discount(discounted) + shipping
	return round(total, 2)
