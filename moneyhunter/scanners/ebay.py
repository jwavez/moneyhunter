"""eBay Browse API (active listings) for competition checks. Needs EBAY_CLIENT_ID and
EBAY_CLIENT_SECRET (free developer keys). Skipped when keys are missing.
Note: Browse returns ACTIVE listings only, not sold prices [S]."""
import base64, json, os, statistics, time, urllib.parse, urllib.request

def available() -> bool:
    return bool(os.getenv("EBAY_CLIENT_ID") and os.getenv("EBAY_CLIENT_SECRET"))

_token = None
_token_expires = 0.0
def _auth() -> str:
    global _token, _token_expires
    if _token and time.monotonic() < _token_expires: return _token
    cred = base64.b64encode(f"{os.environ['EBAY_CLIENT_ID']}:{os.environ['EBAY_CLIENT_SECRET']}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
    req = urllib.request.Request("https://api.ebay.com/identity/v1/oauth2/token", data=data,
                                 headers={"Authorization": "Basic " + cred, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
        _token = data["access_token"]
        _token_expires = time.monotonic() + max(0, int(data.get("expires_in", 7200)) - 60)
    return _token

def active_stats(query: str) -> dict:
    q = urllib.parse.urlencode({"q": query, "limit": 50, "filter": "buyingOptions:{FIXED_PRICE},itemLocationCountry:GB"})
    req = urllib.request.Request("https://api.ebay.com/buy/browse/v1/item_summary/search?" + q,
                                 headers={"Authorization": "Bearer " + _auth(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"})
    with urllib.request.urlopen(req, timeout=20) as r:
        js = json.load(r)
    prices = [float(i["price"]["value"]) for i in js.get("itemSummaries", []) if i.get("price", {}).get("currency") == "GBP"]
    return {"active": js.get("total", 0), "median_ask": statistics.median(prices) if prices else None}


# ---- Live active-listing comps (used only when a stored sold comp is stale) ----
INSIGHTS_SCOPE = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"
ASK_HAIRCUT = 0.95      # asking prices sit above sale prices; take 5% off [H]
MIN_ACTIVE = 5          # need at least this many strictly-matched listings

def insights_available() -> bool:
    """True only if eBay granted Marketplace Insights (sold data) to this keyset. Never logs secrets."""
    cred = base64.b64encode(f"{os.environ['EBAY_CLIENT_ID']}:{os.environ['EBAY_CLIENT_SECRET']}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": INSIGHTS_SCOPE}).encode()
    req = urllib.request.Request("https://api.ebay.com/identity/v1/oauth2/token", data=data,
                                 headers={"Authorization": "Basic " + cred, "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return "access_token" in json.load(r)
    except Exception:
        return False

def _pct(xs, p):
    xs = sorted(xs); k = (len(xs) - 1) * p; f = int(k)
    return xs[f] if f + 1 >= len(xs) else xs[f] + (xs[f + 1] - xs[f]) * (k - f)

def search_new_gb(query: str, limit: int = 100) -> list:
    q = urllib.parse.urlencode({"q": query, "limit": limit,
                                "filter": "buyingOptions:{FIXED_PRICE},itemLocationCountry:GB,deliveryCountry:GB,conditionIds:{1000},priceCurrency:GBP"})
    req = urllib.request.Request("https://api.ebay.com/buy/browse/v1/item_summary/search?" + q,
                                 headers={"Authorization": "Bearer " + _auth(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"})
    with urllib.request.urlopen(req, timeout=20) as r:
        js = json.load(r)
    return [{"title": i.get("title", ""), "price": float(i["price"]["value"])}
            for i in js.get("itemSummaries", []) if i.get("price", {}).get("currency") == "GBP"]

def active_comp(comp, items: list, check, today=None):
    """Conservative comp from active asks. Strict matching (check) is applied to every listing title.
    Returns a new Comp or None. sold_90d stays None, so it can never pass the sold-comps gate (no grade A)."""
    import datetime as dt, dataclasses
    prices = [it["price"] for it in items if it["price"] > 0 and check(it["title"], "", comp) == ""]
    if len(prices) >= 3:   # drop likely fakes/errors (way under) and collabs/rarities (way over) [H]
        med = statistics.median(prices); prices = [p for p in prices if 0.6 * med <= p <= 1.8 * med]
    if len(prices) < MIN_ACTIVE: return None
    p25, p50 = _pct(prices, 0.25), _pct(prices, 0.50)
    low = round(min(p25 * ASK_HAIRCUT, comp.low), 2)
    high = round(max(low, min(p50 * ASK_HAIRCUT, comp.high)), 2)
    return dataclasses.replace(comp, low=low, high=high,
        evidence=f"{len(prices)} matched new UK listings, 25th pct ask £{p25:.2f} (ACTIVE asks, not sold)",
        source=f"eBay UK active listings (live) {(today or dt.date.today()).isoformat()}",
        sold_90d=None, sell_through=None, evidence_type="active_ask", days_to_sell=None)


def active_items(query: str, business_only: bool = False) -> dict:
    """Documented Browse search of current NEW UK offers. Never a sold-data call.

    Do not use this endpoint to retry challenged completed-item pages. It is the
    application's separately authorised active competition integration only.
    No retry/proxy fallback; permission and rate-limit failures are visible upstream.
    """
    filters = "buyingOptions:{FIXED_PRICE},itemLocationCountry:GB,deliveryCountry:GB,conditionIds:{1000},priceCurrency:GBP"
    if business_only: filters += ",sellerAccountTypes:{BUSINESS}"
    q = urllib.parse.urlencode({"q":query,"limit":50,"filter":filters})
    req = urllib.request.Request("https://api.ebay.com/buy/browse/v1/item_summary/search?" + q,
        headers={"Authorization": "Bearer " + _auth(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)
