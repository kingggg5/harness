from app import api


def fetch_all_orders(status=None):
	return api.list_orders(status)
