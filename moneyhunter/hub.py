"""Routes scanner output to the community hub channels. Community-safe: deal data only.
Webhook URLs come from env MONEYHUNTER_WEBHOOKS (JSON {channel: url}); never printed."""
import datetime as dt, json, os, re, urllib.request
from . import discord as D, embeds as E, sell as S
from .scanners import hotukdeals
from . import product_format as PF, presentation

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
PRICES = os.path.join(DATA, "prices.json")
CAT_CHANNEL = {"trainers": "trainers", "sportswear": "trainers", "lego": "lego", "gaming": "games-consoles",
               "tools": "tools", "fragrance": "fragrance", "tech": "tech"}
PRICE_ERROR_RE = re.compile(r"price (error|glitch|mistake)|pricing error|glitch|mispric", re.I)   # [H]
HOT_HEAT, ERROR_HEAT, DROP_PCT = 200, 500, 10   # [H] hot ≥200° to category channels, very hot ≥500° to #price-errors, drop ≥10%
GROCERY_RE = re.compile(r"\b(tesco|asda|sainsbury|iceland|morrisons|aldi|lidl|co-?op|ocado|waitrose|clubcard|nectar|"
                        r"farmfoods|heron|b&m|home bargains|poundland|fuel|petrol|takeaway|just eat|deliveroo|uber eats|"
                        r"greggs|mcdonald|kfc|subway|costa|starbucks|burger king|nando)\b", re.I)   # not flippable
NOT_RESELLABLE_RE = re.compile(
    r"\b(steam|pc game|pc code|cd ?key|game key|digital|download|dlc|season pass|code in a box|e-?gift|gift card|voucher|"
    r"subscription|membership|game pass|ps plus|playstation plus|nintendo online|prime video|to buy prime|to rent|rental|"
    r"rent |streaming|ebook|kindle edition|audible|audiobook|app store|in-app|vpn|broadband|sim only|sim card|insurance|"
    r"soy sauce|sauce|coffee|tea bags|snack|chocolate|crisps|biscuit|cereal|drink|bottle of|wine|beer|lager|gin|vodka|whisky|"
    r"water|juice|protein|vitamin|food|munch|meal|pizza|"
    r"dishwasher|detergent|laundry|washing (up|liquid|powder|capsules|pods)|fabric|toilet|kitchen roll|bin bags|cleaner|"
    r"bleach|shampoo|conditioner|toothpaste|razor blades|nappies|wipes|tablets|capsules|pods|batteries|light ?bulb|"
    r"thermo bottle|flask|food storage|container|tupperware|plant|compost|pet food|cat litter|"
    r"pre-?order|preorder|blu-?ray|dvd|4k uhd|box ?set|film collection|movie collection|"
    r"e-?scooter|electric scooter|scooter|e-?bike)\b", re.I)   # [H] digital, pre-orders, discs, scooters never flip fast
CAT_LABEL = {"trainers": "👟 Trainers", "sportswear": "👕 Sportswear", "lego": "🧱 LEGO", "gaming": "🎮 Games & consoles",
             "tools": "🛠️ Tools", "fragrance": "🧴 Fragrance", "tech": "🎧 Tech"}
DELIVERY_FAILURES = []
WATCH_PER_CHANNEL = 3   # [H] max WATCH cards per category channel per run

DIGITAL_STOREFRONTS = {"eneba", "loaded", "cdkeys", "cdkeys.com", "steam", "gog", "gog.com", "xbox", "microsoft", "nintendo eshop", "playstation store"}

def digital_store_risk(it):
    """Conservative source/format risk, not an assertion that every store item is digital.

    Explicit hardware can still be a physical research candidate. A game sold by a
    code/storefront source is not promoted merely because its title omitted 'digital'.
    """
    title = it.get("title", "")
    hardware = re.search(r"\b(controller|headset|keyboard|mouse|console|racing wheel)\b", title, re.I)
    return bool(PF.reason(it))

def resellable(it) -> bool:
    """Physical goods in a category we price; never food, household, consumables, digital or rentals."""
    return it.get("category") in CAT_LABEL and it.get("online_eligible", hotukdeals.online_status(it.get("title", ""))) and not digital_store_risk(it) and not NOT_RESELLABLE_RE.search(it.get("title") or "")

