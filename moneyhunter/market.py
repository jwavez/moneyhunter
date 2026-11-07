"""Automatic indicative ACTIVE asks, isolated from all sold/evidence/grading inputs.

Original implementation of identity-keyed caching/explicit capability concepts
reviewed in listing-monitor and ebay-sniper; see docs/OPEN_SOURCE_RESEARCH.md.
"""
import datetime as dt
import math
import re
from collections import Counter
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from . import matching as M
from .scanners import ebay

TTL_HOURS = 6
CALL_BUDGET = 6


def identity(raw):
    """Bounded, title-derived research identities, not human-reviewed product facts."""
    title, cat = raw.get("title", ""), raw.get("category")
    t = M.norm(title)
    if M.has(t, *M.CONDITION, *M.BUNDLE, *M.PREORDER, "digital", "download", "code in a box", "dlc", "compatible", "replica", "moc") or M._multipack(t):
        return None
    if cat == "lego":
        ids = set(re.findall(r"(?<!\d)\d{5,6}(?!\d)", title))
        if len(ids) != 1 or not M.has(t, "lego"): return None
        query = "LEGO " + next(iter(ids))
    elif cat == "gaming":
        # Preserve platform/edition. Too much promotional noise means no lookup,
        # rather than over-aggressively deleting words from the actual game name.
        title = re.split(r"\s(?:@|at)\s|\s+with code|\s+w/", title, maxsplit=1, flags=re.I)[0]
        title = re.sub(r"[£]\s?\d+(?:\.\d{1,2})?", "", title)
        title = re.sub(r"free (?:delivery|c&c)|new sealed|physical copy", "", title, flags=re.I)
        query = " ".join(M.norm(title).split())
        platforms = [p for p in ("ps4", "ps5", "xbox", "switch", "pc") if M.has(M.norm(query), p)]
        if len(platforms) != 1 or platforms[0] == "pc" or len(query.split()) < 4 or len(query) > 100:
            return None
    else:
        return None  # shoes, tools, fragrances need more exact reviewed attributes
    c = SimpleNamespace(match=query, category=cat, identity={"condition": "new"})
    if not matches(title, c): return None
    return c


def matches(title, ident):
    t = M.norm(title)
    if M.has(t, "instructions", "manual only", "box only", "empty box", "light kit", "lighting kit", "led kit", "display case", "parts only", "spares", "stickers", "compatible", "replica", "moc"):
        return False
    if ident.category == "lego" and M.has(t, "minifigure", "minifig", "minifigures", "minifigs", "parts", "spare", "replacement", "bag", "bags", "missing", "without", "incomplete", "for lego"):
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
        if item.get("itemGroupHref") or item.get("itemGroupType"):
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
        offers.append({"url": urlunsplit((url.scheme, url.netloc, url.path, "", "")), "listed_total": round(price + min(shipping), 2)})
    xs = sorted(o["listed_total"] for o in offers)
    q = lambda p: round(ebay._pct(xs, p), 2) if xs else None
    spread = bool(xs and xs[-1] > xs[0] * 1.5)
    return {"kind": "active_ask", "query": ident.match, "category": ident.category,
        "observed_at": when.isoformat(timespec="seconds"), "date": when.date().isoformat(), "sample_count": len(xs),
        "listed_total_low": xs[0] if xs else None, "listed_total_p25": q(.25),
        "listed_total_median": q(.5), "listed_total_p75": q(.75), "listed_total_high": xs[-1] if xs else None,
        "status": "no_exact_shipped_samples" if not xs else "small_sample" if len(xs) < 3 else "wide_spread" if spread else "indicative_only",
        "warnings": ["Active asking totals, NOT sold prices or a resale prediction. Buyer-only fees may be additional.",
                     "Title-derived identity, not independently reviewed. No demand, velocity or cash floor inferred."] + (["Wide spread: variants/outliers may remain; no values silently discarded."] if spread else []),
        "offers": sorted(offers, key=lambda x: x["listed_total"])[:3], "rejected": dict(rejected)}


def enrich(candidates, raws, state, when=None, budget=CALL_BUDGET):
    """Rotate absent/oldest research keys, reuse six-hour snapshots, never alter grades."""
    when = when or dt.datetime.now(dt.timezone.utc)
    cache = state["ask_cache"]
    health = {"purpose": "indicative current asks only; not sold valuation", "queries": 0, "cached": 0,
              "candidates_with_samples": 0, "status": "ready" if ebay.available() else "unavailable_no_keys", "errors": []}
    by_url = {r["url"]: r for r in raws}
    pending = {}
    for c in candidates:
        ident = identity(by_url.get(c["url"], {}))
        if ident:
            c["ask_status"] = "awaiting_query_budget" if ebay.available() else "unavailable_no_keys"
            k = "browse-asks-v2:" + ident.category + ":" + ident.match.lower()
            pending.setdefault(k, (ident, []))[1].append(c)
        else: c["ask_status"] = "exact_identity_not_supported"
    def age(entry):
        try: return (when-dt.datetime.fromisoformat(entry["observed_at"])).total_seconds()/3600
        except (KeyError, TypeError, ValueError): return float("inf")
    for k, (ident, rows) in sorted(pending.items(), key=lambda kv: (-age(cache.get(kv[0], {})), -max(r.get("priority", 0) for r in kv[1][1]), kv[0])):
        snapshot = cache.get(k, {})
        hours = age(snapshot)
        fresh = snapshot.get("kind") == "active_ask" and 0 <= hours < TTL_HOURS
        if fresh: health["cached"] += 1
        blocked = cache.get("browse-blocked")
        if not fresh and blocked:
            health["status"] = "paused_operator_review_required"
            for c in rows: c["ask_status"] = health["status"]
        elif not fresh and ebay.available() and health["queries"] < budget:
            # Failure cache prevents repeated query storms; permanent permission failures
            # stop ALL subsequent calls until an operator explicitly clears the marker.
            if snapshot.get("kind") == "ask_error" and 0 <= hours < .25: continue
            health["queries"] += 1
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
            for c in rows:
                c["ask_context"] = snapshot
                c["ask_status"] = snapshot["status"]
                if snapshot["sample_count"]: health["candidates_with_samples"] += 1
    if health["errors"] and health["status"] == "ready": health["status"] = "partial_failure"
    return health
