"""Read-only trainers pipeline diagnostic. Never changes gates, parsers, allocation, or routing."""
from __future__ import annotations

import json
import re
import traceback
from pathlib import Path

from . import details, market, matching as M, publication, variants

STAGES = (
    "identity_not_supported",
    "identity_ambiguous",
    "no_comparators_found",
    "no_risky_lowest",
    "detail_check_pending",
    "detail_check_failed",
    "comparator_depth_insufficient",
    "comparator_support_insufficient",
    "shipping_unknown",
    "coupon_unresolved",
    "economics_negative",
    "publication_qualified",
    "above_budget",
    "other",
)


def _lookup(rows, url):
    for row in rows or []:
        if row.get("url") == url:
            return row
    return None


# Deterministic trainer brand labels (diagnostic only; does not change identity lanes).
NAMED_TRAINER_BRANDS = (
    "new balance",
    "helly hansen",
    "under armour",
    "on running",
    "nike",
    "adidas",
    "asics",
    "reebok",
    "vans",
    "puma",
    "saucony",
    "veja",
    "skechers",
    "boss",
    "hoka",
    "fila",
    "converse",
    "salomon",
    "brooks",
)


def parse_trainer_brand(title):
    """Map a trainer title to a deterministic brand label.

    Named brands (case-insensitive) → canonical lowercase name.
    Other identifiable footwear → "other".
    Empty / unidentifiable → "unknown".
    Label only: does not change identity matching or lanes.
    """
    if title is None:
        return "unknown"
    raw = str(title).strip()
    if not raw:
        return "unknown"
    cleaned = variants.clean(raw)
    # Prefer longer multi-word brands first.
    for brand in NAMED_TRAINER_BRANDS:
        parts = brand.split()
        if len(parts) == 1:
            if M.has(cleaned, parts[0]):
                return brand
        else:
            # All tokens must appear (order-tolerant via has).
            if all(M.has(cleaned, part) for part in parts):
                # "on running" requires both tokens to reduce false positives.
                if brand == "on running" and not (
                    re.search(r"\bon\b", cleaned) and re.search(r"\brunning\b", cleaned)
                ):
                    continue
                return brand
    # Identifiable footwear brand/product language but not in the named list.
    if re.search(r"\b(?:shoe|shoes|trainer|trainers|sneaker|sneakers|boot|boots)\b", cleaned, re.I) or re.search(
        r"\buk\s*(?:size\s*)?\d", raw, re.I
    ):
        return "other"
    return "unknown"


def _brand_parsed(offer, ident=None):
    # Prefer title parse so ASICS/etc. are consistent even when identity brand is Nike/adidas-only.
    title = (offer or {}).get("title") or ""
    parsed = parse_trainer_brand(title)
    if parsed != "unknown":
        return parsed
    if ident is not None:
        brand = (getattr(ident, "variant", None) or {}).get("brand")
        if brand:
            return parse_trainer_brand(str(brand))
    return "unknown"


def _identity_match_result(offer):
    """Reuse market.identity; classify None as ambiguous vs not_supported without changing parser."""
    try:
        ident = market.identity(offer)
    except Exception:
        return "not_supported", None, None
    if ident:
        return "matched", str(getattr(ident, "match", None) or None), ident

    # Diagnostic-only signals mirroring variants.trainer rejection modes.
    title = offer.get("title") or ""
    t = variants.clean(title)
    brand = "Nike" if M.has(t, "nike") else "adidas" if M.has(t, "adidas") else None
    if not brand:
        return "not_supported", None, None
    pattern = r"[A-Z]{2}\d{4}-\d{3}" if brand == "Nike" else r"[A-Z]{2}\d{4}"
    text = title + " " + (offer.get("desc") or "")
    codes = {s.upper() for s in re.findall(r"\b" + pattern + r"\b", text, re.I)}
    sizes = re.findall(r"\buk\s*(?:size\s*)?(\d{1,2}(?:\.5)?)\b", title, re.I) + re.findall(
        r"\b(\d{1,2}(?:\.5)?)\s*uk\b", title, re.I
    )
    multi = re.search(
        r"\buk\s*(?:size\s*)?\d+(?:\.5)?\s*(?:[-/,&]|or|to)\s*\d", title, re.I
    ) or M.has(t, "sizes", "choose size", "various sizes", "select size")
    genders = [
        g
        for g, terms in [
            ("women", ("women", "womens", "woman", "ladies")),
            ("men", ("men", "mens", "man")),
            ("unisex", ("unisex",)),
        ]
        if M.has(t, *terms)
    ]
    if len(codes) > 1 or multi or len(set(sizes)) > 1 or len(genders) > 1:
        return "ambiguous", None, None
    return "not_supported", None, None


