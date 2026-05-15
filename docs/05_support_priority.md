# Support ticket priorities

The `support_tickets.priority` column uses these values:

## P0 — Outage / fraud
Customer cannot complete a purchase, account is locked, or suspected
account-takeover fraud. Target first response: **15 minutes**. On-call
rotation pages the support lead.

## P1 — Order issue
Existing order problem: missing item, wrong item, damaged shipment,
delivery exception. Target first response: **2 hours** during business
hours, **next morning** otherwise.

## P2 — Billing / refund question
Refund status, billing dispute, store-credit question. Target first
response: **1 business day**.

## P3 — General inquiry
Product questions, sizing help, "how do I…" type questions. Target
first response: **2 business days**.

## Resolution SLA
All P0/P1 tickets must be resolved within 24 hours. P2 within 5 business
days. P3 within 10 business days. The `support_tickets.resolved` boolean
column tracks closure.

When DataPilot is asked "what is our worst priority ticket", it should
filter `WHERE resolved = 0 ORDER BY priority` (P0 sorts before P3).
