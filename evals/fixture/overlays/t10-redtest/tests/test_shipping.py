from app.shipping import shipping_fee


def test_thai_orders_from_50_ship_free():
	assert shipping_fee(50, "TH") == 0.0
	assert shipping_fee(49.99, "TH") == 5.0


def test_country_codes_are_case_insensitive():
	assert shipping_fee(10, "th") == 5.0
	assert shipping_fee(80, "th") == 0.0


def test_other_countries_pay_flat_fee():
	assert shipping_fee(80, "US") == 15.0
