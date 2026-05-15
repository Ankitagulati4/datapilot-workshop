# Customer segment glossary

The `customers.segment` column has exactly three possible values:

## new
A customer whose first order was within the last 90 days. They get
welcome email flows and a 10% off second-order coupon. We measure new
customer **activation rate** = (placed 2nd order within 30 days) /
(total new).

## returning
A customer with 2 or more orders, none of them in the last 90 days
classifying them as new. Returning customers are the bulk of revenue
and receive standard lifecycle marketing.

## vip
A customer with lifetime revenue above $2,000 OR more than 12 orders.
VIP customers get early access to new product launches, a dedicated
support email, and free expedited shipping. VIP status is recomputed
nightly and never decays — once VIP, always VIP.

When asked about "VIP customers" or "top customers", DataPilot should
filter `WHERE segment = 'vip'`.
