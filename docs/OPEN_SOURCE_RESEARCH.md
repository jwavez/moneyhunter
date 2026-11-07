# Source-led acquisition and capture upgrades — 7 November 2026

## What was actually checked

Read pinned source and licence files through GitHub, without installing/executing
third-party programs. Recent activity is not proof of production quality. The two
large projects below are established; the two tiny eBay tools are experimental.
This implementation is original code using general design ideas, not copied
source. No external dependencies, commercial data dumps or logos were imported.

| Project / pinned revision | Licence / maturity | Actual source finding | Decision |
| --- | --- | --- | --- |
| [changedetection.io](https://github.com/dgtlmoon/changedetection.io/tree/09619ffddb40300e6c09374a4f6aa9af8bab0c3d), active 6 November, ~35k stars | Apache-2.0, NOTICE reviewed | [`filtered_price.py`](https://github.com/dgtlmoon/changedetection.io/blob/09619ffddb40300e6c09374a4f6aa9af8bab0c3d/changedetectionio/processors/restock_diff/filtered_price.py) and [its fixtures](https://github.com/dgtlmoon/changedetection.io/blob/09619ffddb40300e6c09374a4f6aa9af8bab0c3d/changedetectionio/tests/unit/test_restock_filtered_price.py) reject multiple distinct currency prices rather than silently selecting a was/RRP price | Adopted ambiguity principle, independently implemented for GBP. Did not adopt browser/proxy or disabled TLS-verification paths. |
| [RSS-Bridge](https://github.com/RSS-Bridge/rss-bridge/tree/cb19baea75d795a615962fbc434d7f529a44151e), active 3 November, ~9k stars | Unlicense | [`CacheMiddleware.php`](https://github.com/RSS-Bridge/rss-bridge/blob/cb19baea75d795a615962fbc434d7f529a44151e/middlewares/CacheMiddleware.php) handles conditional 304 and caches errors. [`HotUKDealsBridge.php`](https://github.com/RSS-Bridge/rss-bridge/blob/cb19baea75d795a615962fbc434d7f529a44151e/bridges/HotUKDealsBridge.php) offers newest/local/expired filters but inherits an HTML scraper | Adopted conditional-fetch and failure-cooldown concepts for the already-used public RSS endpoints. Did NOT deploy the HTML bridge or treat its licence as permission to scrape any website. |
| [YarSav1/listing-monitor](https://github.com/YarSav1/listing-monitor/tree/3e27051af81df3831131d5d16373f8afa329b3b4), updated 3 October, tiny project | MIT, copyright YarSav1 2026 | [`sources.py`](https://github.com/YarSav1/listing-monitor/blob/3e27051af81df3831131d5d16373f8afa329b3b4/listing_monitor/sources.py) uses documented OAuth + Browse, expires tokens with a safety margin; [`store.py`](https://github.com/YarSav1/listing-monitor/blob/3e27051af81df3831131d5d16373f8afa329b3b4/listing_monitor/store.py) persists `(source, query, item_id)` identity | Adopted expiring-token and source/query/item identity concepts. Rejected its CSS/Playwright/browser-impersonation alternatives. No sold-history capability found. |
| [jtstothard/ebay-sniper](https://github.com/jtstothard/ebay-sniper/tree/894789db89fab0560c0c52cc59ec61ee63c6d7c7), updated 31 October, tiny project | MIT, copyright Jay Stothard 2025 | [`ebay_client.py`](https://github.com/jtstothard/ebay-sniper/blob/894789db89fab0560c0c52cc59ec61ee63c6d7c7/src/sniper/core/ebay_client.py) uses Browse for auctions. [`LIMITATIONS.md`](https://github.com/jtstothard/ebay-sniper/blob/894789db89fab0560c0c52cc59ec61ee63c6d7c7/docs/LIMITATIONS.md) openly acknowledges stubbed bidding; persistent scheduler requires an always-running service | Adopted explicit capability/unknown-state design, not bidding code, stub success or a production shell daemon. Not a sold-data source. |
| [timotheus/ebaysdk-python](https://github.com/timotheus/ebaysdk-python/tree/7ef8ba432332657258038ce86c6da2b02da0681f), last push 2023 | CDDL-1.0 in source and LICENSE, dormant rather than necessarily GitHub-archived | [`finding/__init__.py`](https://github.com/timotheus/ebaysdk-python/blob/7ef8ba432332657258038ce86c6da2b02da0681f/ebaysdk/finding/__init__.py) targets old `svcs.ebay.com`; [`samples/finding.py`](https://github.com/timotheus/ebaysdk-python/blob/7ef8ba432332657258038ce86c6da2b02da0681f/samples/finding.py) executes Finding calls | Rejected as a current sold-data route. eBay retired ALL Finding/Shopping calls on **4 February 2025**, including `findCompletedItems`. No obsolete endpoint was invoked. |
| [cyberkirbi/bb-ebay-arbitrage](https://github.com/cyberkirbi/bb-ebay-arbitrage/tree/be3d0ec63e71dfb8d7a3e758a236248a5bb8ee1d), updated July, tiny project | No licence found: no copying permission established | [`ebayprice.py`](https://github.com/cyberkirbi/bb-ebay-arbitrage/blob/be3d0ec63e71dfb8d7a3e758a236248a5bb8ee1d/ebayprice.py#L298-L363) takes a median of ACTIVE Browse item prices, without shipping, then [`potential_profit`](https://github.com/cyberkirbi/bb-ebay-arbitrage/blob/be3d0ec63e71dfb8d7a3e758a236248a5bb8ee1d/ebayprice.py#L398-L408) subtracts retail item price | Rejected code and the implied resale/profit interpretation. Active median minus retail is not realised net profit. Its API does not fix sold-history access. |

## Implemented improvements

1. **Automatic indicative asking research** for identifiable LEGO set numbers and
   sufficiently specific gaming platform/title queries, including unmatched offers.
   Existing authorised official eBay Browse only: six queries/run, six-hour durable
   snapshots, absent/oldest query rotation, title/condition/GB/edition/variant guards,
   exact known GBP fixed postage, duplicate and ended/multi-variant rejection.
   Preserve genuine price extremes; report wide dispersion instead of deleting low
   observations to manufacture margin. Store observation time and at most three
   source links per snapshot. No seller identities/address data are retained.
2. **Independent capture in the existing Worker/KV**, target every ten minutes:
   four existing public RSS feeds (LEGO, Switch, PlayStation, Xbox), at most twenty
   entries/feed, 512KiB/feed, 300 retained offers, seven-day age bound. Exactly one
   bounded KV write/invocation. Uses ETag/Last-Modified; 403/access challenges pause
   a source until operator review, 429 gets a one-hour cooldown. No proxies, retailer
   HTML fallback, new service, account or outbound Discord delivery.
   This is durable intake, **not** a replacement grading engine. It cannot guarantee
   a feed entry is a live retailer offer. Publication, first/last observation and
   successful grading-scan clocks remain separate. The scanner merges previously
   captured entries; a current direct RSS offer always wins a price conflict.
3. **Usable research UI**: retained capture candidates, hypothetical cost break-even,
   fresh asking ranges only when available, explicit missing-sold/stock/delivery
   blockers and stale-scan warning. Changed acquisition prices discard stale
   research-row context. The public capture endpoint has no write method and exposes
   no private ledger, credentials, submissions or internal cache rows/validators.
4. **Safe production-key diagnostic**: manual scan defaults to `dry_run=true`;
   hard no-send, zero alert budget, no state publication, three-day research artifact.
   Scheduled normal operation retains existing publication/delivery behaviour.
5. Fixed the first-GBP fallback bug (`was £80 now £40` is now ambiguous, not £80)
   and OAuth token reuse past its actual expiry. A real RSS capture also exposed
   game-code storefront leads whose titles omit "digital"; these are now excluded
   conservatively from physical research (explicit hardware is handled separately).

## Boundaries: useful context is not sold pricing

`asking_catalog` and review `ask_context` never enter `Comp`, `target`, floor,
velocity or grading. Ask snapshots expire independently after six hours. A current
listed price is not a realised sale or a forecast; buyer-only fees/regional
surcharges may be additional. No haircut converts asks to "sold" evidence. No A/B
guard or starter cap was lowered. No invented sample entered production evidence.

403/401/429 Browse failures persist `browse-blocked` in public operational state and
stop further lookups pending operator review. Do not clear that marker to dodge an
access restriction. RSS source `paused` markers have the same no-bypass policy.

The four reviewed active projects provided useful engineering ideas, **not** a
new free competitive sold-history entitlement. Official sources:

- [eBay API decommission table](https://developer.ebay.com/develop/api-deprecation-status): Finding/Shopping **2025/02/04**, not a working current `findCompletedItems` route.
- [Browse overview](https://developer.ebay.com/api-docs/buy/api-browse.html) and [shipping option definition](https://developer.ebay.com/api-docs/buy/browse/types/gct:ShippingOptionSummary): current purchasable offers; fixed vs calculated postage.
- [Product Research](https://www.ebay.com/help/selling/selling-tools/product-research?id=4853): free Seller Hub research UI. No supported competitive automated CSV export was established; do not promise one.
- [Marketplace Insights](https://developer.ebay.com/api-docs/buy/marketplace-insights/overview.html): restricted access, not conferred by Browse production keys.
- [Cloudflare Cron](https://developers.cloudflare.com/workers/configuration/cron-triggers/), [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [KV limits](https://developers.cloudflare.com/kv/platform/limits/), [pricing](https://developers.cloudflare.com/workers/platform/pricing/): fits published Free allowances at target cadence (144 requests, 144 KV writes/day; account-wide usage is shared). Free CPU is 10ms/invocation; failed capture must remain visible, not hidden as scanner success. Cron propagation may take fifteen minutes; exact execution times are not guaranteed.

For genuinely actionable sold-valued recommendations, import directly verified
exact-condition/variant records through the existing reviewed evidence schema,
then current exact retailer offers. User-authorised Product Research review or an
approved licensed feed are legitimate acquisition routes. Cash exits and observed
velocity must be sourced too before A. Clearing a browser challenge or having free
software does not itself authorise bulk scraping or create those data rights.