def sell_needed(buy: float, category: str, postage=None):
    """From the fee engine at this buy price: breakeven sell price, and the sell price for £8 net and 40% ROI."""
    from . import config as C
    from .fees import net_profit
    post = C.postage_for(category) if postage is None else postage
    net = lambda p: net_profit(p, buy, "ebay_business", category, post, C.PACKAGING, C.RETURNS_ALLOWANCE).net
    def solve(goal):
        lo, hi = 0.0, buy * 4 + 50
        for _ in range(50):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if net(mid) < goal else (lo, mid)
        import math; return math.ceil(hi * 100) / 100
    from .policy import current
    p = current()
    return solve(0.0), solve(max(p["strong_net"], buy * p["strong_roi"])), post

def watch_card(it, prices):
    from . import intel as I
    from . import matching as M
    from .policy import current
    policy = current()
    if PF.reason(it):return PF.research_card(it)
    it=PF.normalize(it)
    be, tgt, post = sell_needed(it["price"] + (it.get("inbound_delivery") or 0), it["category"])
    t = M.norm(it["title"] + " " + it.get("desc", ""))
    kids = it["category"] in ("trainers", "sportswear") and any(M.has(t, w) for w in M.KIDS)
    heat = f" · 🌡️ {it['heat']}°" if it.get("heat") is not None else ""
    e = {"author": {"name": f"{CAT_LABEL[it['category']]} · WATCH · not priced"},
         "title": ("👀 " + it["title"])[:250], "url": it["url"], "color": 0x64748B,
         "description": f"**£{it['price']:.2f}** at {it.get('merchant') or 'retailer'}{heat}\n"
                        "Competitor-based estimates are not sold prices or a verified BUY. Check exact variant, retailer stock and delivery."
                        + (" Inbound delivery unknown: required resale targets are minimums; any profit figure is an upper bound before delivery." if it.get("inbound_delivery") is None else " Delivery included in calculations.")
                        + ("\n⚠️ Kids' sizes: adult sold prices do not apply." if kids else ""),
         "fields": [{"name": "Breakeven sell price", "value": f"£{be:.2f}", "inline": True},
                    {"name": "Minimum sale needed for policy — NOT market price", "value": f"£{tgt:.2f}+", "inline": True},
                    {"name": "Price history", "value": I.price_history(title_key(it["title"]), it["price"], prices), "inline": True},
                    {"name": "Days to sell", "value": S.dts_label(it["category"], it.get("days_to_sell")), "inline": True},
                    {"name": "Sell on", "value": S.sell_on_value(it["category"], tgt), "inline": True},
                    {"name": "Max hold", "value": S.HOLD_TIP, "inline": False}]
                   + ([{"name": "Quick-cash floor", "value": "Exact CeX CASH/bank quote only, subject to testing. Voucher value is not cash; online payout is not same-day guaranteed.", "inline": False}]
                      if it["category"] in S.CEX_FLOOR else [])
                   + [{"name": "Retailer", "value": I.retailer(it.get("merchant", ""), it["title"])["label"][:200], "inline": False}],
         "footer": {"text": f"Sell prices after eBay business fees incl 20% VAT, £{post:.2f} postage, £0.50 packaging, 3% returns · strong = £{policy['strong_net']:g} net and {policy['strong_roi']*100:g}% ROI"}}
    if it['category']=='fragrance':
        from .transport import scenario
        sc=scenario(it)
        p=sc['profile']
        qualifier='conditional tariff scenario' + ('; excluding UNKNOWN inbound delivery' if not sc.get('inbound_known') else '')
        e['fields'][0]={'name':'Breakeven required resale — NOT market value','value':f"£{sc['breakeven']:.2f}+ ({qualifier})" if sc['breakeven'] is not None else p['reason'],'inline':False}
        e['fields'][1]={'name':'Strong-policy required resale — NOT valuation','value':f"£{sc['required_resale']:.2f}+ ({qualifier})" if sc['required_resale'] is not None else 'Unknown until an applicable compliant transport profile and costs are established','inline':False}
        e['fields'].append({'name':'Bottle-specific delivery scenario','value':transport_text(sc)[:1000],'inline':False})
        e['footer']['text']='Market sell estimate is independent of postage. Tariff scenario is NOT a parcel quote, insurance guarantee or buying approval. Evri prohibits perfume.'
        if not it.get('ask_estimate'):
            e['fields'].insert(0,{'name':'Estimated sell price — competitor asks','value':'Not established: '+it.get('ask_status','exact bottle type/concentration/ml comparable offers not yet available')+'. A required resale target is NOT an estimated selling price.','inline':False})
    model = it.get("ask_estimate")
    if not model and it["price"] + (it.get("inbound_delivery") or 0) > policy["cap"]:
        e["author"]["name"] = "ABOVE BUDGET — WATCH ONLY · not valued"
    if model:
        e["author"]["name"] = CAT_LABEL[it["category"]] + " · " + model["signal"]
        e["fields"] = estimate_fields(model) + e["fields"]
    if (it.get("image_basis") or "").startswith("Reference"):
        e["description"] += "\nImage: exact-set reference; check actual listing condition."
    if it.get("thumb"):
        from .images import safe
        if safe(it["thumb"]):e["image"] = {"url":safe(it["thumb"])}
    from .images import metadata
    e.update(metadata(it))
    e["fields"]=presentation.fields(it,model)+e["fields"]
    return e