def _merchant_price(offer, research=None):
    for src in (offer, research or {}):
        for key in ("price", "item_price", "buy_price"):
            val = src.get(key) if isinstance(src, dict) else None
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return float(val)
    return None


def _merged_row(offer, research):
    row = dict(offer or {})
    if research:
        for key in ("ask_estimate", "ask_context", "publication_proof", "ask_status"):
            if not row.get(key) and research.get(key) is not None:
                row[key] = research[key]
        if row.get("price") is None and research.get("item_price") is not None:
            row["price"] = research.get("item_price")
        if not row.get("title") and research.get("title"):
            row["title"] = research["title"]
        if not row.get("category") and research.get("category"):
            row["category"] = research["category"]
    return row


def _slot_events_for(identity):
    if not identity:
        return []
    return [e for e in details.SLOT_EVENTS if e.get("identity") == identity]


def _getitem_flags(identity):
    evs = _slot_events_for(identity)
    granted = any(e.get("getitem_granted") for e in evs)
    cached = any(e.get("denial_reason") == "cache_hit" for e in evs)
    denied_slots = any(e.get("denial_reason") == "slots_exhausted" for e in evs)
    not_risky = any(
        e.get("phase") == "inspect_skip" or e.get("denial_reason") == "not_risky_lowest"
        for e in evs
    )
    return {
        "getitem_granted": bool(granted),
        "getitem_cached": bool(cached) and not granted,
        "getitem_denied_slots_exhausted": bool(denied_slots) and not granted and not cached,
        "getitem_not_risky": bool(not_risky) and not granted and not cached and not denied_slots,
    }


def _comparator_count(row, estimate):
    ctx = row.get("ask_context") or {}
    if isinstance(estimate, dict):
        for key in ("seller_count", "sample_count"):
            val = estimate.get(key)
            if isinstance(val, int) and val >= 0:
                return val
        sources = estimate.get("sources")
        if isinstance(sources, list):
            return len(sources)
    offers = ctx.get("offers")
    if isinstance(offers, list):
        return len(offers)
    sample = ctx.get("sample_count")
    if isinstance(sample, int):
        return sample
    return 0


def _seller_support(estimate, ctx):
    """Independent seller count and low-supporting count from retained model/context."""
    sellers = None
    support = None
    if isinstance(estimate, dict):
        if isinstance(estimate.get("seller_count"), int):
            sellers = estimate["seller_count"]
        if isinstance(estimate.get("low_price_supporting_sellers"), int):
            support = estimate["low_price_supporting_sellers"]
    if sellers is None or support is None:
        offers = (ctx or {}).get("offers") or []
        by = {}
        for o in offers:
            if not isinstance(o, dict):
                continue
            seller = str(o.get("seller") or "").casefold()
            total = o.get("listed_total")
            if not seller or not isinstance(total, (int, float)) or isinstance(total, bool):
                continue
            if seller not in by or total < by[seller]:
                by[seller] = total
        if by:
            sellers = len(by) if sellers is None else sellers
            low = min(by.values())
            support = sum(1 for t in by.values() if t <= low * 1.1) if support is None else support
    return sellers or 0, support or 0


def _shipping_unknown(row, estimate, proof_reason):
    if proof_reason in ("shipping_unknown",):
        return True
    detail = (row.get("ask_context") or {}).get("lowest_detail") or {}
    for reason in detail.get("reasons") or []:
        if "shipping" in str(reason).lower() and "not supplied" in str(reason).lower():
            return True
    for sc in detail.get("sub_checks") or []:
        if sc.get("sub_check_failed") == details.SUB_SHIP_UNKNOWN:
            return True
    for check in (estimate or {}).get("checks") or []:
        if "shipping" in str(check).lower() and "unknown" in str(check).lower():
            return True
    return False


def _economics_negative(estimate, proof_ok):
    if not isinstance(estimate, dict):
        return False
    # All structural gates aside: model present but not an opportunity / review pass.
    if estimate.get("estimated_opportunity") or estimate.get("worth_reviewing"):
        return False
    if proof_ok:
        # Qualified publication still can be economically SKIP in presentation; treat as negative if net/ROI fail.
        net = estimate.get("net")
        if isinstance(net, (int, float)) and net < 0:
            return True
    checks = " ".join(str(c) for c in (estimate.get("checks") or []))
    if re.search(r"net|roi|strong policy|£\d+", checks, re.I):
        # Only call this economics once earlier structural stages did not fire.
        return True
    signal = str(estimate.get("signal") or "")
    if "SKIP" in signal.upper() or "NOT A BUY" in signal.upper():
        return True
    return False


def _above_budget(offer, research, estimate):
    if isinstance(estimate, dict) and estimate.get("above_budget") is True:
        return True
    price = _merchant_price(offer, research)
    try:
        from . import policy
        cap = policy.current().get("cap", 60.0)
    except Exception:
        cap = 60.0
    if isinstance(price, (int, float)) and price > cap:
        return True
    return False


