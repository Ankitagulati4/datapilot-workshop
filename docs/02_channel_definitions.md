# Sales channel definitions

ShopFlow recognizes three sales channels. The `channel` column on
`orders` always contains one of these three values.

## web
Orders placed through the desktop website (shopflow.com). Historically
our largest channel by revenue and order count. Customers tend to place
larger basket orders here.

## mobile
Orders placed through the ShopFlow iOS / Android apps. Smaller average
basket but the highest order *frequency* per customer. Most growth in
the last 18 months has come from mobile.

## retail
Orders placed in physical ShopFlow pop-up stores (currently 4 locations
worldwide). Cash and card. Lowest volume channel; we use it primarily
for brand presence in new markets.

When DataPilot is asked about "channel performance", it should join
`orders.channel` and group by this column.