def estimate_fields(m):
    if m.get('transport_validated') is False:
        sc=m.get('transport_scenario',{})
        value='Unknown: no applicable verified outbound quote. Market estimate above remains available.'
        if sc.get('status')=='conditional_tariff_scenario':
            value=(f"£{sc['net']:.2f} / {sc['roi']:.1f}% ROI" if sc.get('net') is not None else f"Up to £{sc['net_before_unknown_delivery']:.2f} BEFORE unknown inbound delivery" if sc.get('net_before_unknown_delivery') is not None else 'Unknown')+' — CONDITIONAL tariff/packaging scenario only; actual net/ROI not established.'
        return [
            {'name':'Estimated sell price — competitor asks, NOT a BUY','value':f"£{m['estimated_resale']:.2f}; suggested listing £{m['suggested_listing']:.2f}. Model range £{m['estimated_range'][0]:.2f}–£{m['estimated_range'][1]:.2f}. {m['seller_count']} independent sellers / {m['sample_count']} samples; {m['confidence']} confidence. NOT sold or guaranteed.",'inline':False},
            {'name':'Conditional profit scenario / actual net UNKNOWN','value':value,'inline':False},
            {'name':'Exact variant and provenance checks','value':' · '.join(m['checks'])[:1000],'inline':False},
            {'name':'Competitor sources','value':' · '.join(f"[Offer {i+1}]({o['url']})" for i,o in enumerate(m['sources'][:3])),'inline':False}]
    profit = (f"£{m['net']:.2f} / {m['roi']:.1f}% ROI at £{m['landed_cost']:.2f} landed" if m["delivery_known"] else
              f"Up to £{m['net_before_unknown_delivery']:.2f} before UNKNOWN inbound delivery; actual net/ROI unknown")
    stress = (f"Resale £{m['review_stress_sale']:.2f}: net £{m['review_stress_net']:.2f}, {m['review_stress_roi']:.1f}% ROI" if m.get('review_stress_net') is not None else "Unknown landed delivery: stress economics not established")
    return [
        {"name":"Manual-review downside scenario (not forecast)","value":stress + ". 10% price drop must leave £5 net AND 10% ROI; moderate confidence and 3 supporting low-price sellers required. Velocity unknown unless separately measured.","inline":False},
        {"name":"Estimated resale / suggested listing", "value":f"£{m['estimated_resale']:.2f} / £{m['suggested_listing']:.2f} · model range £{m['estimated_range'][0]:.2f}–£{m['estimated_range'][1]:.2f}. NOT sold or guaranteed.","inline":False},
        {"name":"Estimated net / ROI", "value":profit,"inline":False},
        {"name":"Competition / confidence", "value":f"{m['sample_count']} seller-deduplicated asks · {m['seller_count']} known sellers · {m['confidence']} confidence · observed {m['observed_at']}. Lowest delivered competition £{m['competition_low']:.2f}. {m['discount_note']}","inline":False},
        {"name":"Max landed buy / delivery headroom", "value":f"£{m['max_landed_buy']:.2f} / £{m['delivery_headroom']:.2f}; strong policy £{m.get('policy',{}).get('strong_net',8):g} net + {m.get('policy',{}).get('strong_roi',.4)*100:g}% ROI. Manual-review ceiling £{m.get('review_max_landed_buy',m['max_landed_buy']):.2f}. Check stock and checkout price. No sales speed measured.","inline":False},
        {"name":"Competitor sources", "value":" · ".join(f"[Offer {i+1}]({o['url']})" for i,o in enumerate(m["sources"][:3]))[:1000],"inline":False}]