def classify_failure_stage(offer, research, identity_result, ident, proof, estimate, getitem):
    """First failing stage in the Task 9 vocabulary order."""
    ctx = (research or {}).get("ask_context") or offer.get("ask_context") or {}
    proof_ok = isinstance(proof, dict) and proof.get("ok") is True
    proof_reason = None if proof_ok else (proof or {}).get("reason")
    row = _merged_row(offer, research)

    if identity_result == "not_supported":
        return "identity_not_supported", proof_reason or "unsupported_exact_identity", None
    if identity_result == "ambiguous":
        return "identity_ambiguous", proof_reason or "ambiguous_primary_offer", None

    # Matched identity from here.
    # Slot starvation is a detail-check hold, not a missing-comparator problem.
    if getitem.get("getitem_denied_slots_exhausted"):
        return "detail_check_pending", "detail_check_pending", None

    comparator_count = _comparator_count(row, estimate)
    ask_status = row.get("ask_status") or (research or {}).get("ask_status")
    if comparator_count <= 0 and not estimate and ask_status in (
        None,
        "exact_identity_not_supported",
        "not queried",
        "daily_budget_exhausted",
    ):
        # May still be "not queried" — treat empty retained offers as no comparators when matched.
        if not (ctx.get("offers") or []):
            return "no_comparators_found", proof_reason or "no_supported_resale_estimate", None

    if comparator_count <= 0 and not (ctx.get("offers") or []):
        return "no_comparators_found", proof_reason or "no_supported_resale_estimate", None

    # no_risky_lowest: slot skip / not risky / no comparator lowest for detail.
    if getitem.get("getitem_not_risky") or any(
        e.get("denial_reason") == "not_risky_lowest" for e in _slot_events_for(getattr(ident, "match", None))
    ):
        return "no_risky_lowest", proof_reason or "not_risky_lowest", None
    if details.risky(ident) and not (ctx.get("offers") or estimate):
        return "no_risky_lowest", proof_reason or "not_risky_lowest", None

    detail_status = None
    if isinstance(estimate, dict):
        detail_status = estimate.get("detail_status")
    detail_status = detail_status or ctx.get("detail_status")
    if proof_reason == "detail_check_pending" or detail_status in (
        "awaiting_detail_budget",
        "price_changed",
    ):
        return "detail_check_pending", "detail_check_pending", None
    if proof_reason == "detail_check_failed" or detail_status in (
        "conflict",
        "incomplete",
        "error",
    ):
        return "detail_check_failed", "detail_check_failed", None

    sellers, support = _seller_support(estimate, ctx)
    if proof_reason == "fewer_than_three_exact_independent_comparators" or (
        sellers and sellers < 3 and estimate
    ):
        return "comparator_depth_insufficient", proof_reason or "fewer_than_three_exact_independent_comparators", None
    if proof_reason == "low_price_not_supported" or (support is not None and support < 2 and estimate and sellers >= 3):
        return "comparator_support_insufficient", proof_reason or "low_price_not_supported", None

    if _shipping_unknown(row, estimate, proof_reason):
        return "shipping_unknown", proof_reason or "shipping_unknown", None

    if proof_reason == "uncertain_competitor_coupon" or (
        isinstance(estimate, dict) and estimate.get("competitor_coupon_unknown")
    ):
        return "coupon_unresolved", "uncertain_competitor_coupon", None

    if _economics_negative(estimate, proof_ok):
        return "economics_negative", proof_reason or "economics_negative", None

    if proof_ok:
        return "publication_qualified", None, None

    if _above_budget(offer, research, estimate):
        return "above_budget", proof_reason or "above_budget", None

    note = proof_reason or ask_status or "unclassified trainers pipeline hold"
    return "other", proof_reason, note


def _dominant_stage(stages):
    if not stages:
        return None
    # Prefer non-success failure stages by count; break ties by pipeline order.
    counts = {}
    for s in stages:
        counts[s] = counts.get(s, 0) + 1
    best = None
    best_n = -1
    for stage in STAGES:
        n = counts.get(stage, 0)
        if n > best_n:
            best, best_n = stage, n
    return best


