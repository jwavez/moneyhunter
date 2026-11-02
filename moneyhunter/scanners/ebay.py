"""eBay Browse API (active listings) for competition checks. Needs EBAY_CLIENT_ID and
EBAY_CLIENT_SECRET (free developer keys). Skipped when keys are missing.
Note: Browse returns ACTIVE listings only, not sold prices [S]."""
import base64, json, os, statistics, urllib.parse, urllib.request

def available() -> bool:
    return bool(os.getenv("EBAY_CLIENT_ID") and os.getenv("EBAY_CLIENT_SECRET"))

_token = None
def _auth() -> str:
    global _token
    if _token: return _token
    cred = base64.b64encode(f"{os.environ['EBAY_CLIENT_ID']}:{os.environ['EBAY_CLIENT_SECRET']}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
    req = urllib.request.Request("https://api.ebay.com/identity/v1/oauth2/token", data=data,
                                 headers={"Authorization": "Basic " + cred, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        _token = json.load(r)["access_token"]
    return _token

def active_stats(query: str) -> dict:
    q = urllib.parse.urlencode({"q": query, "limit": 50, "filter": "buyingOptions:{FIXED_PRICE},itemLocationCountry:GB"})
    req = urllib.request.Request("https://api.ebay.com/buy/browse/v1/item_summary/search?" + q,
                                 headers={"Authorization": "Bearer " + _auth(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"})
    with urllib.request.urlopen(req, timeout=20) as r:
        js = json.load(r)
    prices = [float(i["price"]["value"]) for i in js.get("itemSummaries", []) if i.get("price", {}).get("currency") == "GBP"]
    return {"active": js.get("total", 0), "median_ask": statistics.median(prices) if prices else None}
