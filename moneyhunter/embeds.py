"""Discord embed layouts: deal card and scan summary only. No personal data."""
import datetime as dt, urllib.parse
from . import config as C, sell as S

GREEN, AMBER, RED, BLUE, GOLD = 0x22C55E, 0xF59E0B, 0xEF4444, 0x3B82F6, 0xEAB308
SCHEDULE = "30-minute cron target · best effort; check last successful scan"
COMMUNITY_MAX_PRICE = 60.0   # [H] T0 public price cap
import os as _os
TIER_CAPS = C.COMMUNITY_CAPS            # [H] max buy per tier (matches private app ladder)
TIER_BANKROLL = C.COMMUNITY_RULE_BANKROLLS    # [H] representative bankroll so grading gates fit each cap

def active_tier() -> int:
    """Tier number only (0-4), synced from the private app via the workflow. Anything invalid -> 0 (safest)."""
    from .policy import current
    return current()['community_index']

def community_cap() -> float:
    return TIER_CAPS[active_tier()]
COMMUNITY_MIN_NET, COMMUNITY_MIN_ROI = 8.0, 40.0   # [H] neutral max-buy rule
GATE_NAMES = {0: "Profit too small", 1: "Return too low", 2: "Sell speed not proven", 3: "Sell-through not proven",
              4: "Fewer than 5 sold comps", 5: "Low confidence", 6: "No verified exit price", 7: "Over the price cap",
              8: "Sold prices older than 30 days",
              9: "No reviewed exact-variant sold evidence", 10: "Inbound delivery unknown", 11: "Not online-delivery eligible",
              12: "Availability not confirmed", 13: "Cash exit quote missing/stale", 14: "Velocity evidence missing/stale",
              15: "Exact retailer offer identity/price not reviewed"}

def max_buy(r) -> float:
    """Highest buy price that still leaves £8 net and 40% ROI on expected proceeds. Rounded DOWN to the penny."""
    import math
    e_rev = r.cost + r.ev_net
    # Financial ceiling only; availability/evidence/delivery gates still apply. Include downside for VERIFY.
    floor_proceeds = r.cost + r.worst
    downside_limit = floor_proceeds if r.grade.startswith("A") else floor_proceeds / 0.75
    return max(0.0, math.floor(min(e_rev - r.plan.get("min_net", COMMUNITY_MIN_NET), e_rev / (1 + r.plan.get("min_roi", COMMUNITY_MIN_ROI) / 100), r.plan.get("max_item", community_cap()), community_cap(), downside_limit) * 100) / 100)

def worst_text(r) -> str:
    return gbp(r.worst, True) + ("" if r.worst_verified else " (est.)")

def dts_text(days) -> str:
    return f"~{days:g} days" if days is not None else "No data yet"

def exit_text(p, worst_verified) -> str:
    day = f"day {p['time_stop_day']}" + (" (house rule)" if p.get("time_stop_rule") else "")
    if worst_verified:
        return f"exit at {gbp(p['floor'])} (verified floor) by {day}"
    return f"if unsold by {day}, sell at best offer (est. {gbp(p['floor'])}, not verified)"
RISK_BY_CAT = {"trainers": "Fakes and sizing returns", "sportswear": "Condition and sizing", "lego": "Box damage",
               "tools": "Untested or missing parts", "gaming": "Faults and returns", "fragrance": "Fakes, testers, postage rules"}

def gbp(x: float, sign: bool = False) -> str:
    s = f"£{abs(x):,.2f}"
    return ("+" if x >= 0 else "−") + s if sign else ("−" + s if x < 0 else s)

def bar(pct: float, n: int = 10) -> str:
    k = max(0, min(n, round(pct / 100 * n)))
    return "▰" * k + "▱" * (n - k)

def speed_emoji(delivery: str) -> str:
    d = delivery.lower()
    if "next day" in d: return "⚡"
    if "in-store" in d: return "🚫"
    if "collect" in d: return "📦"
    return "🚚"

def ebay_sold_url(q: str) -> str:
    return "https://www.ebay.co.uk/sch/i.html?" + urllib.parse.urlencode({"_nkw": q, "LH_Sold": 1, "LH_Complete": 1, "LH_PrefLoc": 1})

