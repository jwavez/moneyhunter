#!/usr/bin/env python3
"""Task 14 Phase B — read-only eBay Browse clearance probe (Currys seller).

EXACTLY 5 Browse item_summary/search calls. Each call is gated by
research_budget.reserve (shared DAILY_LIMIT=800). Not wired into scans.
Outputs JSON summary + per-item fields for marketingPrice analysis.

Zero new spend: uses existing EBAY_CLIENT_ID / EBAY_CLIENT_SECRET.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Allow `PYTHONPATH=. python scripts/ebay_clearance_probe.py`
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from moneyhunter import research_budget  # noqa: E402
from moneyhunter.scanners import ebay as ebay_scanner  # noqa: E402

# ---- Fixed queries decided BEFORE any Browse call (do not reorder / re-run) ----
SELLER = "currys"
BASE_FILTER = (
    f"sellers:{{{SELLER}}},conditionIds:{{1000}},buyingOptions:{{FIXED_PRICE}},"
    "deliveryCountry:GB,priceCurrency:GBP"
)
MARKETPLACE = "EBAY_GB"
LIMIT = 200
PURPOSE = "clearance-probe"

QUERIES = [
    {
        "id": 1,
        "lane": "broad-electronics",
        "q": None,
        "category_ids": "293",
        "category_name": "Consumer Electronics",
        "rationale": "Broad top-level electronics; category_ids=293 satisfies Browse search without a free-text q",
    },
    {
        "id": 2,
        "lane": "headphones-audio",
        "q": "headphones",
        "category_ids": None,
        "category_name": None,
        "rationale": "moneyhunter audio/tech lane",
    },
    {
        "id": 3,
        "lane": "gaming",
        "q": "playstation",
        "category_ids": None,
        "category_name": None,
        "rationale": "moneyhunter gaming lane",
    },
    {
        "id": 4,
        "lane": "computing-laptops",
        "q": "laptop",
        "category_ids": None,
        "category_name": None,
        "rationale": "moneyhunter computing/tech lane",
    },
    {
        "id": 5,
        "lane": "small-appliances-home-tech",
        "q": "air fryer",
        "category_ids": None,
        "category_name": None,
        "rationale": "small appliances / home tech lane",
    },
]

assert len(QUERIES) == 5, "probe must define exactly 5 queries"


def _seed_state() -> dict:
    """Seed browse_usage from SCAN_STATE_JSON env or empty day bucket."""
    state: dict = {}
    raw = os.environ.get("SCAN_STATE_JSON", "").strip()
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict) and isinstance(loaded.get("browse_usage"), dict):
                state["browse_usage"] = dict(loaded["browse_usage"])
                bp = loaded["browse_usage"].get("by_purpose")
                if isinstance(bp, dict):
                    state["browse_usage"]["by_purpose"] = dict(bp)
        except json.JSONDecodeError:
            pass
    return state


def _localized_aspects(item: dict) -> dict:
    out = {}
    for a in item.get("localizedAspects") or []:
        name = (a.get("name") or "").strip()
        val = a.get("value")
        if name and val is not None:
            out[name] = val
    return out


def _identity_fields(item: dict) -> dict:
    aspects = _localized_aspects(item)
    brand = item.get("brand") or aspects.get("Brand") or aspects.get("brand")
    mpn = None
    for k in ("MPN", "Manufacturer Part Number", "Mpn"):
        if aspects.get(k):
            mpn = aspects[k]
            break
    gtin = None
    for k in ("EAN", "GTIN", "UPC", "ISBN"):
        if aspects.get(k):
            gtin = aspects[k]
            break
    # Browse sometimes puts GTIN on top-level gtin / epid
    if not gtin and item.get("gtin"):
        gtin = item.get("gtin")
    return {
        "brand": brand,
        "mpn": mpn,
        "gtin": gtin,
        "epid": item.get("epid"),
    }


def _money(obj) -> dict | None:
    if not isinstance(obj, dict):
        return None
    return {"value": obj.get("value"), "currency": obj.get("currency")}


def _record_item(item: dict) -> dict:
    mp = item.get("marketingPrice") or {}
    seller = (item.get("seller") or {})
    ident = _identity_fields(item)
    price = item.get("price") or {}
    disc = mp.get("discountPercentage")
    try:
        disc_f = float(disc) if disc is not None and str(disc) != "" else None
    except (TypeError, ValueError):
        disc_f = None
    return {
        "itemId": item.get("itemId"),
        "title": item.get("title"),
        "price": _money(price),
        "marketingPrice": {
            "originalPrice": _money(mp.get("originalPrice")),
            "discountPercentage": disc_f if disc_f is not None else mp.get("discountPercentage"),
            "discountAmount": _money(mp.get("discountAmount")),
            "priceTreatment": mp.get("priceTreatment"),
        }
        if mp
        else None,
        "condition": item.get("condition"),
        "conditionId": item.get("conditionId"),
        "seller": seller.get("username"),
        "itemWebUrl": item.get("itemWebUrl"),
        "brand": ident["brand"],
        "mpn": ident["mpn"],
        "gtin": ident["gtin"],
        "epid": ident["epid"],
        "discountPercentage_num": disc_f,
    }


def _search(query: dict) -> dict:
    params: dict = {"limit": str(LIMIT), "filter": BASE_FILTER}
    if query.get("q"):
        params["q"] = query["q"]
    if query.get("category_ids"):
        params["category_ids"] = query["category_ids"]
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + ebay_scanner._auth(),
            "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _median(xs: list[float]) -> float | None:
    return float(statistics.median(xs)) if xs else None


def main() -> int:
    if not ebay_scanner.available():
        print("ERROR: EBAY_CLIENT_ID / EBAY_CLIENT_SECRET missing", file=sys.stderr)
        return 2

    out_path = Path(os.environ.get("PROBE_OUT", "/workspace/ebay_clearance_probe.json"))
    when = datetime.now(timezone.utc)

    state = _seed_state()
    before = dict(state.get("browse_usage") or {})
    before_calls = int(before.get("calls") or 0)
    before_remaining = max(0, research_budget.DAILY_LIMIT - before_calls)

    per_query = []
    all_items = []
    calls_used = 0
    errors = []

    for q in QUERIES:
        if not research_budget.reserve(state, when, PURPOSE):
            errors.append({"query_id": q["id"], "error": "research_budget.reserve refused (cap reached)"})
            per_query.append(
                {
                    **{k: q[k] for k in ("id", "lane", "q", "category_ids", "category_name", "rationale")},
                    "reserved": False,
                    "http_ok": False,
                    "total": 0,
                    "returned": 0,
                    "items_with_marketingPrice": 0,
                    "items_discount_ge_40": 0,
                    "items_discount_ge_25": 0,
                }
            )
            continue
        calls_used += 1
        entry = {
            **{k: q[k] for k in ("id", "lane", "q", "category_ids", "category_name", "rationale")},
            "reserved": True,
            "filter": BASE_FILTER,
            "limit": LIMIT,
        }
        try:
            js = _search(q)
            summaries = js.get("itemSummaries") or []
            recorded = [_record_item(it) for it in summaries]
            discs = [r["discountPercentage_num"] for r in recorded if r.get("discountPercentage_num") is not None]
            entry.update(
                {
                    "http_ok": True,
                    "total": js.get("total"),
                    "returned": len(recorded),
                    "items_with_marketingPrice": sum(1 for r in recorded if r.get("marketingPrice")),
                    "items_discount_ge_40": sum(
                        1 for d in discs if d is not None and d >= 40
                    ),
                    "items_discount_ge_25": sum(
                        1 for d in discs if d is not None and d >= 25
                    ),
                    "items": recorded,
                }
            )
            all_items.extend(recorded)
        except Exception as e:
            # Counted call; record failure honestly (no retry / no extra call)
            entry.update(
                {
                    "http_ok": False,
                    "error": f"{type(e).__name__}: {e}",
                    "total": 0,
                    "returned": 0,
                    "items_with_marketingPrice": 0,
                    "items_discount_ge_40": 0,
                    "items_discount_ge_25": 0,
                    "items": [],
                }
            )
            errors.append({"query_id": q["id"], "error": entry["error"]})
        per_query.append(entry)

    after = dict(state.get("browse_usage") or {})
    after_calls = int(after.get("calls") or 0)
    after_remaining = max(0, research_budget.DAILY_LIMIT - after_calls)

    # Unique by itemId
    by_id = {}
    for it in all_items:
        iid = it.get("itemId")
        if iid and iid not in by_id:
            by_id[iid] = it
    unique = list(by_id.values())

    discs_all = [
        u["discountPercentage_num"]
        for u in unique
        if u.get("discountPercentage_num") is not None
    ]
    with_mp = [u for u in unique if u.get("marketingPrice")]
    ge40 = [u for u in unique if (u.get("discountPercentage_num") or -1) >= 40]
    ge25 = [u for u in unique if (u.get("discountPercentage_num") or -1) >= 25]

    def has_identity(u: dict) -> bool:
        return bool(u.get("brand") or u.get("mpn") or u.get("gtin") or u.get("epid"))

    identity_n = sum(1 for u in unique if has_identity(u))

    top5 = sorted(
        [u for u in unique if u.get("discountPercentage_num") is not None],
        key=lambda u: (-(u["discountPercentage_num"] or 0), u.get("title") or ""),
    )[:5]

    summary = {
        "calls_used": calls_used,
        "calls_planned": 5,
        "items_returned": len(all_items),
        "unique_items": len(unique),
        "items_with_marketingPrice": len(with_mp),
        "items_discount_ge_40": len(ge40),
        "items_discount_ge_25": len(ge25),
        "discount_pct_distribution": {
            "n": len(discs_all),
            "min": min(discs_all) if discs_all else None,
            "median": _median(discs_all),
            "max": max(discs_all) if discs_all else None,
        },
        "per_query_counts": [
            {
                "id": e["id"],
                "lane": e["lane"],
                "q": e.get("q"),
                "category_ids": e.get("category_ids"),
                "reserved": e.get("reserved"),
                "http_ok": e.get("http_ok"),
                "total": e.get("total"),
                "returned": e.get("returned"),
                "items_with_marketingPrice": e.get("items_with_marketingPrice"),
                "items_discount_ge_40": e.get("items_discount_ge_40"),
                "items_discount_ge_25": e.get("items_discount_ge_25"),
                "error": e.get("error"),
            }
            for e in per_query
        ],
        "share_with_identity_fields": {
            "count": identity_n,
            "unique_items": len(unique),
            "share": (identity_n / len(unique)) if unique else None,
        },
        "budget_before": {
            "date": before.get("date"),
            "calls": before_calls,
            "remaining": before_remaining,
            "daily_limit": research_budget.DAILY_LIMIT,
            "by_purpose": before.get("by_purpose"),
        },
        "budget_after": {
            "date": after.get("date"),
            "calls": after_calls,
            "remaining": after_remaining,
            "daily_limit": research_budget.DAILY_LIMIT,
            "by_purpose": after.get("by_purpose"),
        },
        "seller_filter": SELLER,
        "marketplace": MARKETPLACE,
        "cost": {
            "total_new_spend_gbp": 0,
            "ebay_browse_free_tier_used": "5 calls out of 5,000/day",
            "app_shared_cap": f"{calls_used} calls out of {research_budget.DAILY_LIMIT}/day",
        },
    }

    payload = {
        "generated_at": when.isoformat(),
        "purpose": PURPOSE,
        "queries_locked_before_run": QUERIES,
        "base_filter": BASE_FILTER,
        "summary": summary,
        "top5_by_discount_pct": [
            {
                "itemId": t.get("itemId"),
                "title": t.get("title"),
                "price": t.get("price"),
                "discountPercentage": t.get("discountPercentage_num"),
                "marketingPrice": t.get("marketingPrice"),
                "seller": t.get("seller"),
                "itemWebUrl": t.get("itemWebUrl"),
                "brand": t.get("brand"),
                "mpn": t.get("mpn"),
                "gtin": t.get("gtin"),
            }
            for t in top5
        ],
        "errors": errors,
        "items_unique": unique,
        "notes": {
            "seller_username": SELLER,
            "alternate_clearance_username": "currys_clearance",
            "alternate_note": (
                "Public eBay store pages list currys (main) and currys_clearance (outlet). "
                "This probe used sellers:{currys} + NEW as specified; did not call currys_clearance."
            ),
            "state_mutation": (
                "Reserved against an in-memory browse_usage copy seeded from SCAN_STATE_JSON when provided; "
                "does not write back to the origin/state branch."
            ),
            "marketingPrice_semantics": "Seller was-price / eBay discount treatment; not manufacturer RRP.",
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    # Also write a repo-relative copy when running in Actions
    rel = Path("ebay_clearance_probe.json")
    rel.write_text(out_path.read_text())
    print(json.dumps({"ok": True, "out": str(out_path), "summary": summary}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