def log_trainer_pipeline(offers, research_rows, out_path="trainers_pipeline_diagnostic.json", state=None):
    """
    For each offer where category == "trainers":
    - record offer title, URL, merchant price
    - record identity match result: "matched", "ambiguous", "not_supported"
    - if matched, record canonical identity string
    - record brand parsed: "nike" | "adidas" | "other" | "unknown"
    - record whether a research model was generated
    - record the specific pipeline stage where it failed or was held
    - record the specific blocker (using existing hold-reason labels)
    - record whether a getItem was granted / cached this scan
    - record comparator count for the identity
    - record if the item is publication_qualified
    Read-only: never calls getItem, never changes gates/parsers/allocation/routing.
    """
    entries = []
    trainer_offers = []
    try:
        for offer in offers or []:
            if offer.get("category") != "trainers":
                continue
            research = _lookup(research_rows, offer.get("url"))
            row = _merged_row(offer, research)
            identity_result, canonical, ident = _identity_match_result(offer)
            brand = _brand_parsed(offer, ident)
            price = _merchant_price(offer, research)
            estimate = row.get("ask_estimate")
            model_generated = bool(estimate)
            proof = row.get("publication_proof")
            if not isinstance(proof, dict):
                proof = publication.proof(row)
            qualified = isinstance(proof, dict) and proof.get("ok") is True
            getitem = _getitem_flags(canonical)
            stage, blocker, note = classify_failure_stage(
                offer, research, identity_result, ident, proof, estimate, getitem
            )
            # If classified publication_qualified but proof disagrees, prefer proof.
            if qualified:
                stage, blocker, note = "publication_qualified", None, None
            comparator_count = _comparator_count(row, estimate)

            entry = {
                "offer_title": offer.get("title") or "",
                "offer_url": offer.get("url"),
                "merchant_price": price,
                "identity_match": identity_result,
                "canonical_identity": canonical,
                "brand_parsed": brand,
                "research_model_generated": bool(model_generated),
                "failure_stage": stage,
                "blocker": blocker,
                "getitem_granted": getitem["getitem_granted"],
                "getitem_cached": getitem["getitem_cached"],
                "getitem_denied_slots_exhausted": getitem["getitem_denied_slots_exhausted"],
                "getitem_not_risky": getitem["getitem_not_risky"],
                "comparator_count": comparator_count,
                "publication_qualified": bool(qualified),
            }
            if note and stage == "other":
                entry["note"] = note
            entries.append(entry)
            trainer_offers.append(
                {
                    "offer_title": entry["offer_title"],
                    "offer_url": entry["offer_url"],
                    "merchant_price": price,
                    "brand_parsed": brand,
                }
            )

        by_brand = {"nike": 0, "adidas": 0, "other": 0, "unknown": 0}
        by_stage = {s: 0 for s in STAGES}
        by_blocker = {}
        by_getitem = {
            "granted": 0,
            "cached": 0,
            "denied_slots_exhausted": 0,
            "not_risky": 0,
        }
        for e in entries:
            by_brand[e["brand_parsed"]] = by_brand.get(e["brand_parsed"], 0) + 1
            by_stage[e["failure_stage"]] = by_stage.get(e["failure_stage"], 0) + 1
            if e.get("blocker"):
                by_blocker[e["blocker"]] = by_blocker.get(e["blocker"], 0) + 1
            if e["getitem_granted"]:
                by_getitem["granted"] += 1
            elif e["getitem_cached"]:
                by_getitem["cached"] += 1
            elif e.get("getitem_denied_slots_exhausted"):
                by_getitem["denied_slots_exhausted"] += 1
            elif e.get("getitem_not_risky"):
                by_getitem["not_risky"] += 1

        pub_count = sum(1 for e in entries if e["publication_qualified"])
        above_count = sum(1 for e in entries if e["failure_stage"] == "above_budget")

        brand_comparison = {}
        for brand in ("nike", "adidas", "other"):
            if brand == "other":
                subset = [e for e in entries if e["brand_parsed"] not in ("nike", "adidas", "unknown")]
            else:
                subset = [e for e in entries if e["brand_parsed"] == brand]
            stages = [e["failure_stage"] for e in subset]
            brand_comparison[brand] = {
                "offers": len(subset),
                "identity_matched": sum(1 for e in subset if e["identity_match"] == "matched"),
                "models_generated": sum(1 for e in subset if e["research_model_generated"]),
                "comparators_found": sum(1 for e in subset if (e.get("comparator_count") or 0) > 0),
                "publication_qualified": sum(1 for e in subset if e["publication_qualified"]),
                "dominant_failure_stage": _dominant_stage(stages),
            }

        payload = {
            "entries": entries,
            "trainer_offers": trainer_offers,
            "aggregate": {
                "total_offers": len(entries),
                "by_brand": by_brand,
                "by_stage": by_stage,
                "by_blocker": by_blocker,
                "by_getitem": by_getitem,
                "publication_qualified_count": pub_count,
                "above_budget_count": above_count,
            },
            "brand_comparison": brand_comparison,
            "error": None,
        }
    except Exception as exc:
        payload = {
            "entries": entries,
            "trainer_offers": trainer_offers,
            "aggregate": None,
            "brand_comparison": None,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    path = Path(out_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload
