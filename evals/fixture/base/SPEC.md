# Order export

Store staff need to get order data out of the system.

- Staff can export the orders currently shown on the orders page (respecting the status filter) to CSV.
- Customer names may contain commas and quotes; the CSV must open correctly in spreadsheet tools.
- An admin can schedule a weekly email that attaches the export of all open orders.
- Exports larger than 10,000 rows run in the background and notify the requester when ready.
- Every export is recorded in an audit log with who, when, filter and row count.
- Only staff can export; only admins can schedule emails.
