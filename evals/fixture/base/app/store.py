ORDERS = [
	{
		"id": f"ord-{i:03d}",
		"customer": f"Customer {i}",
		"status": "open" if i % 3 else "shipped",
		"total": 20.0 + i * 7,
		"created": f"2026-09-{(i % 28) + 1:02d}T10:00:00Z",
	}
	for i in range(1, 26)
]
