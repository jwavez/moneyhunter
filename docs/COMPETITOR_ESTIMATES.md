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

## Bounded discovery and independent review policy (7 November 2026)

- Public estimate policy is `moneyhunter/policy.py`, with shared caps and representative rule sets in config. These are not personal balances or private promotion thresholds. Invalid/unavailable tier data stays at starter index 0. No private-app change or automatic promotion was made.
- Starter **Strong estimated CHECK**: £8 net AND 40% ROI; **Worth Reviewing / MANUAL CHECK**: £10 net AND 20% ROI when Strong fails. Both require known landed delivery, five independent sellers with two supporting the low, exact matching, online eligibility and resolved acquisition identity. Neither is verified BUY or a measured fast mover.
- Above the actual cap, discovery is **WATCH ONLY**, never either purchase signal. Starter research ceiling £150, purchase cap unchanged £60. The ceiling scales with the public configured cap, not a guessed account balance. Affordable/above-budget research have separate 35/15 candidate slots and 4/2 new query budgets.
- New real acquisition source: existing separately authorised official eBay Browse `/buy/browse/v1/item_summary/search`, FIXED_PRICE, NEW, GB and GBP. One rotating exact-product acquisition query per scan, at most once per product/hour; at most three distinct-seller cheapest shipped listings per query. Retains one hour/max60 offers, with source/query/observed dates and fixed shipping. Queries rotate across supported identities found in the acquisition feed; this is not a claim to search all eBay inventory. Shared 401/403/429 pause marker prevents retries/bypass. No browser/captcha path is used for eBay candidate status; a recent API observation is not a checkout stock guarantee. Expired observations cannot route.
- Exact acquisition listing and seller are removed from that candidate's comparators. Other real cheap competition stays. Stock, effective checkout prices, coupons and authenticity still need manual checking.
- Broader deterministic identity support is initially NEW Sony WH1000XM4/WH1000XM5 plus explicit Black/Silver/Blue colour, with model/colour/accessory/condition rejection. Missing variants are not guessed. Refurbished/outlet, fragrance and tool sources are **not connected by this change**; their condition/pack/warranty/authenticity evidence needs separate adapters. No paid provider, signup, fake sold observation or commercial catalogue redistribution.
- Official API field/filter reference: https://developer.ebay.com/api-docs/buy/static/ref-buy-browse-filters.html ; https://developer.ebay.com/api-docs/buy/browse/types/gct:ItemSummary . Shipping is the quoted fixed cost, not a guarantee for every destination. Acquisition observations never become sold comps.

### Capital-quality refinement after owner caution against blanket lower thresholds

Manual review is **informational only**, not an automatic purchase recommendation. £10 net/20% ROI are necessary but insufficient: moderate comparator confidence (not wide-spread), at least three independent low-price supporting sellers, plus a 10% lower resale-price scenario that still leaves **£5 net AND 10% ROI** are required. The stress scenario is a house risk buffer, not an empirically calibrated forecast, and does not establish velocity or guarantee losses are bounded. This compensates for lower nominal ROI with stronger price support/downside checks; Strong 40% starter policy remains unchanged. Actual account surcharges, advertised promotion fees and checkout charges still require checking. Fee basis: official UK business seller rate card https://www.ebay.co.uk/help/selling/fees-credits-invoices/store-fees?id=4809 (search checked 7 November 2026), category FVF + 0.35% regulatory + per-order fee, with 20% VAT on fees conservatively included.

Acquisition searches explicitly use documented `sellerAccountTypes:{BUSINESS}` to avoid treating unknown private-seller Buyer Protection charges as zero. This is business-seller sourcing, not a claim to cover private underpriced listings yet. **Business-only acquisition results never replace all-seller competitor snapshots**: cheaper private or discounted competition remains in valuation. No outlet/refurb feed or private-seller checkout-fee model is falsely advertised as connected.