def transport_text(sc):
    p=sc['profile']
    price=f"£{p['postage']:.2f} incl VAT" if p.get('postage') is not None else 'No applicable tariff'
    return f"{p['ml'] or 'Unknown'}ml · {price}; {p['reason']} Online UK small parcel <=2kg /45x35x16cm, original retail pack, protective/leakproof outer, ID8000 and return address; Post Office COUNTER only, not collection/postbox. Packaging £{p['packaging_assumption']:.2f} is only an allowance. Cover/exclusions must be checked, not guaranteed. Tariff checked {p['checked_at']}: [carrier]({p['rate_source']}) · [restrictions]({p['rules_source']})"


def market_pulse(raws, stats) -> str:
    cats = {}
    for it in raws:
        if resellable(it): cats[it["category"]] = cats.get(it["category"], 0) + 1
    top = sorted(cats.items(), key=lambda x: -x[1])
    hot = max((it for it in raws if resellable(it) and it.get("heat") is not None), key=lambda x: x["heat"], default=None)
    s = " · ".join(f"{CAT_LABEL[c]} {n}" for c, n in top) or "no category deals"
    if hot: s += f"\nHottest: {hot['heat']}° {hot['title'][:60]} (£{hot['price']:.2f})"
    return s

TREND_MIN = 100                                   # [H] minimum heat to list in #trending

def hooks() -> dict:
    try: return json.loads(os.getenv("MONEYHUNTER_WEBHOOKS") or "{}")
    except ValueError: return {}

def send(ch, embeds, components=None, dry=False, content=""):
    h = hooks()
    url = h.get(ch) or (os.getenv(D.ENV) if ch == "bot-status" else None)
    if not url and not dry:
        print(f"[hub] no webhook for #{ch}; skipped")
        if ch in ("buy-now", "verify", "bot-status"): DELIVERY_FAILURES.append(f"No delivery endpoint configured for #{ch}")
        return 0
    st = D.post(embeds, content=content, dry_run=dry or not url, components=components, url=url)
    if url and not dry and not ok(st): DELIVERY_FAILURES.append(f"Delivery to #{ch} failed (HTTP {st or 'network/disabled'})")
    print(f"[hub] #{ch}: {st or 'dry-run'}"); return st

def ok(st): return bool(st) and 200 <= st < 300

def title_key(title): return hotukdeals.dedupe_key(title, 0)

def mini(it, color, prefix=""):
    """Compact embed for an unpriced deal (trending / price error / drop)."""
    if PF.reason(it):return PF.research_card(it)
    it=PF.normalize(it)
    q = E.short_query(it["title"])
    heat = f"🌡️ {it['heat']}°" if it.get("heat") is not None else ""
    e = {"title": (prefix + it["title"])[:250], "url": it["url"], "color": color,
         "description": f"**£{it['price']:.2f}** · {it.get('merchant') or 'retailer'} {('· ' + heat) if heat else ''}\n"
                        + (f"Estimated resale £{it['ask_estimate']['estimated_resale']:.2f} (competitor asks; NOT a BUY). Check stock, exact variant and all costs." if it.get("ask_estimate") else "Resale estimate not established: exact comparator research required; do not confuse the required resale target with market value."),
         "footer": {"text": f"MONEYHUNTER · {E.SCHEDULE}"}}
    if it.get("thumb"):
        from .images import safe
        if safe(it["thumb"]):e["image"] = {"url":safe(it["thumb"])}
    from .images import metadata
    e.update(metadata(it))
    return e

def buttons(it):
    q = E.short_query(it["title"])
    b = lambda l, u, em: {"type": 2, "style": 5, "label": l, "url": u[:512], "emoji": {"name": em}}
    row = [b("Open deal", it["url"], "🛒"), b("eBay sold", E.ebay_sold_url(q), "📊")]
    c = it.get("category")
    if c in S.CLOTHING: row.append(b("Vinted", E.vinted_url(q), "👕"))
    elif c in S.CEX_FLOOR: row.append(b("CeX price", S.cex_url(q), "💷"))
    return [{"type": 1, "components": row}]

def read_prices():
    if not os.path.exists(PRICES): return {}
    with open(PRICES) as f: prices = json.load(f)
    if not isinstance(prices, dict): raise ValueError("invalid price history; refusing reset")
    return prices

