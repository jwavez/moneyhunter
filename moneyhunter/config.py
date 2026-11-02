"""Settings. [S] = sourced (see README), [H] = house rule to tune."""
from dataclasses import dataclass

# ---- Tiers by bankroll [H] ----
@dataclass(frozen=True)
class Tier:
    name: str
    min_bankroll: float
    max_pct: float      # max cost per item as % of bankroll
    min_net: float      # min expected net profit, GBP
    min_roi: float      # min expected ROI %
    max_dts: int        # max days-to-sell
    max_items: int
    reinvest: int
    reserve_pct: float

TIERS = [
    Tier("T1 Scout", 0, 30, 8, 40, 10, 8, 100, 10),
    Tier("T2 Hustler", 500, 25, 12, 35, 14, 15, 100, 10),
    Tier("T3 Trader", 1000, 20, 15, 30, 14, 25, 90, 15),
    Tier("T4 Operator", 2500, 15, 20, 25, 21, 40, 80, 15),
    Tier("T5 Merchant", 5000, 12, 30, 25, 21, 60, 75, 20),
    Tier("T6 Tycoon", 10000, 10, 50, 20, 30, 100, 70, 20),
]

def tier_for(bankroll: float) -> Tier:
    t = TIERS[0]
    for x in TIERS:
        if bankroll >= x.min_bankroll:
            t = x
    return t

# ---- Gates [H] ----
MIN_SELL_THROUGH = 80.0
MIN_COMPS = 5
MIN_CONFIDENCE = 60.0
KELLY_FRACTION = 0.25

# ---- Outcome probabilities when uncalibrated [H] ----
P_STRETCH, P_TARGET, P_QUICK = 0.15, 0.60, 0.20   # remainder = floor exit
QUICK_FACTOR = 0.90          # quick-sale = 90% of target
UNVERIFIED_FLOOR_FACTOR = 0.50  # floor guess when no CeX/floor price known
PACKAGING = 0.50
RETURNS_ALLOWANCE = 0.03

# ---- Postage out [S] (royalmail.com, evri.com, InPost via lockerrules.co.uk; Nov 2026) ----
POSTAGE = {"inpost": 1.99, "evri": 2.62, "rm2": 4.40, "collect": 0.0}
DEFAULT_POSTAGE = "evri"
LARGE_POSTAGE = "rm2"   # used for boxes/tools

# ---- hotukdeals feeds (public RSS) mapped to target categories ----
HUKD = "https://www.hotukdeals.com/rss/"
FEEDS = {
    "trainers": ["tag/trainers", "tag/nike", "tag/adidas"],
    "lego": ["tag/lego"],
    "tools": ["tag/dewalt", "tag/makita"],
    "gaming": ["tag/nintendo-switch", "tag/playstation"],
    "fragrance": ["tag/perfume", "tag/aftershave"],
    "any": ["trending", "new"],
}

# Category keywords used to keep only target categories from the general feeds
CATEGORY_KEYWORDS = {
    "trainers": ["trainer", "samba", "air force", "gel-kayano", "sneaker", "air max", "dunk"],
    "lego": ["lego"],
    "tools": ["dewalt", "makita", "milwaukee", "body only", "tool only"],
    "gaming": ["controller", "switch", "ps5", "playstation", "xbox", "dualsense"],
    "fragrance": ["eau de parfum", "eau de toilette", "edp", "edt", "aftershave", "perfume"],
    "sportswear": ["sweatshirt", "hoodie", "football shirt", "umbro"],
}

USER_AGENT = "moneyhunter/0.1 (+personal deal scanner)"
