# Data freshness SLAs

DataPilot's freshness checks compare the most recent timestamp in a
table against "now" (UTC). These are the business SLAs each table is
expected to meet.

## orders
- **Hot SLA:** rows from web + mobile channels should be visible in the
  warehouse within **15 minutes** of being placed.
- **Cold SLA:** the most recent `order_date` in the table should never
  be more than **24 hours** stale. Anything older indicates an ETL
  failure.
- DataPilot tags `orders` as `[STALE]` when freshness > 24h.

## web_sessions
- Sessions are batch-loaded every 6 hours.
- Expected staleness: up to 6 hours is normal. 12+ hours indicates a
  pipeline issue.

## customers
- Snapshot table — refreshed nightly.
- Expected staleness: 24-48 hours is normal.

## products
- Catalog table — refreshed nightly.
- Same SLA as customers.

## support_tickets
- Streaming load.
- Expected staleness: < 30 minutes during business hours.

## returns
- Batch loaded every 4 hours.
- Expected staleness: < 4 hours.

## When DataPilot reports `[STALE]`
The `check_freshness` tool tags any table older than 24h as `[STALE]`.
That's a generic threshold — apply the per-table SLAs above for the
real assessment.
