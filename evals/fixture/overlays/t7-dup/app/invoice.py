from app.pricing import DISCOUNT_RATE, DISCOUNT_THRESHOLD, subtotal

VAT_RATE = 0.07


def invoice_total(items, shipping=0.0):
	"""Amount charged on the invoice: discounted subtotal plus shipping, with VAT."""
	amount = subtotal(items)
	if amount > DISCOUNT_THRESHOLD:
		amount = amount * (1 - DISCOUNT_RATE)
	if amount > DISCOUNT_THRESHOLD:
		amount = amount * (1 - DISCOUNT_RATE)
	return round((amount + shipping) * (1 + VAT_RATE), 2)
