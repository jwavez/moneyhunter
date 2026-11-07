"""Automatic indicative ACTIVE asks, isolated from all sold/evidence/grading inputs.

Original implementation of identity-keyed caching/explicit capability concepts
reviewed in listing-monitor and ebay-sniper; see docs/OPEN_SOURCE_RESEARCH.md.
"""
import datetime as dt
import math
import hashlib
import json
import unicodedata
import re
from collections import Counter
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from . import matching as M
from .scanners import ebay
from . import variants, research_budget

TTL_HOURS = 6
CALL_BUDGET = 12
# Set numbers also occur on instruction sheets, stickers and individual components.
# Name anchors reduce that ambiguity; they are research filters, never sold evidence.
LEGO_NOISE = set("lego new sealed brand boxed box genuine original official complete set sets building build toy toys free delivery click collect c code voucher discount checkout at and the of with inc incl includes including star wars technic ideas speed champions smart play super car pokemon".split())


def lego_terms(title):
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return sorted({w for w in M.norm(text).split() if w not in LEGO_NOISE and
                   not re.fullmatch(r"\d{5,6}", w) and len(w) > 1})


def cache_key(ident):
    # A contradictory name attached to the same numeric SKU cannot inherit context.
    fingerprint = hashlib.sha256(json.dumps(getattr(ident, "variant", getattr(ident, "name_terms", [])),sort_keys=True).encode()).hexdigest()[:12]
    return "browse-asks-v5:" + ident.category + ":" + ident.match.lower() + ":" + fingerprint


def canonical_game(title):
    t=re.split(r"\s(?:@|at)\s|\s+with code|\s+w/",title,maxsplit=1,flags=re.I)[0]
    t=re.sub(r"[£]\s?\d+(?:\.\d{1,2})?",'',t)
    t=re.sub(r"\b(?:brand new(?: and)? sealed|new and sealed|brand new|new sealed|physical copy|in stock)\b|free (?:shipping|delivery|c&c|click (?:and|&) collect|p\s*&\s*p)",'',t,flags=re.I)
    t=M.norm(t)
    t=re.sub(r'\bplaystation ([45])\b',r'ps\1',t)
    # Descriptor adjacent to a platform, never an arbitrary word in the game name.
    t=re.sub(r'\b(ps[45]|xbox series x s|xbox series x|nintendo switch 2|nintendo switch) game\b',r'\1',t)
    platforms=re.findall(r'\bps[45]\b|\bxbox series x s\b|\bxbox series x\b|\bxbox one\b|\bnintendo switch 2\b|\bnintendo switch\b',t)
    if len(set(platforms))==1:
        platform=platforms[0];t=re.sub(r'\b'+re.escape(platform)+r'\b','',t)
        t=' '.join(t.split())+' '+platform
    return ' '.join(t.split())


def identity(raw):
    """Bounded, title-derived research identities, not human-reviewed product facts."""
    from . import product_format as PF
    if PF.reason(raw):return None
    raw=PF.normalize(raw)
    title, cat = raw.get("title", ""), raw.get("category")
    t = M.norm(title)
    if M.has(t, *M.CONDITION, *M.BUNDLE, *M.PREORDER, "digital", "download", "code in a box", "dlc", "compatible", "replica", "moc") or M._multipack(t):
        return None
    if cat == 'gaming' and M.has(t,'key','keycode','activation','steam','account','digital code','cd key','download code'):
        return None  # actual first live acquisition probe surfaced an Xbox digital key
    extra = variants.identity(raw)
    if extra: return extra
    # A structured model rejected for ambiguous colour/condition must not fall back
    # to the older less-specific model matcher (e.g. Pink OR Black XM5).
    if cat=='tech' and re.search(r'\b(?:wh[ -]?(?:ch[ -]?520|1000xm[45])|wf[ -]?c[ -]?(?:510|710n))\b',title,re.I):return None
    name_terms = []
    if cat == "lego":
        name_terms = lego_terms(title)
        if not name_terms: return None
        ids = set(re.findall(r"(?<!\d)\d{5,6}(?!\d)", title))
        if len(ids) != 1 or not M.has(t, "lego"): return None
        set_number=next(iter(ids))
        # Reviewed same-set anchor: promotional title wording must not fragment Munchlax.
        if set_number=='72150' and M.has(t,'munchlax'):name_terms=['munchlax']
        query = "LEGO " + set_number
    elif cat == "gaming":
        # Preserve platform/edition. Too much promotional noise means no lookup,
        # rather than over-aggressively deleting words from the actual game name.
        query = canonical_game(title)
        platforms = [p for p in ("ps4", "ps5", "xbox", "switch", "pc") if M.has(M.norm(query), p)]
        if len(platforms) != 1 or platforms[0] == "pc" or len(query.split()) < 4 or len(query) > 100:
            return None
    elif cat == 'tech':
        # Deliberately narrow exact model + explicit colour, never a generic headphone search.
        code = re.search(r'\bwh[ -]?1000xm[45]\b', title, re.I)
        colours = [v for v in ('black','silver','blue') if M.has(t,v)]
        if not code or not M.has(t,'sony') or len(colours) != 1: return None
        query = 'Sony ' + re.sub('[ -]', '',code.group()).upper() + ' ' + colours[0]
    else:
        return None  # unreviewed bottle/tool/clothing variants are not guessed
    c = SimpleNamespace(match=query, category=cat, identity={"condition": "new"}, name_terms=name_terms)
    if not matches(title, c): return None
    return c


