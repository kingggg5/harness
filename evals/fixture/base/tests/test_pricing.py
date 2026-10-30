from app.pricing import order_total


def test_small_order_has_no_discount():
	assert order_total([{"price": 20, "qty": 2}]) == 40.0


def test_shipping_is_added():
	assert order_total([{"price": 20, "qty": 1}], shipping=5) == 25.0
