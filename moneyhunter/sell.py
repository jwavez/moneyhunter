"""Where to sell, per category. [H] house routing for fast (<=10 day) turnover; fees from fees.py.
Community-safe: platform advice only."""
import urllib.parse

FAST_DAYS = 10                                   # [H] fast-mover threshold (matches T1 max days-to-sell)
VINTED_MAX = 80.0                                # [H] Vinted first for everyday pairs under ~£80
HOLD_TIP = "Aim ≤10 days: cut price + cross-list D7, quick-sale D10"

ROUTES = {
    "trainers": {"preferred": "Vinted (only if commercial activity permitted)", "backup": "eBay (limited or £80+) · Depop (streetwear)",
                 "floor": "No verified cash floor; best offer is not a floor", "note": "Size must match the listing exactly"},
    "sportswear": {"preferred": "Vinted", "backup": "Depop (streetwear) · eBay", "floor": "No verified cash floor; best offer is not a floor",
                   "note": "Condition photos, exact size"},
    "lego": {"preferred": "eBay (search by set number)", "backup": "eBay best offer", "floor": "No verified cash floor; best offer is not a floor",
             "note": "Sealed sets only. Skip slow retired 'maybe' sets; sell gift sets before Christmas posting dates"},
    "gaming": {"preferred": "eBay", "backup": "eBay best offer", "floor": "CeX / musicMagpie: exact tested cash quote required",
               "note": "Sealed or boxed only"},
    "tools": {"preferred": "eBay (model number in title)", "backup": "eBay delivered listing (model and contents exact)",
              "floor": "No verified cash floor; best offer is not a floor", "note": "Never mix body-only and kit prices"},
    "fragrance": {"preferred": "eBay (exact size in title)", "backup": "eBay best offer", "floor": "No verified cash floor; best offer is not a floor",
                  "note": "Gift peaks: Valentine's, Mother's Day, Father's Day (see the seasonal calendar)"},
    "tech": {"preferred": "eBay", "backup": "eBay best offer", "floor": "CeX: exact tested cash quote required", "note": "Sealed only; no phones"},
}
DEFAULT = {"preferred": "eBay", "backup": "eBay best offer", "floor": "No verified cash floor; best offer is not a floor", "note": ""}
CLOTHING = ("trainers", "sportswear")
CEX_FLOOR = ("gaming", "tech")

def route(category: str, price: float = None) -> dict:
    r = dict(ROUTES.get(category, DEFAULT))
    if category == "trainers" and price is not None and price >= VINTED_MAX:
        r["preferred"], r["backup"] = "eBay (£80+ / limited)", "Vinted · Depop (streetwear)"
    return r

def platforms_text(category: str, price: float = None) -> str:
    r = route(category, price)
    return f"{r['preferred']} → {r['backup']} → floor: {r['floor']}"

def sell_on_value(category: str, price: float = None) -> str:
    r = route(category, price)
    s = f"**{r['preferred']}**\nBackup: {r['backup']}\nFloor: {r['floor']}"
    return s[:1024]

def is_fast(category: str, days_to_sell) -> bool:
    return days_to_sell is not None and 0 <= days_to_sell <= FAST_DAYS

def fast_route(grade: str, category: str, days_to_sell) -> bool:
    """Copy to #fast-movers only for A/B grades that should sell in <=10 days."""
    return grade in ("A", "B") and is_fast(category, days_to_sell)

def dts_label(category: str, days_to_sell) -> str:
    if days_to_sell is not None: base = f"~{days_to_sell:g} days"
    else: base = "No measured data yet"
    return ("⚡ FAST · " if is_fast(category, days_to_sell) else "") + base

def cex_url(q: str) -> str:
    return "https://uk.webuy.com/search?" + urllib.parse.urlencode({"stext": q})

def guide_embed(category: str, label: str) -> dict:
    r = route(category)
    lines = [f"**Sell first on:** {r['preferred']}", f"**Backup:** {r['backup']}", f"**Floor exit:** {r['floor']}"]
    if r["note"]: lines.append(f"**Tip:** {r['note']}")
    lines += ["", f"⏱️ {HOLD_TIP}.", "⚡ **FAST** badge = observed median ≤10 days, not a future-sale guarantee.",
              "👀 WATCH cards are homework, not buy signals. BUY requires every evidence gate; VERIFY is not permission to buy."]
    return {"title": f"🧭 Where to sell · {label}", "color": 0x10B981, "description": "\n".join(lines)[:4096],
            "footer": {"text": "MONEYHUNTER · house guidance, not guarantees"}}