def matches(title, ident):
    from . import product_format as PF
    if PF.reason({'title':title}):return False
    if hasattr(ident,"variant"): return variants.matches(title,ident)
    t = M.norm(title)
    if ident.category=='gaming':
        wanted=canonical_game(ident.match)
        if canonical_game(title)!=wanted:return False
        checked=SimpleNamespace(match=wanted,category=ident.category,identity=ident.identity)
        return M.check(title,'',checked)==''
    if ident.category == 'tech':
        wanted = re.sub(r'[^a-z0-9]', '',ident.match.lower())
        actual = re.sub(r'[^a-z0-9]', '',title.lower())
        if not all(word in actual for word in re.findall(r'sony|wh1000xm[45]|black|silver|blue',wanted)): return False
        if M.has(t,'case','cover','earpad','ear pads','replacement','headband','charger','charging','dock','cable','earcups','parts','repair','broken','spares','compatible','used','refurbished','renewed','open box'): return False
        if sum(M.has(t,c) for c in ('black','silver','blue')) != 1: return False
        return not M.has(t,*M.CONDITION,*M.BUNDLE,*M.PREORDER)
    if M.has(t, "instructions", "manual only", "box only", "empty box", "light kit", "lighting kit", "led kit", "display case", "parts only", "spares", "stickers", "compatible", "replica", "moc"):
        return False
    if ident.category == "lego":
        # Real Browse examples: "Minecraft Baby Pig From Set 21268 Item ...".
        # Number and franchise/name words do not make a component the whole set.
        if re.search(r"\b(?:from|out of)\s+(?:(?:the|a|lego)\s+)*(?:(?:set|sets)\s+)?\d{5,6}\b", t) or M.has(t, "taken from", "removed from"):
            return False
        if M.has(t, "instruction", "manual", "manuals", "booklet", "booklets", "sticker", "stickers", "sheet", "sheets", "minifigure", "minifig", "minifigures", "minifigs", "parts", "spare", "replacement", "bag", "bags", "missing", "without", "incomplete", "for lego", "display stand", "display base", "display mount", "wall mount", "wall bracket", "mounting bracket", "display plinth", "acrylic", "light", "lights", "lighting", "led", "tag", "tags"):
            return False
        terms = getattr(ident, "name_terms", [])
        if terms:
            normalized = M.norm(unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode())
            if sum(M.has(normalized, word) for word in terms) < min(2, len(terms)):
                return False
    return M.check(title, "", ident) == ""


def money(value):
    if not isinstance(value, dict) or value.get("currency") != "GBP": return None
    try:
        n = float(value["value"])
        return n if math.isfinite(n) and n >= 0 else None
    except (KeyError, TypeError, ValueError): return None


