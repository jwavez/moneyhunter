"""Routes scanner output to the community hub channels. Community-safe: deal data only.
Webhook URLs come from env MONEYHUNTER_WEBHOOKS (JSON {channel: url}); never printed."""
import datetime as dt, json, os, re, urllib.request
from . import discord as D, embeds as E
from .scanners import hotukdeals

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
PRICES = os.path.join(DATA, "prices.json")
CAT_CHANNEL = {"trainers": "trainers", "sportswear": "trainers", "lego": "lego", "gaming": "games-consoles",
               "tools": "tools", "fragrance": "fragrance", "tech": "tech"}
PRICE_ERROR_RE = re.compile(r"price (error|glitch|mistake)|pricing error|glitch|mispric", re.I)   # [H]
HOT_HEAT, ERROR_HEAT, DROP_PCT = 200, 500, 10   # [H] hot ≥200° to category channels, very hot ≥500° to #price-errors, drop ≥10%
TREND_MIN = 100                                   # [H] minimum heat to list in #trending

def hooks() -> dict:
    try: return json.loads(os.getenv("MONEYHUNTER_WEBHOOKS") or "{}")
    except ValueError: return {}

def send(ch, embeds, components=None, dry=False, content=""):
    h = hooks()
    url = h.get(ch) or (os.getenv(D.ENV) if ch == "bot-status" else None)
    if not url and not dry:
        print(f"[hub] no webhook for #{ch}; skipped"); return 0
    st = D.post(embeds, content=content, dry_run=dry or not url, components=components, url=url)
    print(f"[hub] #{ch}: {st or 'dry-run'}"); return st

def ok(st): return bool(st) and 200 <= st < 300

def title_key(title): return hotukdeals.dedupe_key(title, 0)

def mini(it, color, prefix=""):
    """Compact embed for an unpriced deal (trending / price error / drop)."""
    q = E.short_query(it["title"])
    heat = f"🌡️ {it['heat']}°" if it.get("heat") is not None else ""
    e = {"title": (prefix + it["title"])[:250], "url": it["url"], "color": color,
         "description": f"**£{it['price']:.2f}** · {it.get('merchant') or 'retailer'} {('· ' + heat) if heat else ''}\n"
                        f"Not yet priced by MONEYHUNTER: check sold prices before buying.",
         "footer": {"text": f"MONEYHUNTER · {E.SCHEDULE}"}}
    if it.get("thumb"): e["thumbnail"] = {"url": it["thumb"]}
    return e

def buttons(it):
    q = E.short_query(it["title"])
    b = lambda l, u, em: {"type": 2, "style": 5, "label": l, "url": u[:512], "emoji": {"name": em}}
    return [{"type": 1, "components": [b("Open deal", it["url"], "🛒"), b("eBay sold", E.ebay_sold_url(q), "📊"), b("Vinted", E.vinted_url(q), "👕")]}]

def price_drops(raws, now=None):
    """Compare to prices seen in earlier scans (state branch prices.json)."""
    now = now or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    old = json.load(open(PRICES)) if os.path.exists(PRICES) else {}
    drops = []
    for it in raws:
        k = title_key(it["title"]); prev = old.get(k)
        if prev and it["price"] <= prev["price"] * (1 - DROP_PCT / 100):
            drops.append((it, prev))
        if not prev or it["price"] < prev["price"] or (prev.get("ts", "") < now[:10]):
            low = min(it["price"], prev["price"]) if prev else it["price"]
            old[k] = {"price": it["price"], "low": low, "ts": now, "url": it["url"]}
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=45)).isoformat()
    old = {k: v for k, v in old.items() if v.get("ts", "") >= cutoff}   # keep 45 days
    return drops, old

def route(raws, graded, stats, near, seen, dry=False, max_cards=5):
    """Post everything new. Returns keys to add to seen."""
    new = set()
    # 1) graded A/B cards -> buy-now / verify + category channel
    n = 0
    for d, r in graded:
        g = r.grade[0]
        if g not in "AB" or r.cost > E.COMMUNITY_MAX_PRICE: continue
        k = hotukdeals.dedupe_key(d.title, d.buy_price)
        if k in seen or n >= max_cards: continue
        card, comps = E.deal_card(d, r), E.link_buttons(d)
        st = send("buy-now" if g == "A" else "verify", card, comps, dry)
        ch = CAT_CHANNEL.get(d.category)
        if ch: send(ch, card[:1], comps, dry)
        if ok(st) or dry: new.add(k); n += 1
    # 2) price errors / very hot
    for it in raws:
        k = "pe:" + it["url"]
        if k in seen: continue
        if PRICE_ERROR_RE.search(it["title"]) or (it.get("heat") or 0) >= ERROR_HEAT:
            st = send("price-errors", [mini(it, 0xF97316, "⚡ ")], buttons(it), dry)
            if ok(st) or dry: new.add(k)
    # 3) trending digest: new hot items, one message, up to 10
    hot = sorted([it for it in raws if (it.get("heat") or 0) >= TREND_MIN and "tr:" + it["url"] not in seen],
                 key=lambda x: -x["heat"])[:10]
    if hot:
        lines = [f"**{it['heat']}°** · [{it['title'][:70]}]({it['url']}) · £{it['price']:.2f}" for it in hot]
        st = send("trending", [{"title": f"🌡️ Trending on hotukdeals · {len(hot)} new", "color": 0xEF4444,
                                "description": "\n".join(lines)[:4000], "footer": {"text": "Heat = community votes · not priced by MONEYHUNTER"}}], None, dry)
        if ok(st) or dry: new |= {"tr:" + it["url"] for it in hot}
        for it in hot:   # hot items also go to their category channel
            ch = CAT_CHANNEL.get(it["category"])
            if ch and it["heat"] >= HOT_HEAT and "cat:" + it["url"] not in seen:
                if ok(send(ch, [mini(it, 0xEF4444, "🔥 ")], buttons(it), dry)) or dry: new.add("cat:" + it["url"])
    # 4) price drops
    drops, prices = price_drops(raws)
    for it, prev in drops[:5]:
        k = f"pd:{it['url']}:{it['price']}"
        if k in seen: continue
        e = mini(it, 0x06B6D4, "📉 ")
        e["description"] = f"**£{prev['price']:.2f} → £{it['price']:.2f}** (−{(1 - it['price'] / prev['price']) * 100:.0f}%) since {prev['ts'][:10]}\n" + e["description"].split("\n", 1)[1]
        if ok(send("price-drops", [e], buttons(it), dry)) or dry: new.add(k)
    if not dry: json.dump(prices, open(PRICES, "w"))
    # 5) health report every scan
    send("bot-status", [E.scan_summary(stats, near)], None, dry)
    return new

def digest(deals_path, dry=False):
    """Daily 8am near-miss digest from the published deals.json."""
    d = json.load(open(deals_path))
    near = [x for x in d["deals"] if x["grade"] == "R"][:10]
    lines = [f"`{'✅' if x['under_cap'] else '£60+'}` [{x['title'][:60]}]({x['url']}) · £{x['buy']:.2f} → £{x['target']:.2f} · net {x['net']:+.2f} · max buy £{x['max_buy']:.2f} · {(x['why'] or ['-'])[0]}" for x in near]
    s = d["stats"]
    return send("near-misses", [{"title": f"🟠 Daily near-miss digest · {dt.date.today():%a %d %b}", "color": 0xF59E0B,
        "description": ("These nearly passed. If one drops to its **max buy**, it becomes a deal.\n\n" + "\n".join(lines))[:4000] if lines else "No priced near-misses in the last scan.",
        "footer": {"text": f"{s['scanned']} scanned · {s['priced']} priced · {s['A']} buy · {s['B']} verify"}}], None, dry)

def leaderboard(api_url, dry=False):
    with urllib.request.urlopen(urllib.request.Request(api_url, headers={"User-Agent": "moneyhunter"}), timeout=20) as r:
        lb = json.load(r)
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"{medals[i] if i < 3 else f'`{i+1}.`'} **{u['name'][:32]}** · {u['xp']} XP · {u['flips']} flips" for i, u in enumerate(lb.get("top", [])[:15])]
    return send("leaderboard", [{"title": f"🏆 Weekly leaderboard · w/c {dt.date.today():%d %b %Y}", "color": 0xEAB308,
        "description": "\n".join(lines) if lines else "No flips logged yet. Be first: use **Log a flip** in #flip-log.",
        "footer": {"text": "XP: 10 per logged flip + 1 per £ profit (max 200 per flip)"}}], None, dry)