def vinted_url(q: str) -> str:
    return "https://www.vinted.co.uk/catalog?" + urllib.parse.urlencode({"search_text": q, "order": "price_low_to_high"})

def short_query(title: str) -> str:
    import re
    # Preserve exact SKUs, hyphenated models, sizes and platform/edition information.
    # Only cut an explicitly separated promotional suffix, never an internal hyphen.
    t = re.split(r"\s[-–|]\s|\s+w/|\s+with code|\s+sold by", title, maxsplit=1, flags=re.I)[0]
    t = re.sub(r"[£]\s?\d+(?:\.\d{1,2})?", "", t)
    return " ".join(t.split())[:160]

def gates_failed(r) -> list:
    return [GATE_NAMES.get(i, name) for i, (name, ok) in enumerate(r.gates) if not ok]

def deal_card(d, r, preview: bool = False) -> list:
    g = r.grade[0]
    color, icon, word = {"A": (GREEN, "🟢", "BUY"), "B": (AMBER, "🟡", "VERIFY")}.get(g, (RED, "🔴", "PASS"))
    q = short_query(d.title)
    failed = gates_failed(r)
    if g == "A": why = "All evidence, landed-cost and availability checks pass · current cash quote above breakeven (subject to testing)"
    elif g == "B": why = "Profit works on estimated prices. Not proven yet: " + " · ".join(failed[:3]) + ". Check eBay sold before buying."
    else: why = " · ".join(failed[:2])
    mb = max_buy(r)
    conf = int(r.confidence)
    dts = S.dts_label(d.category, d.days_to_sell)
    alt = f"[👕 Vinted]({vinted_url(q)})" if d.category in S.CLOTHING else f"[💷 CeX]({S.cex_url(q)})" if d.category in S.CEX_FLOOR else ""
    links = f"[🛒 Buy]({d.url}) · [📊 eBay sold]({ebay_sold_url(q)})" + (f" · {alt}" if alt else "")
    card = {
        "author": {"name": f"{'PREVIEW · ' if preview else ''}{d.merchant or d.source} via hotukdeals · {speed_emoji(d.delivery)} {d.delivery}"[:256]},
        "title": ("⚡ FAST · " if S.fast_route(g, d.category, d.days_to_sell) else "") + f"{icon} {word} · {gbp(r.ev_net, True)} net · {r.ev_roi:+.0f}% ROI".replace("-", "−"),
        "url": d.url,
        "description": f"**{d.title[:180]}**\n{links}",
        "color": color,
        "fields": [
            {"name": "Buy", "value": gbp(r.cost), "inline": True},
            {"name": "Sell target", "value": gbp(r.plan["target"]), "inline": True},
            {"name": "Net (expected)", "value": gbp(r.ev_net, True), "inline": True},
            {"name": "ROI", "value": f"{r.ev_roi:+.0f}%".replace("-", "−"), "inline": True},
            {"name": "Days to sell", "value": dts, "inline": True},
            {"name": "Max landed cost (money gates only)", "value": gbp(mb), "inline": True},
            {"name": "Worst case", "value": worst_text(r), "inline": True},
            {"name": "Confidence", "value": f"{bar(conf)} {conf}", "inline": True},
            {"name": "Why" if g == "A" else "Why not BUY", "value": why[:300], "inline": False},
            {"name": "Sell on", "value": S.sell_on_value(d.category, r.plan["target"]), "inline": False},
            {"name": "Max hold", "value": S.HOLD_TIP, "inline": False},
            {"name": "Risks", "value": RISK_BY_CAT.get(d.category, "Condition and returns"), "inline": False},
        ] + _intel_fields(d),
        "footer": {"text": f"MONEYHUNTER · {SCHEDULE} · not financial advice"},
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    from . import presentation,product_format as PF
    if PF.reason(vars(d)):return [PF.research_card(vars(d))]
    legacy={'grade':g,'evidence_type':getattr(d,'evidence_type',None),'plan':r.plan,'buy':d.buy_price,'landed_cost':r.cost,'delivery_known':d.delivery_known,'postage':r.postage}
    card['fields']=presentation.fields({'price':d.buy_price,'category':d.category},model=getattr(d,'ask_estimate',None),legacy=legacy)+card['fields']
    if getattr(d, "thumb", ""):
        from .images import safe
        if safe(d.thumb):card["image"] = {"url":safe(d.thumb)}
    from .images import metadata
    card.update(metadata({**vars(d),'publication_listing':r.plan['list']}))
    if (getattr(d,"image_basis",None) or "").startswith("Reference"):card["description"] += "\nImage: exact-set reference, not proof of listing condition."
    p = r.plan
    details = {
        "color": color,
        "description": (f"**Plan** list {gbp(p['list'])} → {gbp(p['target'])} (D3) → −5% + cross-list (D7) → {gbp(p['quick'])} (D10) → "
                        f"{exit_text(p, r.worst_verified)}\n"
                        f"**Costs counted** eBay business standard fees incl 20% VAT, {gbp(r.postage)} postage, £0.50 packaging, 3% returns\n"
                        f"**Sell on** {p['platforms']}\n"
                        f"**Failed checks** {', '.join(failed) if failed else 'none'}\n"
                        f"**Comps** {(d.comp_note or 'none')[:180]}")[:1500],
    }
    return [card, details]

def _intel_fields(d) -> list:
    i = getattr(d, "intel", None) or {}
    out = []
    if i.get("retailer"): out.append({"name": "Retailer", "value": i["retailer"][:200], "inline": False})
    if i.get("fake"): out.append({"name": "Fake risk", "value": i["fake"][:200], "inline": False})
    if i.get("history"): out.append({"name": "Price history", "value": i["history"][:200], "inline": True})
    if i.get("cashback"): out.append({"name": "Cashback", "value": i["cashback"][:200], "inline": True})
    return out

def sources_text(sources):
    lines = []
    for name, v in sources.items():
        if "feeds_ok" in v:
            lines.append(f"{name}: feeds {v.get('feeds_ok', 0)} OK/{v.get('feeds_failed', 0)} failed, raw {v.get('feed_items', 0)}, duplicates {v.get('duplicates', 0)}, old {v.get('old_dropped', 0)}, missing price/category {v.get('missing_price_or_category', 0)}")
        else:
            detail = v.get("research")
            suffix = f"; indicative asks {detail['candidates_with_samples']} candidates, {detail['queries']} queries, {detail['cached']} cached ({detail['status']})" if detail else ""
            if detail:
                watch=detail.get('above_budget_research',{})
                suffix+=f"; watch {watch.get('queries',0)} queries/{watch.get('cached',0)} cached"
            if name=='ebay_acquisition':suffix+=f"; {v.get('queries',0)}/{v.get('query_budget',0)} queries ({v.get('price_led_queries',0)} value-led / {v.get('research_discovery_queries',0)} discovery), {v.get('candidates',0)} retained offers"
            lines.append(f"{name}: {v.get('status', 'not configured')}{suffix}")
    return " · ".join(lines)[:1000] or "Not reported"

def scan_summary(stats: dict, near: list, preview: bool = False) -> dict:
    lines = []
    for d, r in near[:6]:
        f = gates_failed(r)
        lines.append(f"`{r.grade[0] if r.grade[0] in 'AB' else 'R'}` **{short_query(d.title)[:38]}** · {gbp(r.cost)} → {gbp(r.plan['target'])} · "
                     f"{gbp(r.ev_net, True)} · {f[0] if f else 'passes'}")
    color = GREEN if stats["A"] else AMBER if stats["B"] else BLUE
    return {
        "author": {"name": ("PREVIEW · " if preview else "") + "MONEYHUNTER scan report"},
        "title": f"🔎 {stats['scanned']} unique feed offers · {stats['A']} buy · {stats['B']} verify",
        "color": color,
        "fields": [
            {"name": "New / rescanned", "value": f"{stats.get('new', '?')} / {stats.get('rescanned', '?')}", "inline": True},
            {"name": "Sold-valued / reference-only", "value": f"{stats.get('sold_valued', 0)} / {stats.get('reference_only', 0)}", "inline": True},
            {"name": "Legacy/reference-priced offers (separate ask lane)", "value": str(stats["priced"]), "inline": True},
            {"name": f"Legacy/reference-priced under {gbp(community_cap())} cap (index {active_tier()}, {C.tier_for(TIER_BANKROLL[active_tier()]).name})", "value": str(stats["affordable"]), "inline": True},
            {"name": "All offers: online physical / known inbound / landed under cap", "value": f"{stats.get('online_eligible', '?')} / {stats.get('delivery_known', '?')} / {stats.get('under_cap_known_delivery', '?')}", "inline": False},
            {"name": "Source health", "value": sources_text(stats.get("sources", {})), "inline": False},
            {"name": "🟢 A", "value": str(stats["A"]), "inline": True},
            {"name": "🟡 B", "value": str(stats["B"]), "inline": True},
            {"name": "🔴 Rejected", "value": str(stats["R"]), "inline": True},
            {"name": "Closest near-misses", "value": "\n".join(lines) if lines else "None under the price cap this scan", "inline": False},
            {"name": "Safety filters", "value": f"{stats.get('uncertain', 0)} uncertain matches · {stats.get('stale', 0)} stale references · expiry checked {stats.get('expiry_checked', 0)}, expired {stats.get('expired', 0)}, unknown/not checked {stats.get('expiry_unknown', 0)}", "inline": False},
            {"name": "Help price more deals", "value": f"{stats['unpriced']} without legacy/reference pricing; {stats.get('without_any_pricing',stats['unpriced'])} without either pricing lane. {stats.get('review_candidates',0)} research candidates in review_queue. Submit exact competitor asking links for estimate research or actual sold links for evidence review; neither automatically becomes BUY. Above-budget remains WATCH ONLY.", "inline": False},
        ],
        "footer": {"text": f"Last prior successful scan: {stats.get('previous_success') or 'no history yet'} · gap {stats.get('gap_minutes', '?')} min"},
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def link_buttons(d) -> list:
    """Non-interactive link buttons; allowed on plain webhooks with ?with_components=true [S docs.discord.com]."""
    q = short_query(d.title)
    btn = lambda label, url, emoji: {"type": 2, "style": 5, "label": label, "url": url[:512], "emoji": {"name": emoji}}
    row = [btn("Open deal", d.url, "🛒"), btn("eBay sold", ebay_sold_url(q), "📊")]
    if d.category in S.CLOTHING: row.append(btn("Vinted", vinted_url(q), "👕"))
    elif d.category in S.CEX_FLOOR: row.append(btn("CeX price", S.cex_url(q), "💷"))
    return [{"type": 1, "components": row}]

def quiet_key(now=None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    return f"quiet:{now:%Y-%m-%d-%H}"

def quiet_card(stats: dict, pulse: str) -> dict:
    """Professional 'market quiet' note when a scan finds no A/B deals. No profit claims."""
    return {"title": "🔎 No verified buying opportunities this scan", "color": BLUE,
            "description": (f"Scanned **{stats['scanned']}** offers · {stats.get('new','?')} new / {stats.get('rescanned','?')} rescans · {stats.get('ask_valued',0)} competitor-ask estimates · {stats.get('estimated_opportunities',0)} Strong CHECK / {stats.get('worth_reviewing',0)} manual review / {stats.get('above_budget_estimates',0)} above-budget estimates.\nSeparately: {stats['priced']} legacy/reference valuations, {stats.get('sold_valued',0)} sold-valued; {stats.get('A',0)} verified BUY / {stats.get('B',0)} verified VERIFY. This is not proof the market has no deals.\n"
                            f"**Market pulse:** {pulse}\n\n"
                            "👀 WATCH cards in category channels are homework, not buy signals.\n"
                            "⚡ Fast movers (≤10 days to sell) post to #fast-movers when they appear.\n"
                            "Cron targets 30 minutes but can be delayed/dropped; see scan health. Never force a bad buy.")[:4096],
            "footer": {"text": f"MONEYHUNTER · {SCHEDULE} · at most one quiet note per hour"},
            "timestamp": now_iso()}

def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