def summary(payload, ident, when):
    rejected, seen, offers = Counter(), set(), []
    for item in payload.get("itemSummaries", [])[:50]:
        key = item.get("itemId")
        if not key or key in seen:
            rejected["duplicate_or_missing_id"] += 1; continue
        seen.add(key)
        if str(item.get("conditionId")) != "1000" or not matches(item.get("title", ""), ident):
            rejected["identity_or_condition"] += 1; continue
        if item.get("lotSize") not in (None, 1, "1") or item.get("itemGroupHref") or item.get("itemGroupType"):
            rejected["multi_variant_listing"] += 1; continue
        if item.get("itemLocation", {}).get("country") != "GB":
            rejected["location_unknown_or_non_gb"] += 1; continue
        end = item.get("itemEndDate")
        if end:
            try:
                if dt.datetime.fromisoformat(end.replace("Z", "+00:00")) <= when:
                    rejected["ended"] += 1; continue
            except (ValueError, TypeError):
                rejected["invalid_end_date"] += 1; continue
        price = money(item.get("price"))
        shipping = [money(s.get("shippingCost")) for s in item.get("shippingOptions", []) if s.get("shippingCostType") == "FIXED"]
        shipping = [v for v in shipping if v is not None]
        if price is None or price <= 0 or not shipping:
            rejected["price_currency_or_shipping_unknown"] += 1; continue
        url = urlsplit(item.get("itemWebUrl", ""))
        if url.scheme != "https" or url.username or url.password or url.hostname not in ("www.ebay.co.uk", "www.ebay.com") or not url.path.startswith("/itm/"):
            rejected["source_url_unknown"] += 1; continue
        from .images import safe
        image = safe((item.get("image") or {}).get("imageUrl"))
        seller = (item.get("seller") or {}).get("username")
        marketing = item.get("marketingPrice") or {}
        original = money(marketing.get("originalPrice"))
        try: percentage = float(marketing.get("discountPercentage") or 0)
        except (ValueError, TypeError): percentage = 0
        discounted = (original is not None and original > price) or percentage > 0 or (money(marketing.get("discountAmount")) or 0) > 0
        offers.append({"item_id": str(key), "seller": str(seller)[:100] if seller else None,
            "image":image,"country": "GB", "currency": "GBP", "condition_id": "1000", "discount_status": "advertised_discount" if discounted else "unknown",
            "advertised_original_total": round(original + min(shipping), 2) if original is not None and original > price else None,
            "available_coupons": item.get("availableCoupons") is True,
            "buying_options":item.get("buyingOptions",[]),"end_at":end,"promotion_id": None, "url": urlunsplit((url.scheme, url.netloc, url.path, "", "")), "title": item.get("title", "")[:200],
            "declared_condition": "new", "item_price": price, "shipping": min(shipping), "listed_total": round(price + min(shipping), 2)})
    xs = sorted(o["listed_total"] for o in offers)
    q = lambda p: round(ebay._pct(xs, p), 2) if xs else None
    spread = bool(xs and xs[-1] > xs[0] * 1.5)
    return {"kind": "active_ask", "query": ident.match, "category": ident.category, "name_terms": getattr(ident, "name_terms", []),
        "identity":ident.identity,"observed_at": when.isoformat(timespec="seconds"), "date": when.date().isoformat(), "sample_count": len(xs),
        "listed_total_low": xs[0] if xs else None, "listed_total_p25": q(.25),
        "listed_total_median": q(.5), "listed_total_p75": q(.75), "listed_total_high": xs[-1] if xs else None,
        "status": "no_exact_shipped_samples" if not xs else "small_sample" if len(xs) < 3 else "wide_spread" if spread else "indicative_only",
        "warnings": ["Active asking totals, NOT sold prices or a resale prediction. Buyer-only fees may be additional.",
                     "Title-derived identity with product-name filters, not independently reviewed. No demand, velocity or cash floor inferred."] + (["Wide spread: variants/outliers may remain; no values silently discarded."] if spread else []),
        "offers": sorted(offers, key=lambda x: x["listed_total"])[:50], "rejected": dict(rejected)}


def revalidate(snapshot, ident, when):
    """Reclassify retained real observations after matcher repairs, without refreshing their clock."""
    if snapshot.get("kind") != "active_ask" or not snapshot.get("offers"): return snapshot
    good = [o for o in snapshot["offers"] if matches(o.get("title", ""), ident)]
    removed = [o for o in snapshot["offers"] if not matches(o.get("title", ""), ident)]
    if not removed: return snapshot
    xs = sorted(o["listed_total"] for o in good)
    q = lambda p: round(ebay._pct(xs, p), 2) if xs else None
    spread = bool(xs and xs[-1] > xs[0]*1.5)
    rejected = dict(snapshot.get("rejected", {}))
    rejected["accessory_reclassified"] = rejected.get("accessory_reclassified", 0)+len(removed)
    return {**snapshot, "offers":good, "sample_count":len(good), "rejected":rejected,
        "excluded_after_review":(snapshot.get("excluded_after_review", [])+removed)[:50],
        "reclassified_at":when.isoformat(timespec="seconds"),
        "listed_total_low":xs[0] if xs else None,"listed_total_p25":q(.25),"listed_total_median":q(.5),
        "listed_total_p75":q(.75),"listed_total_high":xs[-1] if xs else None,
        "status":"no_exact_shipped_samples" if not xs else "small_sample" if len(xs)<3 else "wide_spread" if spread else "indicative_only"}


