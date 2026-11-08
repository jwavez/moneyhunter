"""Grading engine: EV across 4 outcomes, no-loss floor, 8 gates, tiers, quarter-Kelly."""
from dataclasses import dataclass, field
from typing import Optional
from . import sell as S
from . import config as C
from .fees import net_profit

@dataclass
class Deal:
    title: str; url: str; buy_price: float; category: str; source: str
    merchant: str = ""; inbound_delivery: float = 0.0; delivery: str = "unknown"
    target: Optional[float] = None; stretch: Optional[float] = None
    floor: Optional[float] = None; floor_verified: bool = False
    sold_90d: Optional[int] = None; sell_through: Optional[float] = None; days_to_sell: Optional[float] = None
    comp_note: str = ""; heat: Optional[int] = None
    comp_age_days: Optional[int] = None; comp_has_evidence: bool = False
    evidence_type: str = "legacy_reference"
    floor_age_days: Optional[int] = None
    velocity_age_days: Optional[int] = None
    delivery_known: bool = False
    online_eligible: bool = False
    offer_verified: bool = False
    availability: str = "unknown"

@dataclass
class Result:
    grade: str; ev_net: float; ev_roi: float; worst: float; annual_roi: Optional[float]
    confidence: float; kelly_stake: float; outcomes: list; gates: list; cost: float
    platform: str; plan: dict = field(default_factory=dict); reasons: list = field(default_factory=list)
    worst_verified: bool = False; postage: float = 0.0

def grade(d: Deal, bankroll: float, platform: str = "ebay_business") -> Optional[Result]:
    if d.target is None:
        return None  # unpriced: no comps, cannot grade
    import math
    values = (d.buy_price, d.inbound_delivery, d.target, d.stretch or d.target)
    if not all(math.isfinite(v) and v >= 0 for v in values) or d.buy_price <= 0:
        raise ValueError("finite positive acquisition/valuation and nonnegative delivery required")
    tier = C.tier_for(bankroll)
    cost = round(d.buy_price + d.inbound_delivery, 2)
    stretch = d.stretch or d.target
    quick = round(d.target * C.QUICK_FACTOR, 2)
    floor_fresh = d.floor_age_days is not None and 0 <= d.floor_age_days <= C.MAX_FLOOR_AGE_DAYS
    if getattr(d,'floor_observed_at',None):
        from .evidence import age_hours
        floor_fresh = floor_fresh and 0 <= age_hours(d.floor_observed_at) < 24
    verified_floor = d.floor_verified and floor_fresh
    velocity_fresh = d.velocity_age_days is not None and 0 <= d.velocity_age_days <= C.MAX_VELOCITY_AGE_DAYS
    floor = d.floor if verified_floor and d.floor is not None else round(d.target * C.UNVERIFIED_FLOOR_FACTOR, 2)
    post = C.postage_for(d.category)
    net = lambda p: net_profit(p, cost, platform, d.category, post, C.PACKAGING, C.RETURNS_ALLOWANCE).net
    pf = max(0.0, 1 - C.P_STRETCH - C.P_TARGET - C.P_QUICK)
    outs = [("Stretch", stretch, C.P_STRETCH, net(stretch)), ("Target", d.target, C.P_TARGET, net(d.target)),
            ("Quick-sale", quick, C.P_QUICK, net(quick)),
            ("Floor exit" + ("" if verified_floor else " (unverified est.)"), floor, pf,
             round(floor - cost, 2) if verified_floor else net(floor))]   # verified floor = CeX cash (no fees); else sold on eBay
    ev = sum(p * n for _, _, p, n in outs)
    roi = ev / cost * 100 if cost else 0.0
    worst = outs[3][3]
    dts = d.days_to_sell
    fresh = d.comp_age_days is not None and 0 <= d.comp_age_days <= C.MAX_COMP_AGE_DAYS
    annual = roi * 365 / (dts + 3) if dts is not None else None
    # confidence from comp evidence
    conf = 0.0
    if d.sold_90d: conf += min(80, d.sold_90d * 8)
    if d.sell_through: conf += 20 if d.sell_through >= 100 else d.sell_through / 5
    if d.comp_note and not d.sold_90d: conf = 40.0   # published study only, not your own Terapeak check
    # quarter-Kelly
    wins = [(p, n) for _, _, p, n in outs if n > 0]; losses = [(p, n) for _, _, p, n in outs if n <= 0]
    pw = sum(p for p, _ in wins)
    w = sum(p * n for p, n in wins) / pw if pw else 0
    l = -sum(p * n for p, n in losses) / (1 - pw) if (1 - pw) > 0 else 0
    if l <= 0.01: kelly = 1.0
    else: kelly = max(0.0, pw / (l / cost) - (1 - pw) / (max(0.01, w) / cost))
    stake = round(min(kelly * C.KELLY_FRACTION, tier.max_pct / 100) * bankroll, 2)
    max_item = bankroll * tier.max_pct / 100
    gates = [
        (f"EV net >= £{tier.min_net}", ev >= tier.min_net),
        (f"EV ROI >= {tier.min_roi}%", roi >= tier.min_roi),
        (f"Days-to-sell <= {tier.max_dts}", dts is not None and dts <= tier.max_dts),
        (f"Sell-through >= {C.MIN_SELL_THROUGH:.0f}%", d.sell_through is not None and d.sell_through >= C.MIN_SELL_THROUGH),
        (f"Sold comps >= {C.MIN_COMPS} (90d)", d.sold_90d is not None and d.sold_90d >= C.MIN_COMPS),
        (f"Confidence >= {C.MIN_CONFIDENCE:.0f}", conf >= C.MIN_CONFIDENCE),
        ("No-loss: verified floor >= breakeven", verified_floor and worst >= 0),
        (f"Cost <= max item £{max_item:.2f}", cost <= max_item),
        (f"Sold prices <= {C.MAX_COMP_AGE_DAYS} days old", fresh),
        ("Reviewed exact-variant sold evidence", d.evidence_type == "sold" and d.comp_has_evidence),
        ("Inbound delivery known", d.delivery_known),
        ("Online delivery eligible", d.online_eligible),
        ("Availability checked", d.availability == "live"),
        ("Cash floor fresh", floor_fresh),
        ("Velocity evidence fresh", velocity_fresh),
        ("Exact offer identity/price reviewed", d.offer_verified),
    ]
    passed = sum(ok for _, ok in gates)
    money_ok = gates[0][1] and gates[1][1] and gates[7][1]
    if passed == len(gates): g = "A — BUY"
    elif money_ok and ev > 0 and fresh and all(ok for _, ok in gates[9:13]) and d.offer_verified and worst >= -0.25 * cost: g = "B — VERIFY"   # numbers work; missing your own comps/floor check
    else: g = "REJECT"
    if g == "REJECT": stake = 0.0
    reasons = [name for name, ok in gates if not ok]
    plan = {"entry": cost, "list": stretch, "target": d.target, "quick": quick, "floor": floor,
            "time_stop_day": tier.max_dts + 7, "time_stop_rule": dts is None,
            "reprice": "D3 target · D7 −5% + cross-list · D10 quick-sale",
            "platforms": S.platforms_text(d.category, d.target), "min_net": tier.min_net, "min_roi": tier.min_roi, "max_item": max_item}
    return Result(g, round(ev, 2), round(roi, 1), worst, round(annual, 0) if annual else None, conf, stake,
                  outs, gates, cost, platform, plan, reasons, verified_floor, post)
