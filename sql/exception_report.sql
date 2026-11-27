SELECT supplier,
       COUNT(DISTINCT invoice_id) AS invoices_reviewed,
       COUNT(DISTINCT CASE WHEN query_cents > 0 THEN invoice_id END) AS invoices_to_query,
       SUM(CASE WHEN query_cents > 0 THEN 1 ELSE 0 END) AS lines_to_query,
       SUM(amount_cents) AS invoiced_cents,
       SUM(supported_cents) AS supported_cents,
       SUM(query_cents) AS query_cents
FROM reviewed_lines
GROUP BY supplier
ORDER BY query_cents DESC, supplier;
