"""Hidden acceptance tests, run against a trial repo after the agent finishes."""
import os

import pytest

TASK = os.environ.get("HAB_TASK", "")


@pytest.mark.skipif(TASK != "t1-bugfix", reason="t1 only")
def test_discount_applied_once():
	from app.pricing import order_total
	assert order_total([{"price": 100, "qty": 2}]) == 180.0
	assert order_total([{"price": 100, "qty": 2}], shipping=5) == 185.0
	assert order_total([{"price": 50, "qty": 1}]) == 50.0
	assert order_total([{"price": 100, "qty": 1}]) == 100.0


@pytest.mark.skipif(TASK != "t2-feature", reason="t2 only")
def test_cursor_pagination_covers_everything_once():
	from app import api, client
	seen = []
	page = api.list_orders(limit=10)
	assert set(page) >= {"items", "next_cursor"} and len(page["items"]) == 10
	while True:
		seen.extend(o["id"] for o in page["items"])
		if page["next_cursor"] is None:
			break
		page = api.list_orders(limit=10, cursor=page["next_cursor"])
	assert len(seen) == 25 and len(set(seen)) == 25
	shipped = client.fetch_all_orders("shipped")
	assert isinstance(shipped, list) and len(shipped) == 8
	assert all(o["status"] == "shipped" for o in shipped)
	assert len(client.fetch_all_orders()) == 25


@pytest.mark.skipif(TASK != "t4-library", reason="t4 only")
def test_iana_zones_with_dst():
	from app.dates import to_local
	assert to_local("2026-07-01T12:00:00Z", "America/New_York") == "2026-07-01T08:00:00-04:00"
	assert to_local("2026-01-15T12:00:00Z", "America/New_York") == "2026-01-15T07:00:00-05:00"
	assert to_local("2026-07-01T12:00:00Z", "Europe/London") == "2026-07-01T13:00:00+01:00"
	assert to_local("2026-01-01T17:30:00Z", "Asia/Bangkok") == "2026-01-02T00:30:00+07:00"
	assert to_local("2026-01-01T00:00:00Z", "Australia/Sydney") == "2026-01-01T11:00:00+11:00"
