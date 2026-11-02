"""Discord embed layouts: deal card and scan summary only. No personal data."""
import datetime as dt, urllib.parse
from . import config as C

GREEN, AMBER, RED, BLUE, GOLD = 0x22C55E, 0xF59E0B, 0xEF4444, 0x3B82F6, 0xEAB308
SCHEDULE = "Scans every 30 min, 24/7"
COMMUNITY_MAX_PRICE = 60.0   # [H] fixed public price cap shown in reports
COMMUNITY_MIN_NET, COMMUNITY_MIN_ROI = 8.0, 40.0   # [H] neutral max-buy rule
GATE_NAMES = {0: "Profit too small", 1: "Return too low", 2: "Sell speed not proven", 3: "Sell-through not proven",
              4: "Fewer than 5 sold comps", 5: "Low confidence", 6: "No verified exit price", 7: "Over the price cap",
              8: "Sold prices older than 30 days"}

def max_buy(r) -> float:
    """Highest buy price that still leaves £8 net and 40% ROI on expected proceeds. Rounded DOWN to the penny."""
    import math
    e_rev = r.cost + r.ev_net
    return max(0.0, math.floor(min(e_rev - COMMUNITY_MIN_NET, e_rev / (1 + COMMUNITY_MIN_ROI / 100)) * 100) / 100)

def worst_text(r) -> str:
    return gbp(r.worst, True) + ("" if r.worst_verified else " (est.)")

def dts_text(days) -> str:
    return f"~{days:g} days" if days else "No data yet"

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
    t = re.split(r"[-–(|,]| w/| with | sold by", title, maxsplit=1, flags=re.I)[0]
    return " ".join(t.split()[:6])

def gates_failed(r) -> list:
    return [GATE_NAMES[i] for i, (_, ok) in enumerate(r.gates) if not ok]

def deal_card(d, r, preview: bool = False) -> list:
    g = r.grade[0]
    color, icon, word = {"A": (GREEN, "🟢", "BUY"), "B": (AMBER, "🟡", "VERIFY")}.get(g, (RED, "🔴", "PASS"))
    q = short_query(d.title)
    failed = gates_failed(r)
    if g == "A": why = "All 9 checks pass · verified exit above breakeven"
    elif g == "B": why = "Profit works on estimated prices. Not proven yet: " + " · ".join(failed[:3]) + ". Check eBay sold before buying."
    else: why = " · ".join(failed[:2])
    mb = max_buy(r)
    conf = int(r.confidence)
    dts = dts_text(d.days_to_sell)
    links = f"[🛒 Buy]({d.url}) · [📊 eBay sold]({ebay_sold_url(q)}) · [👕 Vinted]({vinted_url(q)})"
    card = {
        "author": {"name": f"{'PREVIEW · ' if preview else ''}{d.merchant or d.source} via hotukdeals · {speed_emoji(d.delivery)} {d.delivery}"[:256]},
        "title": f"{icon} {word} · {gbp(r.ev_net, True)} net · {r.ev_roi:+.0f}% ROI".replace("-", "−"),
        "url": d.url,
        "description": f"**{d.title[:180]}**\n{links}",
        "color": color,
        "fields": [
            {"name": "Buy", "value": gbp(r.cost), "inline": True},
            {"name": "Sell target", "value": gbp(r.plan["target"]), "inline": True},
            {"name": "Net (expected)", "value": gbp(r.ev_net, True), "inline": True},
            {"name": "ROI", "value": f"{r.ev_roi:+.0f}%".replace("-", "−"), "inline": True},
            {"name": "Days to sell", "value": dts, "inline": True},
            {"name": "Max buy price", "value": gbp(mb), "inline": True},
            {"name": "Worst case", "value": worst_text(r), "inline": True},
            {"name": "Confidence", "value": f"{bar(conf)} {conf}", "inline": True},
            {"name": "Why" if g == "A" else "Why not BUY", "value": why[:300], "inline": False},
            {"name": "Risks", "value": RISK_BY_CAT.get(d.category, "Condition and returns"), "inline": False},
        ] + _intel_fields(d),
        "footer": {"text": f"MONEYHUNTER · {SCHEDULE} · not financial advice"},
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if getattr(d, "thumb", ""):
        card["thumbnail"] = {"url": d.thumb}
    p = r.plan
    details = {
        "color": color,
        "description": (f"**Plan** list {gbp(p['list'])} → {gbp(p['target'])} (D3) → −5% + cross-list (D7) → {gbp(p['quick'])} (D10) → "
                        f"{exit_text(p, r.worst_verified)}\n"
                        f"**Costs counted** eBay business fees, {gbp(r.postage)} postage, £0.50 packaging, 3% returns\n"
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

def scan_summary(stats: dict, near: list, preview: bool = False) -> dict:
    lines = []
    for d, r in near[:6]:
        f = gates_failed(r)
        lines.append(f"`{r.grade[0] if r.grade[0] in 'AB' else 'R'}` **{short_query(d.title)[:38]}** · {gbp(r.cost)} → {gbp(r.plan['target'])} · "
                     f"{gbp(r.ev_net, True)} · {f[0] if f else 'passes'}")
    color = GREEN if stats["A"] else AMBER if stats["B"] else BLUE
    return {
        "author": {"name": ("PREVIEW · " if preview else "") + "MONEYHUNTER scan report"},
        "title": f"🔎 {stats['scanned']} deals scanned · {stats['A']} buy · {stats['B']} verify",
        "color": color,
        "fields": [
            {"name": "Scanned", "value": str(stats["scanned"]), "inline": True},
            {"name": "Priced", "value": str(stats["priced"]), "inline": True},
            {"name": f"Under {gbp(COMMUNITY_MAX_PRICE)} cap", "value": str(stats["affordable"]), "inline": True},
            {"name": "🟢 A", "value": str(stats["A"]), "inline": True},
            {"name": "🟡 B", "value": str(stats["B"]), "inline": True},
            {"name": "🔴 Rejected", "value": str(stats["R"]), "inline": True},
            {"name": "Closest near-misses", "value": "\n".join(lines) if lines else "None under the price cap this scan", "inline": False},
            {"name": "Safety filters", "value": f"{stats.get('uncertain', 0)} uncertain matches not priced (kids, bundles, editions, sizes) · {stats.get('stale', 0)} stale comps · {stats.get('expired', 0)} expired deals dropped", "inline": False},
            {"name": "Help price more deals", "value": f"{stats['unpriced']} deals had no sold-price data yet. Spotted what one of these really sells for? Share the sold listing and it gets added.", "inline": False},
        ],
        "footer": {"text": f"MONEYHUNTER · hourly summary · errors post immediately"},
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def link_buttons(d) -> list:
    """Non-interactive link buttons; allowed on plain webhooks with ?with_components=true [S docs.discord.com]."""
    q = short_query(d.title)
    btn = lambda label, url, emoji: {"type": 2, "style": 5, "label": label, "url": url[:512], "emoji": {"name": emoji}}
    return [{"type": 1, "components": [btn("Open deal", d.url, "🛒"), btn("eBay sold", ebay_sold_url(q), "📊"), btn("Vinted", vinted_url(q), "👕")]}]
