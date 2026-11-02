"""Fee and cost engine. Rates [S] checked 2 Nov 2026:
- eBay UK private: no final value fee (ebay.co.uk help 4822)
- eBay UK business: category FVF on item+postage, +£0.30 (<=£10) / £0.40 (>£10) per order, +0.35% regulatory (help 4809)
- Vinted: no seller fee (vinted.co.uk/pricelist)
- Depop UK: 2.9% + £0.30 processing on item+postage (Depop help 360001791127)
- StockX L1: 9% (min £4.50) + 3% processing, £4 UK seller shipping
"""
from dataclasses import dataclass

EBAY_BUSINESS_FVF = {  # [S] eBay UK business seller rate card (subset)
    "trainers": [(100, 0.119), (None, 0.07)],   # 11.9%, 7% if price >= £100 (whole item)
    "sportswear": [(None, 0.119)],
    "lego": [(None, 0.109)],
    "fragrance": [(None, 0.109)],
    "gaming": [(None, 0.099)],                  # video games & accessories; consoles differ
    "tools": [(750, 0.069), (None, 0.03)],      # power tools 6.9% to £750 then 3%
    "default": [(None, 0.129)],                 # conservative fallback
}

def ebay_business_fee(price: float, category: str, postage_charged: float = 0.0) -> float:
    total = price + postage_charged
    bands = EBAY_BUSINESS_FVF.get(category, EBAY_BUSINESS_FVF["default"])
    if category == "trainers":
        pct = 0.07 if price >= 100 else 0.119
        fvf = total * pct
    else:
        fvf, prev = 0.0, 0.0
        for cap, pct in bands:
            top = total if cap is None else min(total, cap)
            if top > prev:
                fvf += (top - prev) * pct
            if cap is None or total <= cap:
                break
            prev = cap
    per_order = 0.30 if total <= 10 else 0.40
    return round(fvf + per_order + total * 0.0035, 2)

def platform_fee(platform: str, price: float, category: str = "default", postage_charged: float = 0.0) -> float:
    if platform == "ebay_private" or platform == "vinted" or platform == "fb":
        return 0.0
    if platform == "ebay_business":
        return ebay_business_fee(price, category, postage_charged)
    if platform == "depop":
        return round((price + postage_charged) * 0.029 + 0.30, 2)
    if platform == "stockx":
        return round(max(4.50, price * 0.09) + price * 0.03 + 4.0, 2)
    raise ValueError(f"unknown platform {platform}")

@dataclass
class CostBreakdown:
    sale_price: float
    platform_fee: float
    postage: float
    packaging: float
    returns_allowance: float
    buy_cost: float
    net: float

def net_profit(sale_price: float, buy_cost: float, platform: str, category: str,
               postage: float, packaging: float, returns_pct: float) -> CostBreakdown:
    fee = platform_fee(platform, sale_price, category)
    post = 0.0 if platform == "vinted" else postage   # Vinted buyer pays postage [S]
    ret = sale_price * returns_pct
    net = sale_price - fee - post - packaging - ret - buy_cost
    return CostBreakdown(sale_price, fee, post, packaging, round(ret, 2), buy_cost, round(net, 2))