def price_drops(raws, now=None):
    """Compare to prices seen in earlier scans (state branch prices.json)."""
    now = now or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    old = read_prices()
    drops = []
    for it in raws:
        k = title_key(it["title"]); prev = old.get(k)
        if prev and it["price"] <= prev["price"] * (1 - DROP_PCT / 100):
            drops.append((it, prev))
        low = min(it["price"], prev.get("low", prev["price"])) if prev else it["price"]
        old[k] = {"price": it["price"], "low": low, "ts": now, "url": it["url"]}
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=45)).isoformat()
    old = {k: v for k, v in old.items() if v.get("ts", "") >= cutoff}   # keep 45 days
    return drops, old

def acquisition_status(raw):
    if raw.get('source') == 'ebay_browse':
        from .scanners.discovery import status
        return status(raw)
    return hotukdeals.live_status(raw['url'])


def route(raws, graded, stats, near, seen, dry=False, max_cards=5):
    """Post everything new. Returns keys to add to seen."""
    DELIVERY_FAILURES.clear()
    new = set()
    from .images import publishable
    raws,_=PF.partition(raws)
    graded=[(d,r) for d,r in graded if not PF.reason(vars(d))]
    original_raws=raws
    raws=[r for r in raws if publishable(r)]
    graded=[(d,r) for d,r in graded if publishable(vars(d))]
    # 1) graded A/B cards -> buy-now / verify + category channel
    n = 0
    for d, r in graded:
        g = r.grade[0]
        if g not in "AB" or r.cost > E.community_cap(): continue
        k = "alert:" + g + ":" + hotukdeals.dedupe_key(d.title, d.buy_price)
        if k in seen or n >= max_cards: continue
        card, comps = E.deal_card(d, r), E.link_buttons(d)
        st = send("buy-now" if g == "A" else "verify", card, comps, dry)
        ch = CAT_CHANNEL.get(d.category)
        if ch: send(ch, card[:1], comps, dry)
        if S.fast_route(g, d.category, d.days_to_sell): send("fast-movers", card[:1], comps, dry)
        if ok(st) or dry: new.add(k); n += 1
    # Separate ask-based CHECK path, never BUY / sold-verified / fast-mover.
    for it in raws:
        model = it.get("ask_estimate")
        if not model or not (model["estimated_opportunity"] or model.get("worth_reviewing")): continue
        k = ("estimated:" if model["estimated_opportunity"] else "review:") + hotukdeals.dedupe_key(it["title"], it["price"])
        if k in seen or n >= max_cards: continue
        if acquisition_status(it) != "live": continue
        st = send("verify", [watch_card(it, read_prices())], buttons(it), dry)
        if ok(st) or dry: new.add(k); n += 1
    # 2) price errors / very hot
    for it in raws:
        k = "pe:" + it["url"]
        if k in seen: continue
        if PRICE_ERROR_RE.search(it["title"]) or (it.get("heat") or 0) >= ERROR_HEAT:
            status = acquisition_status(it)
            if status == "expired": new.add(k); continue
            if status != "live": continue  # unknown must be retryable, never marked sent/expired
            st = send("price-errors", [mini(it, 0xF97316, "⚡ ")], buttons(it), dry)
            if ok(st) or dry: new.add(k)
    # 3) trending digest: new hot items, one message, up to 10
    hot = sorted([it for it in raws if (it.get("heat") or 0) >= TREND_MIN and "tr:" + it["url"] not in seen
                  and resellable(it) and not GROCERY_RE.search(it.get("merchant", ""))],
                 key=lambda x: -x["heat"])[:10]
    if hot:
        priced = {d.url for d, _ in graded}
        lines = [f"**{it['heat']}°** · {CAT_LABEL[it['category']]} · [{it['title'][:65]}]({it['url']}) · £{it['price']:.2f}"
                 + (" · priced, see the category feed" if it["url"] in priced else " · perfume transport conditional; see research/Price Check" if it["category"]=="fragrance" else f" · break even £{sell_needed(it['price'] + (it.get('inbound_delivery') or 0), it['category'])[0]:.2f}+" + (" (item-only; delivery unknown)" if it.get('inbound_delivery') is None else " (incl inbound delivery)"))
                 for it in hot]
        lego_hot=[mini(it,0xEF4444,"🔥 ") for it in hot if it["category"]=="lego"]
        lines=[line for line,it in zip(lines,hot) if it["category"]!="lego"]
        digest_embeds=([{"title": f"🌡️ Trending on hotukdeals · {len(hot)} new", "color": 0xEF4444,
                                "description": "\n".join(lines)[:4000], "footer": {"text": "Resellable items in our categories only · heat = community votes · breakeven after eBay fees, postage, packaging, returns"}}] if lines else [])+lego_hot
        st=send("trending",digest_embeds,None,dry)
        if ok(st) or dry: new |= {"tr:" + it["url"] for it in hot}
        for it in hot:   # hot items also go to their category channel
            ch = CAT_CHANNEL.get(it["category"])
            if ch and it["heat"] >= HOT_HEAT and "cat:" + it["url"] not in seen:
                if ok(send(ch, [mini(it, 0xEF4444, "🔥 ")], buttons(it), dry)) or dry: new.add("cat:" + it["url"])
    # 3b) WATCH cards: relevant new deals per category channel (no profit claimed)
    graded_urls = {d.url for d, r in graded if r.grade[0] in "AB"}
    prices_now = read_prices()
    per = {}
    for it in sorted(raws, key=lambda x: (x.get('source')=='ebay_browse',-x.get("review_priority", 0), -(x.get("heat") or 0))):
        ch = CAT_CHANNEL.get(it.get("category"))
        k = ("w:ask-model-v1:" if it.get("ask_estimate") else "w:") + it["url"]
        if not ch or k in seen or "cat:" + it["url"] in seen or it["url"] in graded_urls or not resellable(it): continue
        if per.get(ch, 0) >= WATCH_PER_CHANNEL: continue
        from .policy import current
        if it["price"] + (it.get("inbound_delivery") or 0) > current()["watch_ceiling"]: continue
        if re.search(r"in.?store|pre.?order|tester", it["title"], re.I): continue   # no car; no pre-orders or testers
        status = acquisition_status(it)
        if status == "expired": new.add(k); continue
        if status != "live": continue
        if ok(send(ch, [watch_card(it, prices_now)], buttons(it), dry)) or dry:
            new.add(k); per[ch] = per.get(ch, 0) + 1
    # 3c) quiet-market pulse: no A/B this scan -> one note per hour [H]
    n_drops = 0
    if not stats.get("A") and not stats.get("B") and not stats.get("estimated_opportunities"):
        qk = E.quiet_key()
        if qk not in seen and not (stats.get("errors") and not stats.get("scanned")):
            if ok(send("buy-now", [E.quiet_card(stats, market_pulse(original_raws, stats).split(chr(10))[0][:300])], None, dry)) or dry: new.add(qk)
    # 4) price drops
    drops, prices = price_drops(original_raws)
    for it, prev in [x for x in drops if resellable(x[0]) and publishable(x[0])][:5]:
        k = f"pd:{it['url']}:{it['price']}"
        if k in seen: continue
        e = mini(it, 0x06B6D4, "📉 ")
        e["description"] = f"**£{prev['price']:.2f} → £{it['price']:.2f}** (−{(1 - it['price'] / prev['price']) * 100:.0f}%) since {prev['ts'][:10]}\n" + e["description"].split("\n", 1)[1]
        if ok(send("price-drops", [e], buttons(it), dry)) or dry: new.add(k); n_drops += 1
    if not dry:
        from .evidence import atomic_write
        atomic_write(PRICES, prices)
    # 5) #bot-status: errors immediately, otherwise one summary per hour (the :07 run) [H]
    stats["errors"] = list(dict.fromkeys((stats.get("errors") or []) + DELIVERY_FAILURES))[:20]
    errs = stats["errors"]
    if errs or dt.datetime.now(dt.timezone.utc).minute < 30 or os.getenv("MONEYHUNTER_FORCE_STATUS") == "1":
        e = E.scan_summary(stats, near)
        e["fields"].insert(0, {"name":"Competitor-based resale estimates (NOT verified BUY)", "value":f"{stats.get('ask_valued',0)} offers estimated · {stats.get('estimated_opportunities',0)} strong / CHECK · {stats.get('worth_reviewing',0)} manual review · {stats.get('above_budget_estimates',0)} above-budget watch · {stats.get('ask_delivery_known',0)} known inbound / {stats.get('qualified_delivery_unknown',0)} unknown inbound · {stats.get('ask_unique_products',0)} distinct estimated products. A/B sold-evidence grades unchanged.","inline":False})
        e["fields"].append({"name": "📉 price-drops", "value": f"{n_drops} new this scan" + ("" if n_drops or os.path.exists(PRICES) else " · fills after a few days of price history"), "inline": True})
        e["fields"].insert(0, {"name": "📈 Market pulse (deals this scan)", "value": market_pulse(raws, stats)[:1000], "inline": False})
        if stats.get('source_coverage'):
            e['fields'].append({'name':'Retail feeds retained + complementary eBay acquisition',
                'value':' · '.join(f"{src}: {v['offers']} offers / {v['new']} new / {v['estimated']} estimated / {v['actionable']} CHECK or review" for src,v in stats['source_coverage'].items())[:1000],'inline':False})
        if stats.get('value_watchlist'):
            w=stats['value_watchlist'];a=stats.get('sources',{}).get('ebay_acquisition',{})
            e['fields'].append({'name':'Value-led watchlist (not buy approval)',
                'value':f"{w['products']} exact identities / {w['usable_targets']} fresh configured-cost targets; {a.get('price_led_queries',0)} price-targeted + {a.get('research_discovery_queries',0)} discovery searches. getItem {stats.get('item_details',{}).get('calls',0)}/4; shared 800/day cap.",'inline':False})
        if stats.get('pricing_coverage'):
            e['fields'].append({'name':'Exact pricing coverage (offers / estimated / distinct products)',
                'value':' · '.join(f"{cat}: {x['offers']}/{x['estimated_offers']}/{x['estimated_products']}" for cat,x in stats['pricing_coverage'].items())[:1000],'inline':False})
        if stats.get('warnings'):
            e['fields'].insert(0,{'name':'Warnings — scan continued safely','value':'\n'.join(stats['warnings'])[:1000],'inline':False})
        if errs:
            e["color"] = 0xEF4444; e["title"] = "⚠️ Scan problem · " + e["title"]
            e["fields"].insert(0, {"name": "Errors", "value": "\n".join(errs)[:1000], "inline": False})
        send("bot-status", [e], None, dry)
    stats["delivery_failures"] = len(DELIVERY_FAILURES)
    stats["errors"] = list(dict.fromkeys(stats["errors"] + DELIVERY_FAILURES))[:20]
    return new

