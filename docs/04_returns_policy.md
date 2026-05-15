# Returns policy

## Window
Customers may return any product within **30 days** of the order date
for a full refund. After 30 days, only store credit is offered, and only
for unworn / unopened items.

## Reason codes
The `returns.reason` column uses these standardized codes:
- `defective` — product arrived damaged or stopped working within 7 days
- `not_as_described` — product differs from listing photos or specs
- `wrong_size` — apparel only; customer ordered the wrong size
- `changed_mind` — buyer's remorse, no fault of the product
- `late_delivery` — arrived after the customer's needed-by date
- `other` — free-text fallback; should be < 5% of returns

## Refund processing
Refunds for `defective` and `not_as_described` are processed within 2
business days. All other reasons are processed within 7 business days
after the returned item is received and inspected at the warehouse.

## Restocking fee
We do **not** charge restocking fees on any return reason. This is a
deliberate brand promise.

## Excluded items
Personalized / monogrammed products and intimate apparel are
non-returnable. These are marked with `products.returnable = 0` in the
catalog (note: this column is not currently in the schema, planned for
v2).
