# ShopFlow data dictionary (summary)

Full schema lives in `data/build_shopflow.py`. This document summarizes
the meaning of less-obvious columns.

## customers
- `customer_id` — surrogate primary key, never reused
- `email` — lower-cased, unique, business contact
- `country` — ISO 3166-1 alpha-2 code (e.g. `US`, `IN`, `DE`)
- `signup_date` — ISO date of first account creation
- `segment` — one of `new` / `returning` / `vip` (see segment glossary)

## products
- `product_id` — surrogate PK
- `category` — one of: Apparel, Books, Electronics, Home, Outdoor,
  Toys, Beauty
- `price` — current list price in USD; updated when promo ends
- `cost` — last known landed cost (COGS); updated weekly
- `active` — 0/1; inactive products are hidden from the storefront but
  kept for historical join integrity

## orders
- `order_date` — wall-clock date the order was placed (NOT shipped)
- `channel` — see channel definitions
- `status` — one of `placed`, `shipped`, `delivered`, `cancelled`,
  `returned`. State machine: placed → shipped → delivered, with
  cancelled and returned as terminal states.
- `total_amount` — sum of (quantity * unit_price) across line items,
  before tax and shipping. Tax is not modeled in this dataset.

## order_items
- The line-item grain. To get revenue **per product**, you must SUM
  `quantity * unit_price` from `order_items`, NOT use `orders.total_amount`.
- `unit_price` is captured at the time of sale (may differ from the
  current `products.price` if there was a promo).

## returns
- One row per returned **item** (not per order). One order can spawn
  multiple return rows.
- See returns policy doc for reason codes.

## support_tickets
- See support priority doc for priority levels.
- `customer_id` is nullable (anonymous pre-account inquiries are
  allowed).
