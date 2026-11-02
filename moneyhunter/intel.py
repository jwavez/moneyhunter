"""Deal intelligence that needs no paid API: retailer reliability, fake risk, cashback hint, price history.
All ratings are house guidance [H] unless marked [S]."""
import re
from .matching import norm, has

# [H] Well-known UK retailers that sell new stock directly and handle returns under the Consumer Contracts Regs.
TRUSTED = {"amazon", "argos", "currys", "very", "jd sports", "jd", "john lewis", "smyths", "smyths toys", "game", "box",
           "screwfix", "toolstation", "the fragrance shop", "fragrance shop", "boots", "superdrug", "the perfume shop",
           "sports direct", "office", "schuh", "footasylum", "size?", "end.", "adidas", "nike", "lego", "zavvi",
           "the entertainer", "tesco", "asda", "sainsburys", "very.co.uk", "ao", "ao.com", "costco", "selfridges",
           "next", "marks & spencer", "m&s", "debenhams", "jacamo", "wex", "ebuyer", "scan", "ccl", "hughes", "richer sounds",
           "decathlon", "b&q", "wickes", "homebase", "ffx", "itsco", "toolstop", "d&m tools", "base", "shopto", "coolshop"}
MARKETPLACE = ("ebay", "aliexpress", "temu", "wish", "onbuy", "fruugo", "facebook", "vinted", "depop", "gumtree",
               "sold by", "marketplace", "third party", "3rd party", "fulfilled by")
FAKE_PRONE = {"trainers": "high", "sportswear": "high", "fragrance": "high", "tech": "medium", "lego": "low",
              "tools": "medium", "gaming": "low"}
CASHBACK_LIKELY = {"argos", "currys", "very", "jd sports", "john lewis", "boots", "superdrug", "the fragrance shop",
                   "the perfume shop", "zavvi", "ao", "ao.com", "schuh", "office", "footasylum", "adidas", "nike", "next",
                   "selfridges", "sports direct", "decathlon", "wickes", "b&q", "homebase", "ebuyer", "lego"}

def retailer(merchant: str, title: str = "") -> dict:
    m = (merchant or "").strip().lower()
    t = norm(title + " " + merchant)
    if any(has(t, k) for k in MARKETPLACE) or "marketplace" in m:
        return {"rating": "caution", "label": "⚠️ Marketplace/third-party seller: check seller rating and returns"}
    if m in TRUSTED or m.split(" ")[0] in TRUSTED:
        return {"rating": "trusted", "label": "✅ Major UK retailer (14-day returns online)"}
    if not m:
        return {"rating": "unknown", "label": "❔ Retailer unknown: check returns policy"}
    return {"rating": "unknown", "label": f"❔ {merchant}: smaller retailer, check reviews and returns"}

def fake_risk(category: str, merchant: str, title: str = "") -> dict:
    base = FAKE_PRONE.get(category, "medium")
    r = retailer(merchant, title)["rating"]
    level = "high" if (base == "high" and r != "trusted") or r == "caution" else ("medium" if base == "high" else base)
    tip = {"trainers": "Keep the receipt and box; list with receipt photo (buyers pay more for proof).",
           "fragrance": "Keep the receipt and sealed cellophane; never list testers as new.",
           "sportswear": "Keep tags and receipt.", "tech": "Keep receipt and serial number; check it is UK stock."}.get(category, "Keep the receipt.")
    icon = {"high": "🔴", "medium": "🟠", "low": "🟢"}[level]
    return {"level": level, "label": f"{icon} {level.title()} fake/authenticity risk · {tip}"}

def cashback(merchant: str) -> str:
    m = (merchant or "").strip().lower()
    if m in CASHBACK_LIKELY:
        return f"Check TopCashback/Quidco for {merchant} before buying (rates change daily; not counted in profit)."
    if m == "amazon":
        return "Amazon: little or no cashback. Check the CamelCamelCamel price history link."
    return ""

def price_history(title_key: str, price: float, prices: dict) -> str:
    p = prices.get(title_key)
    if not p: return "First time seen by MONEYHUNTER"
    low = p.get("low", p["price"])
    if price <= low: return f"Lowest seen by MONEYHUNTER (since {p['ts'][:10]})"
    return f"Seen lower: £{low:.2f} (tracking since {p['ts'][:10]})"

def camel_url(url: str, title: str) -> str:
    import urllib.parse
    return "https://uk.camelcamelcamel.com/search?" + urllib.parse.urlencode({"sq": title[:80]})
