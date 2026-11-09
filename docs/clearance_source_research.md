# Clearance / outlet source research (Task 14 Phase A)

**Date:** 2026-11-09 (Europe/London)  
**Scope:** Research only. No code. No signups. No paid services. No HTML scraping of bot-blocking sites.  
**Browse budget:** **0** live eBay Browse API calls were made for this research (shared app-wide `DAILY_LIMIT=800` in `moneyhunter/research_budget.py`). Findings below come from official public docs / lightweight `robots.txt` probes only.

**Viability rule:** reject a source if it fails **2+** of: (1) Accessible, (2) Legal, (3) Free/≤£50/mo, (4) Structured, (5) Identity-rich, (6) Clearance signal.

**Not assumed:** No third-party aggregator named “ReefAPI” (or similar) was treated as existing. A web search for a free UK clearance aggregator of that kind was not used as a substitute for official retailer/network docs; none was adopted as a recommendation without verification.

---

## Summary table

| Source | Access method | Legal | Cost | Format | Identity | Clearance signal | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Argos clearance | No public retailer API found. Affiliate product data via **CJ Affiliate** (daily product feed / Product Search API after publisher + advertiser approval). Site `robots.txt` returned **HTTP 403 Access Denied** to a lightweight probe — not a usable public feed. | CJ publisher programme + Argos T&Cs after approval; site scraping would fight bot controls → refuse scrape | Free to join CJ; £0/mo within ≤£50 | CJ feed / GraphQL Product Search (structured) once approved | Typically SKU / product id + title; EAN depends on advertiser feed columns (verify after join) | Sale/discount fields possible in CJ shopping feeds; **Argos-specific clearance/was_price not verified pre-join** | **needs verification** (viable *if* approved + feed exposes RRP/sale; not viable as public API today) |
| Currys clearance (site) | Public HTML clearance page only (`currys.co.uk/clearance`). `robots.txt` probe **403**/blocked. | Scraping blocked pages / ToS anti-bot → refuse | N/A | HTML | Page titles only | Clearance category on site | **not viable** (accessibility + legal for scrape) |
| Currys via **Awin** product feed | Documented daily (advanced multi-day) **Awin product datafeed** for approved affiliates ([Currys Awin terms](https://ui.awin.com/merchant-profile-terms/1599); [Create-a-Feed](https://help.awin.com/developers/docs/downloading-feeds-using-create-a-feed)) | Awin publisher + Currys programme terms (PPC brand restrictions, etc.) | Free Awin signup; £0/mo | CSV/TSV (structured) | Product ID, name, merchant category; brand/EAN when merchant supplies columns | Awin columns include `search_price` + optional **`rrp_price`** / prior price ([feed column docs](https://cdn.document360.io/ec9ead62-8ecc-46ef-aac7-9b0a9081b40b/Images/Documentation/PM-FeedColumnDescriptions(1).pdf)); filter `rrp_price` vs price for ≥40% off; category keywords for clearance | **viable** (subject to affiliate approval + confirming Currys feed populates `rrp_price` / clearance categories) |
| Currys Outlet on **eBay** (invert Browse) | Already-connected **Browse API** `item_summary/search` with `filter=sellers:{currys}` (public store [ebay.co.uk/usr/currys](https://www.ebay.co.uk/usr/currys)) + UK marketplace + `conditionIds` / `price` / `deliveryCountry:GB` ([Buy API Field Filters](https://developer.ebay.com/api-docs/buy/static/ref-buy-browse-filters.html)) | Existing eBay Developers / Browse licence already used by moneyhunter for comps | Within existing Browse budget (app cap 800/day) | JSON | Brand/MPN/GTIN when present on item; title + seller SKU variable | Response may include **`marketingPrice.originalPrice` / `discountPercentage` / `discountAmount`** when seller discount applies ([ItemSummary.marketingPrice](https://developer.ebay.com/api-docs/buy/browse/types/gct:ItemSummary)). **Cannot filter by discount % in the request** — must fetch then post-filter. Seller “was” ≠ manufacturer RRP | **viable** (best zero-signup path; clearance signal conditional) |
| Amazon Warehouse / Renewed | **Creators API** (PA-API successor) only via Amazon Associates ([Creators API docs](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction); [UK Associates](https://affiliate-program.amazon.co.uk/help/operating/policies/)) | Associates T&Cs; API for referred shopping, not raw warehouse dump | Free programme but **eligibility bar** | JSON via API | ASIN-rich | Warehouse/Renewed browse exists on site; API eligibility gated | **not viable** now (fails accessible *for this app*: needs Associates + **≥10 qualifying sales / 30 days** per marketplace) |
| Sports Direct / Flannels / USC | Affiliate via **Partnerize** (not Awin); product feed claimed by programme listings; no free public API found | Partnerize + merchant T&Cs after approval | Free to apply | Feed (verify format post-join) | Likely SKU/title; verify | Outlet merchandising on site; feed clearance fields **unverified** | **needs verification** |
| Very / Littlewoods | **Awin** programme + product feed ([Very Awin profile](https://ui.awin.com/merchant-profile/3090)) | Awin + Very terms | Free Awin | CSV via Create-a-Feed | Product IDs + attributes when provided | Awin `rrp_price` / search price pattern applies when merchant fills RRP | **viable** (same Awin path; fashion-heavy mix may be weaker for current identity lanes) |
| Costco UK | Membership retailer; affiliate mentions via third parties; **no official public product API/feed** verified | Membership / partner T&Cs; scrape refuse | Unknown / membership | N/A verified | N/A | Warehouse deals are membership-gated | **not viable** |
| Home Bargains / B&M | No official product feed/API found. Third-party scrapers exist → out of policy. B&M `robots.txt` reachable and disallows `/search` and `/*?` | Scrape refuse; no affiliate feed verified | N/A | N/A | N/A | In-store clearance culture; weak online structured clearance | **not viable** |
| eBay Outlet / eBay Deals (Browse only) | Browse filters: `price`, `priceCurrency`, `itemLocationCountry`, `conditionIds`, `sellers`, `buyingOptions`, `deliveryCountry`, etc. ([filters ref](https://developer.ebay.com/api-docs/buy/static/ref-buy-browse-filters.html)). **No** `discountPercentage` request filter | Existing Browse access | Shared 800/day | JSON | Variable | `marketingPrice` when present (post-filter ≥40%) | **viable** as acquisition tactic, not a true RRP-clearance catalogue |
| eBay **Deal API** | Documented Buy API ([Deal API](https://developer.ebay.com/api-docs/buy/static/api-deal.html)) | **Limited Release** — production needs EPN + Buy API application + contracts ([Buy APIs Requirements](https://developer.ebay.com/api-docs/buy/static/buy-requirements.html)) | Partner process; not free “flip a switch” | JSON | Deal/event items | Native deals/events | **not viable** for this app today (access gate) |
| ShopTo | **Awin** programme; daily-updated product feed noted on [ShopTo Awin profile](https://ui.awin.com/merchant-profile/2943) | Awin + ShopTo terms | Free Awin | CSV | Strong for games/tech SKUs when feed complete | RRP columns when populated; gaming/tech overlap with lanes | **viable** |
| Zavvi / The Hut (THG) | Awin programmes ([The Hut terms](https://ui.awin.com/merchant-profile-terms/2547); Zavvi packs mention feeds) | Awin + THG terms | Free Awin | CSV | Variable (entertainment/fashion skew) | RRP when populated | **viable** (secondary; category fit weaker than Currys/ShopTo for tools/LEGO/tech lanes) |
| **Awin network (general)** | Publisher **Create-a-Feed** URL download ([docs](https://help.awin.com/developers/docs/downloading-feeds-using-create-a-feed)); join free | Awin publisher policies | **£0** (≤£50) | CSV/TSV | Merchant-dependent | `rrp_price` / prior price fields in standard Awin column set | **viable** platform |
| **CJ Affiliate (general)** | Product feeds + GraphQL Product Search ([CJ APIs overview](https://junction.cj.com/article/cj-affiliates-apis-5-things-you-should-know)) | CJ policies | Free join | XML/API JSON | Merchant-dependent | Shopping feed sale fields when provided | **viable** platform (Argos lives here) |
| Rakuten / Webgains / other aggregators | Network product-feed exports after publisher join | Network T&Cs | Free–low | CSV/XML | Merchant-dependent | Merchant-dependent | **needs verification** per merchant; not researched merchant-by-merchant beyond Awin/CJ |
| Paid data aggregators / scrape APIs (Bright Data etc.) | Commercial scrape/API products | Often ToS-grey vs retailer | Typically **>£50/mo** | JSON | Varies | Varies | **not viable** under cost + legal criteria (and out of Phase A “no paid without approval”) |

---

## Viable sources — quirks

### 1) Awin retailer feeds (Currys primary; ShopTo / Very / THG secondary)

- **Auth:** Awin publisher account + per-merchant approval. No feed until Currys (etc.) accepts the site.
- **Access:** UI **Toolbox → Create-a-Feed** builds a download URL (CSV). Optional compression. Column picker includes pricing/RRP fields when the advertiser supplies them.
- **Rate limits:** Feed pulls are batch downloads, not per-item API hammering; still cache locally and refresh ≤ daily (Currys documents daily + optional advanced multi-refresh).
- **Clearance:** Prefer rows where `rrp_price` (or equivalent) is populated and `(rrp - search_price)/rrp ≥ 0.40`, and/or merchant category contains clearance/outlet. **Must verify** Currys’ live feed actually fills RRP for clearance SKUs after join — docs promise a datafeed with accurate pricing, not a guaranteed 40%+ slice.
- **Legal quirks:** Currys Awin terms restrict brand PPC and hard-coded stale creatives ([terms](https://ui.awin.com/merchant-profile-terms/1599)).
- **Identity:** Map feed product id / MPN / EAN columns into moneyhunter identity attrs; expect gaps → fail closed like HUKD.

### 2) eBay Browse API as acquisition (Currys seller / UK NEW / post-filter marketingPrice)

- **Auth:** Existing app credentials already used for competition asks.
- **Filters that work:** `sellers:{currys}`, `conditionIds:{1000}` (NEW), `price:[..X],priceCurrency:GBP`, `deliveryCountry:GB`, `buyingOptions:{FIXED_PRICE}`, `itemLocationCountry` (GB marketplace rules apply). See [filter reference](https://developer.ebay.com/api-docs/buy/static/ref-buy-browse-filters.html).
- **Clearance signal:** `itemSummaries[].marketingPrice.{originalPrice,discountPercentage,discountAmount}` when eBay returns a seller discount ([ItemSummary](https://developer.ebay.com/api-docs/buy/browse/types/gct:ItemSummary)). **There is no request filter for discount %** — every candidate page costs Browse calls from the **shared 800/day** research budget (`moneyhunter/research_budget.py`).
- **Risk:** Many listings omit `marketingPrice`; discount is often vs seller’s own was-price, not Argos/Currys shelf RRP; stock is contested; fees still apply when *reselling* but acquisition is eBay (fee stack changes strategy).
- **Deal API:** Exists but **Limited Release / partner approval** — not available as a drop-in for this bot ([requirements](https://developer.ebay.com/api-docs/buy/static/buy-requirements.html)).

### 3) CJ + Argos feed

- Argos programme is on **CJ** with a marketed daily product feed ([affiliate-toolkit / Affilitizer programme notes](https://www.affilitizer.com/programs/argos.co.uk)).
- Publisher Product Search API is structured, but **approval + Argos acceptance** required; clearance/was_price columns **not confirmed** without an approved feed sample.
- Direct site access is bot-hostile (403 on `robots.txt` probe).

---

## Sources rejected or blocked

- **Currys/Argos HTML clearance:** bot controls (403) → scrape refused.
- **Amazon Warehouse/Renewed API:** Creators API needs Associates + trailing sales volume — not met.
- **Costco UK / Home Bargains / B&M:** no verified free structured clearance feed; scrape out of policy.
- **eBay Deal API production:** partner gate.
- **Paid scrape APIs:** cost and ToS.

---

## Final recommendation

**Implement [Awin → Currys product feed] first, because** it is the only researched path that is simultaneously (a) officially documented as a structured affiliate datafeed, (b) free within ≤£50/mo, (c) identity-capable, and (d) has a standard **RRP vs search price** column model for detecting ≥40% off — which HUKD lacks. Currys’ category mix (computing, gaming, audio, appliances) overlaps moneyhunter lanes better than fashion-heavy feeds.

**Estimated implementation effort:** **medium** (Awin join + Currys approval wait + feed parser + identity mapping + clearance filter + scan wiring; no pricing-engine changes).

**Risk:** Currys may delay/deny affiliate approval; feed may omit `rrp_price` on the deepest clearance SKUs; stock accuracy lags; PPC/creative terms constrain promotion (less relevant if used only as acquisition research). If approval fails, **fall back to eBay Browse `sellers:{currys}` + `marketingPrice` post-filter** using the existing Browse budget (small effort, weaker RRP semantics, burns shared 800/day).

**Parallel zero-signup probe (optional, budget-aware):** at most a **handful** (≤5) Browse searches filtered to seller `currys` / UK NEW to measure how often `marketingPrice.discountPercentage ≥ 40` appears — each call counts against the shared 800/day research budget. **Not done in Phase A (0 calls).**

---

## Decision point (user chooses before Phase B)

1. **Signup (recommended):** Create/approve **Awin** publisher account and apply to **Currys** (then ShopTo). Proceed to Phase B feed ingest after approval + a sample feed confirming RRP/clearance fields.  
2. **Pay:** Only if (1) fails — evaluate a named paid catalogue API with written ToS and ≤£50/mo; none recommended from this research without a quote.  
3. **Pivot:** Stay on HUKD + use **eBay Browse acquisition** (Currys seller / marketingPrice post-filter) knowing discounts are seller-was, not true RRP clearance, and Browse budget is shared with competitor research.

**Phase B must not start until this decision is explicit.**
