# Competitor-based resale estimates — user-selected policy, 7 November 2026

Sold data is **not a prerequisite** for this separate practical valuation path.
Existing official Browse current offers supply exact-title NEW physical product
competition, including fixed quoted shipping, GB location, sample dates, item IDs
and public seller IDs. Existing verified A/B grades and sold evidence are unchanged.
LEGO and specific gaming/platform identities are supported; vague shoe sizes,
fragrance variants and unspecified technology models are not guessed.

## Model and economics

- Remove the actual acquisition listing by canonical URL/item ID, and its known
  seller when available. Direct eBay item links in the RSS description are retained
  without following redirectors. When an eBay acquisition cannot be identified,
  do not emit an opportunity. Missing retailer/seller links remain explicitly unknown.
- Deduplicate items and keep the cheapest delivered listing per seller. Quantity is
  not a sales/sample count. Unknown-seller offers can lower competition but cannot
  establish independent-seller confidence.
- Never remove genuinely cheaper competition to manufacture an edge. Same-promotion
  listings are excluded from regular-price references, but their current lower price
  still caps resale. Advertised original prices are labelled as such, not invented
  regular market values. Missing discount metadata means unknown, not full price.
- Estimated resale = **97% of lowest accepted competing delivered ask**. Suggested
  listing = lowest ask minus 1p. Model range = 90%–100% of that competing total.
  The 90% figure is a quick-sale pricing scenario, **not observed selling speed**.
- Five independent sellers and at least two within 10% of the low price support the
  separate CHECK path. Wide spreads lower confidence, never delete cheap offers.
  Low competing offers with unapplied coupons require an additional check.
- Count conservative eBay business fees plus fee VAT, outbound home postage,
  packaging and returns allowance. Unknown inbound delivery gives a qualified net
  upper bound; actual net/ROI remain null. Show delivery headroom, not assumed £0.
- Max landed buy satisfies both £8 net and 40% ROI, capped at £60. Required resale
  target/break-even remain separate from market-derived estimated resale.

`ESTIMATED OPPORTUNITY — CHECK BEFORE BUYING` is distinct from verified BUY. It
requires known delivery, the above sample support, online eligibility and economics.
Check actual retailer stock, checkout cost and exact variant before buying. No
cash exit, sales velocity or profit guarantee is inferred. No manually crafted
Discord test messages are needed; offline tests and no-send real-source publication
validate it, and normal app operation may publish the labelled cards.

Worker Price Check and Resale Estimates display these models, competitor links,
confidence, fee economics and missing delivery. Raw full bounded provenance stays
in operational state; public bot payloads include at most ten examples per snapshot.

Official field reference (consulted this turn):
https://developer.ebay.com/api-docs/buy/browse/types/gct:ItemSummary
`itemId`, `seller.username`, `marketingPrice.originalPrice/discountAmount/discountPercentage`,
`availableCoupons`, `shippingOptions`. Existing documented Browse search remains the
only active-market acquisition endpoint. No browser challenge is retried and no
active ask is inserted as a sale.

Live provenance exposed a Wall Display Mount incorrectly sharing LEGO set/name
words. Display/wall mounting accessories are now excluded explicitly. Retained
cached offers are rechecked under current matching rules before valuation, with
excluded provenance retained and original observation dates unchanged. A code
repair therefore fixes cached comparators without pretending to observe a new sale
or waiting six hours for the bad entry to expire.
