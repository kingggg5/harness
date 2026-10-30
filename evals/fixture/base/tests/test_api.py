from app.api import list_orders


def test_lists_every_order():
	assert len(list_orders()) == 25


def test_filters_by_status():
	assert all(o["status"] == "shipped" for o in list_orders("shipped"))