def enrich(candidates, raws, state, when=None, budget=CALL_BUDGET, lane="asking"):
    """Rotate absent/oldest research keys, reuse six-hour snapshots, never alter grades."""
    when = when or dt.datetime.now(dt.timezone.utc)
    cache = state["ask_cache"]
    health = {"purpose": "indicative current asks only; not sold valuation", "queries": 0, "cached": 0,
              "query_budget":budget,"queries_by_category":{},"candidates_with_samples": 0, "status": "ready" if ebay.available() else "unavailable_no_keys", "errors": []}
    by_url = {r["url"]: r for r in raws}
    pending = {}
    for c in candidates:
        ident = identity(by_url.get(c["url"], {}))
        if ident:
            c["ask_status"] = "awaiting_query_budget" if ebay.available() else "unavailable_no_keys"
            k = cache_key(ident)
            pending.setdefault(k, (ident, []))[1].append(c)
        else: c["ask_status"] = "exact_identity_not_supported"
    def age(entry):
        try: return (when-dt.datetime.fromisoformat(entry["observed_at"])).total_seconds()/3600
        except (KeyError, TypeError, ValueError): return float("inf")
    rotation=state.setdefault('research_rotation',{})
    ordered=research_budget.fair_order(pending.items(),lambda kv:kv[1][0].category,
        lambda kv:(-int(any(by_url.get(r['url'],{}).get('source')!='ebay_browse' for r in kv[1][1])),-age(cache.get(kv[0],{})),-max(r.get('priority',0) for r in kv[1][1]),kv[0]),rotation.get(lane,0))
    for k, (ident, rows) in ordered:
        snapshot = cache.get(k, {})
        checked = revalidate(snapshot, ident, when)
        if checked is not snapshot: cache[k] = checked; snapshot = checked
        hours = age(snapshot)
        fresh = snapshot.get("kind") == "active_ask" and 0 <= hours < TTL_HOURS
        # A newly acquired candidate cannot rely on a pre-existing competition snapshot:
        # refresh ALL sellers, not just the business-only acquisition response.
        acquisition_rows = [by_url.get(c['url'],{}) for c in rows]
        newer_acquisition = any(r.get('source') == 'ebay_browse' and r.get('source_observed_at','') > snapshot.get('observed_at','') for r in acquisition_rows)
        if newer_acquisition: fresh = False
        if fresh: health["cached"] += 1
        blocked = cache.get("browse-blocked")
        if not fresh and blocked:
            health["status"] = "paused_operator_review_required"
            for c in rows: c["ask_status"] = health["status"]
        elif not fresh and ebay.available() and health["queries"] < budget:
            # Failure cache prevents repeated query storms; permanent permission failures
            # stop ALL subsequent calls until an operator explicitly clears the marker.
            if snapshot.get("kind") == "ask_error" and 0 <= hours < .25: continue
            if not research_budget.reserve(state,when,lane):
                health['status']='daily_budget_exhausted';continue
            health['queries'] += 1
            health['queries_by_category'][ident.category]=health['queries_by_category'].get(ident.category,0)+1
            rotation[lane]=rotation.get(lane,0)+1
            try:
                snapshot = summary(ebay.active_items(ident.match), ident, when)
                cache[k] = snapshot
                fresh = True
            except Exception as exc:
                code = getattr(exc, "code", None)
                error = f"Active ask lookup failed: {type(exc).__name__}" + (f" HTTP {code}" if code else "")
                health["errors"].append(error)
                cache[k] = {"kind": "ask_error", "observed_at": when.isoformat(), "date": when.date().isoformat(), "error": error}
                if code in (401, 403, 429):
                    cache["browse-blocked"] = {"kind": "source_paused", "date": when.date().isoformat(), "status": code}
                    health["status"] = "paused_operator_review_required"
        if fresh:
            from . import details
            snapshot=details.inspect_snapshot(snapshot,ident,state,when)
            cache[k]=snapshot
            for c in rows:
                c["ask_context"] = {**details.for_acquisition(snapshot,by_url.get(c["url"],{}),ident,state,when),"query_aliases":sorted({by_url[r["url"]]["title"] for r in rows})}
                c["ask_status"] = snapshot["status"]
                if snapshot["sample_count"]: health["candidates_with_samples"] += 1
    if health["errors"] and health["status"] == "ready": health["status"] = "partial_failure"
    return health