def digest(deals_path, dry=False):
    """Daily 8am near-miss digest from the published deals.json."""
    d = json.load(open(deals_path))
    near = [x for x in d["deals"] if x["grade"] == "R"][:10]
    from .images import publishable
    near=[x for x in near if publishable(x)]
    lego_cards=[mini({**x,"price":x["buy"]},0xF59E0B,"🟠 ") for x in near if x.get("category")=="lego"]
    lines = [f"`{'✅' if x['under_cap'] else '£60+'}` [{x['title'][:60]}]({x['url']}) · £{x['buy']:.2f} → £{x['target']:.2f} · net {x['net']:+.2f} · max buy £{x['max_buy']:.2f} · {(x['why'] or ['-'])[0]}" for x in near if x.get("category")!="lego"]
    s = d["stats"]
    digest_embeds=([{"title": f"🟠 Daily near-miss digest · {dt.date.today():%a %d %b}", "color": 0xF59E0B,
        "description": ("Research candidates (may have major evidence blockers). The financial ceiling is not approval: exact evidence, delivery, availability and exit checks must also pass.\n\n" + "\n".join(lines))[:4000] if lines else "No priced near-misses in the last scan.",
        "footer": {"text": f"{s['scanned']} scanned · {s['priced']} priced · {s['A']} buy · {s['B']} verify"}}] if lines or not lego_cards else [])+lego_cards
    return send("near-misses",digest_embeds,None,dry)

def leaderboard(api_url, dry=False):
    with urllib.request.urlopen(urllib.request.Request(api_url, headers={"User-Agent": "moneyhunter"}), timeout=20) as r:
        lb = json.load(r)
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"{medals[i] if i < 3 else f'`{i+1}.`'} **{u['name'][:32]}** · {u['xp']} XP · {u['flips']} flips" for i, u in enumerate(lb.get("top", [])[:15])]
    return send("leaderboard", [{"title": f"🏆 Weekly leaderboard · w/c {dt.date.today():%d %b %Y}", "color": 0xEAB308,
        "description": "\n".join(lines) if lines else "No flips logged yet. Be first: use **Log a flip** in #flip-log.",
        "footer": {"text": "XP: 10 per logged flip + 1 per £ profit (max 200 per flip)"}}], None, dry)
