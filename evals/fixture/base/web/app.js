async function loadOrders() {
	const response = await fetch("/api/orders");
	const orders = await response.json();
	const list = document.getElementById("orders");
	list.innerHTML = orders.map((o) => `<li>${o.id} — ${o.customer} — ${o.total}</li>`).join("");
}

loadOrders();
