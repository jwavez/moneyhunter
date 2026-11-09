"""Read-only tools detail-failure diagnostic. Never changes gates, routes, or parsers."""
from __future__ import annotations

import json
import traceback
from pathlib import Path

from . import details, market, publication


def _lookup(rows, url):
    for row in rows or []:
        if row.get("url") == url:
            return row
    return None


def _identity_string(offer):
    try:
        ident = market.identity(offer)
    except Exception:
        return "none"
    if not ident:
        return "none"
    return str(getattr(ident, "match", None) or "none")


def _merged_row(offer, research):
    row = dict(offer or {})
    if research:
        if not row.get("ask_estimate") and research.get("ask_estimate"):
            row["ask_estimate"] = research["ask_estimate"]
        if not row.get("ask_context") and research.get("ask_context"):
            row["ask_context"] = research["ask_context"]
    return row


def _failures_from_detail(detail):
    """Reuse assess sub_checks when present; otherwise map existing reason strings."""
    existing = detail.get("sub_checks")
    if isinstance(existing, list) and existing:
        return [
            {
                "sub_check_failed": f.get("sub_check_failed") or details.SUB_OTHER,
                "expected": f.get("expected"),
                "observed": f.get("observed"),
                "note": f.get("note") or f.get("reason"),
            }
            for f in existing
        ]
    out = []
    for reason in detail.get("reasons") or []:
        name = details.map_reason_to_sub_check(reason)
        out.append(
            {
                "sub_check_failed": name,
                "expected": None,
                "observed": None,
                "note": reason,
            }
        )
    if not out and detail.get("status") and detail.get("status") != "verified_fields":
        out.append(
            {
                "sub_check_failed": details.SUB_OTHER,
                "expected": "verified_fields",
                "observed": detail.get("status"),
                "note": "detail status not verified; no reason list retained",
            }
        )
    return out


def _comparator_fields(ctx, detail):
    """Pull the already-checked lowest comparator; never call getItem again."""
    offers = list(ctx.get("offers") or [])
    item_id = detail.get("item_id")
    comp = None
    if item_id:
        for o in offers:
            if o.get("item_id") == item_id:
                comp = o
                break
    missing_notes = []
    if item_id and comp is None and offers:
        missing_notes.append("lowest_detail item_id not found among retained ask offers")
    if not offers:
        missing_notes.append("no ask_context offers retained")

    # Prefer values retained on the detail snapshot from the same getItem pass.
    title = detail.get("title")
    if title is None and comp is not None:
        title = comp.get("title")
    if title is None:
        missing_notes.append("comparator_title not retained")

    condition = detail.get("condition_id")
    if condition is None and comp is not None:
        condition = comp.get("condition") or comp.get("declared_condition")
    if condition is None:
        missing_notes.append("comparator_condition not retained")

    price = detail.get("checked_item_price")
    if price is None and comp is not None:
        price = comp.get("item_price")
    if price is None:
        missing_notes.append("comparator_price not retained")

    shipping = detail.get("fixed_shipping")
    if shipping is None and comp is not None and isinstance(comp.get("shipping"), (int, float)):
        shipping = comp.get("shipping")
    if shipping is None:
        missing_notes.append("comparator_shipping not retained from getItem")

    availability = detail.get("availability")
    if availability is None:
        missing_notes.append("comparator_availability not retained")

    url = None
    if comp is not None:
        url = comp.get("url")
    if url is None:
        url = detail.get("source_url")
    if url is None:
        missing_notes.append("comparator_url not retained")

    present = detail.get("getitem_fields_present")
    absent = detail.get("getitem_fields_missing")
    if present is None and absent is None:
        missing_notes.append("getitem field inventory not retained on this detail row")

    return {
        "comparator_url": url,
        "comparator_title": title,
        "comparator_condition": condition,
        "comparator_price": price,
        "comparator_shipping": shipping,
        "comparator_availability": availability,
        "getitem_fields_present": present if present is not None else [],
        "getitem_fields_missing": absent if absent is not None else [],
        "note": "; ".join(missing_notes) if missing_notes else None,
    }


def _delivered_price(offer):
    total = offer.get("listed_total")
    if isinstance(total, (int, float)) and not isinstance(total, bool):
        return float(total)
    price = offer.get("item_price")
    ship = offer.get("shipping")
    if isinstance(price, (int, float)) and not isinstance(price, bool):
        s = float(ship) if isinstance(ship, (int, float)) and not isinstance(ship, bool) else 0.0
        return float(price) + s
    return None


def _observed_model_number(detail):
    """Model/MPN already retained on a getItem assess row. Never fetches."""
    if not isinstance(detail, dict):
        return None
    for aspect in detail.get("aspects") or []:
        if not isinstance(aspect, dict):
            continue
        name = str(aspect.get("name") or "").strip().lower()
        if name in ("model", "mpn", "manufacturer part number"):
            val = aspect.get("value")
            if val is not None and str(val).strip():
                return str(val)
    mpn = detail.get("mpn")
    if mpn is not None and str(mpn).strip():
        return str(mpn)
    return None


def _detail_fail_reason(detail):
    failures = _failures_from_detail(detail or {})
    if failures:
        return failures[0].get("sub_check_failed") or failures[0].get("note")
    status = (detail or {}).get("status")
    return status if status and status != "verified_fields" else None


def _cached_detail_for_candidate(state, identity, item_id):
    """Read-only lookup of an already-fetched getItem row. Never calls Browse."""
    if not item_id or not identity:
        return None
    cache = (state or {}).get("item_detail_cache") or {}
    key = str(item_id) + "::" + str(identity)
    cached = cache.get(key)
    if isinstance(cached, dict):
        return cached
    # Fall back: any cache key ending with this identity whose item_id matches.
    for k, row in cache.items():
        if not isinstance(row, dict):
            continue
        if row.get("item_id") == item_id and str(k).endswith("::" + str(identity)):
            return row
    return None


def _seller_deduped_offers(offers):
    """Cheapest listing per seller (unknown sellers kept). Matches asking.estimate spirit."""
    sellers, unknown, seen = {}, [], set()
    for offer in offers or []:
        if not isinstance(offer, dict):
            continue
        if _delivered_price(offer) is None:
            continue
        item_id = offer.get("item_id")
        key = item_id or offer.get("url")
        if key in seen:
            continue
        seen.add(key)
        seller = str(offer.get("seller") or "").casefold()
        if seller:
            prev = sellers.get(seller)
            if prev is None or _delivered_price(offer) < _delivered_price(prev):
                sellers[seller] = offer
        else:
            unknown.append(offer)
    return sorted([*sellers.values(), *unknown], key=lambda o: (_delivered_price(o), str(o.get("item_id") or "")))


def build_comparator_candidates(ctx, detail, identity, state=None, max_candidates=3):
    """Read-only candidate list for a detail_check_failed entry. No extra getItem."""
    offers = _seller_deduped_offers(ctx.get("offers") or [])
    # Guide: at most three cheapest distinct-seller offers; never invent beyond retained.
    offers = offers[: max(0, int(max_candidates))]
    checked_id = (detail or {}).get("item_id")
    out = []
    for rank, offer in enumerate(offers, start=1):
        item_id = offer.get("item_id")
        price = offer.get("item_price")
        shipping = offer.get("shipping")
        delivered = _delivered_price(offer)
        # Prefer explicit item/shipping fields; fall back to delivered split only for display.
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            price = delivered
            shipping = 0.0 if shipping is None else shipping
        ran = False
        would_pass = None
        fail_reason = None
        observed_model = None
        matched_detail = None
        if checked_id and item_id == checked_id and isinstance(detail, dict) and detail.get("status") not in (
            None,
            "awaiting_detail_budget",
        ):
            ran = True
            matched_detail = detail
        else:
            cached = _cached_detail_for_candidate(state, identity, item_id)
            if isinstance(cached, dict) and cached.get("status") not in (None, "awaiting_detail_budget"):
                ran = True
                matched_detail = cached
        if ran and matched_detail is not None:
            would_pass = matched_detail.get("status") == "verified_fields"
            fail_reason = None if would_pass else _detail_fail_reason(matched_detail)
            observed_model = _observed_model_number(matched_detail)
        out.append(
            {
                "rank_by_price": rank,
                "price": price,
                "shipping": shipping if isinstance(shipping, (int, float)) and not isinstance(shipping, bool) else 0.0,
                "title": offer.get("title"),
                "item_id": item_id,
                "url": offer.get("url"),
                "getitem_ran": ran,
                "detail_would_pass": would_pass,
                "detail_fail_reason": fail_reason,
                "observed_model_number": observed_model,
            }
        )
    return out


def _categorize_identity(identity, events):
    """Map an identity to not_risky_lowest | other | wanted using slot events."""
    from . import tools_slot_diagnostic as slot_diag

    evs = [e for e in (events or []) if e.get("identity") == identity]
    if not evs:
        return "other"
    bucket, _note = slot_diag._classify_identity_events(evs)
    if bucket == "denied_not_risky":
        return "not_risky_lowest"
    if bucket == "granted":
        return "wanted"
    if bucket in ("denied_slots_exhausted", "denied_cache_hit", "denied_other"):
        # wanted path (actually demanded a lookup) vs pure skip already handled.
        if bucket == "denied_other" and all(e.get("phase") == "inspect_skip" for e in evs):
            return "not_risky_lowest"
        return "wanted"
    return "other"


def build_pr34_categorization_check(events=None):
    """Confirm PR 34 moved DTD152Z/DUB185Z off denied_other into not_risky_lowest."""
    from . import tools_slot_diagnostic as slot_diag

    events = list(events if events is not None else details.SLOT_EVENTS)
    per = slot_diag._per_category_slot_summary(events)
    tools = next((r for r in per if r.get("category") == "tools"), None) or {
        "wanted": 0,
        "considered": 0,
    }
    dtd = "Makita DTD152Z bare tool 18V"
    dub = "Makita DUB185Z bare tool 18V"
    dtd_as = _categorize_identity(dtd, events)
    dub_as = _categorize_identity(dub, events)
    expected_wanted = 5
    passes = (
        tools.get("wanted") == expected_wanted
        and dtd_as == "not_risky_lowest"
        and dub_as == "not_risky_lowest"
    )
    out = {
        "tools_wanted": tools.get("wanted"),
        "tools_considered": tools.get("considered"),
        "expected_tools_wanted_after_pr34": expected_wanted,
        "dtd152z_categorized_as": dtd_as,
        "dub185z_categorized_as": dub_as,
        "passes": bool(passes),
    }
    if not passes:
        out["actual_log"] = {
            "tools_wanted": tools.get("wanted"),
            "tools_considered": tools.get("considered"),
            "dtd152z_categorized_as": dtd_as,
            "dub185z_categorized_as": dub_as,
            "note": "PR 34 expectation failed; logged actual values",
        }
    return out


def _seller_counts(offers):
    sellers = {}
    for o in offers or []:
        if not isinstance(o, dict):
            continue
        seller = str(o.get("seller") or "").casefold()
        total = _delivered_price(o)
        if total is None:
            continue
        if seller:
            if seller not in sellers or total < sellers[seller]:
                sellers[seller] = total
    if not sellers:
        return 0, 0, None
    low = min(sellers.values())
    supporting = sum(1 for t in sellers.values() if t <= low * 1.1)
    return len(sellers), supporting, low


def build_near_publish_diagnostic_dga452z(offers, research_rows, events=None):
    """Explain existing near_publish flag for DGA452Z. Does not recompute allocation."""
    events = list(events if events is not None else details.SLOT_EVENTS)
    identity = "Makita DGA452Z bare tool 18V"
    # Prefer slot-event flag recorded at allocation time.
    dga_events = [e for e in events if e.get("identity") == identity]
    flag_from_event = None
    for e in dga_events:
        if "near_publish" in e:
            flag_from_event = bool(e.get("near_publish"))
            break

    # Locate research/offer row for this identity.
    match_offer = None
    match_research = None
    for offer in offers or []:
        ident = _identity_string(offer)
        title = (offer.get("title") or "").upper()
        if "DGA452Z" in title or "DGA452Z" in (ident or "").upper():
            match_offer = offer
            match_research = _lookup(research_rows, offer.get("url"))
            break
    row = _merged_row(match_offer or {}, match_research)
    ctx = row.get("ask_context") or {}
    estimate = row.get("ask_estimate") or {}
    # Snapshot as allocation would have seen it (ask_estimate not yet stamped on snapshot).
    snapshot_for_flag = dict(ctx) if ctx else {}
    # Strip ask_estimate if somehow present on context — allocation used sample_count path.
    snapshot_for_flag.pop("ask_estimate", None)
    computed_flag = details._near_publish_pending(snapshot_for_flag)
    near_flag = flag_from_event if flag_from_event is not None else computed_flag

    research_model_present = bool(estimate) or bool(row.get("ask_estimate"))
    # Depth = sample_count at inspect time (what _near_publish_pending reads).
    comparator_depth = ctx.get("sample_count")
    if comparator_depth is None:
        comparator_depth = estimate.get("sample_count")
    if comparator_depth is None:
        comparator_depth = len(ctx.get("offers") or [])
    try:
        comparator_depth = int(comparator_depth or 0)
    except (TypeError, ValueError):
        comparator_depth = 0

    independent_seller_count, supporting_low_count, _low = _seller_counts(ctx.get("offers") or [])
    if estimate.get("seller_count") is not None:
        try:
            independent_seller_count = int(estimate.get("seller_count"))
        except (TypeError, ValueError):
            pass
    if estimate.get("low_price_supporting_sellers") is not None:
        try:
            supporting_low_count = int(estimate.get("low_price_supporting_sellers"))
        except (TypeError, ValueError):
            pass

    other_gates_missing = []
    # Publication-style blockers already on the model (informational; not near_publish inputs).
    for b in estimate.get("checks") or []:
        other_gates_missing.append(str(b)[:200])
    detail_status = (
        (ctx.get("detail_status") if ctx else None)
        or estimate.get("detail_status")
        or (row.get("ask_estimate") or {}).get("detail_status")
    )
    if detail_status and detail_status != "verified_fields":
        gate = f"detail_status={detail_status}"
        if gate not in other_gates_missing:
            other_gates_missing.append(gate)

    if near_flag:
        explanation = (
            "near_publish true: allocation saw a viable research-model depth "
            f"(sample_count/comparator_depth={comparator_depth}) and only the detail check was missing"
        )
    else:
        # Exact gate from _near_publish_pending: ask_estimate absent on snapshot AND sample_count < 3.
        if comparator_depth < 3:
            explanation = (
                f"near_publish false because comparator_depth/sample_count={comparator_depth} "
                "(requires sample_count >= 3 at allocation; ask_estimate is not yet on the snapshot)"
            )
        elif research_model_present:
            explanation = (
                "near_publish false at allocation despite a later research_model: "
                f"allocation-time snapshot sample_count={comparator_depth} did not meet "
                "details._near_publish_pending (ask_estimate not stamped until after flush)"
            )
        else:
            explanation = (
                f"near_publish false: details._near_publish_pending saw sample_count={comparator_depth} "
                "and no ask_estimate on the allocation snapshot"
            )

    return {
        "near_publish_flag": bool(near_flag),
        "research_model_present": bool(research_model_present),
        "comparator_depth": comparator_depth,
        "independent_seller_count": independent_seller_count,
        "supporting_low_count": supporting_low_count,
        "other_gates_missing": other_gates_missing,
        "explanation": explanation,
    }


def log_tool_detail_failures(offers, research_rows, out_path="tools_detail_diagnostic.json", state=None):
    """
    For each tool offer where publication reason is detail_check_pending or detail_check_failed:
    - record offer title and URL
    - record the exact identity string
    - record the comparator listing that was checked
    - record each failed detail sub-check with expected vs observed
    - record which getItem fields were present vs missing
    - for detail_check_failed: record comparator_candidates (read-only)
    Also emit pr34_categorization_check and near_publish_diagnostic.dga452z.
    Write the list to out_path as JSON.
    Do not change any state, route, gate, or parser. Never call getItem.
    """
    entries = []
    try:
        for offer in offers or []:
            if offer.get("category") != "tools":
                continue
            research = _lookup(research_rows, offer.get("url"))
            row = _merged_row(offer, research)
            # Reuse existing publication classifier; do not invent a new gate.
            proof = publication.proof(row)
            if proof.get("ok") is True or proof.get("reason") not in ("detail_check_pending", "detail_check_failed"):
                continue
            ctx = row.get("ask_context") or (research or {}).get("ask_context") or {}
            detail = ctx.get("lowest_detail") or {}
            if not detail and row.get("ask_estimate"):
                # Model may carry detail_status without embedding lowest_detail.
                detail = {
                    "status": row["ask_estimate"].get("detail_status"),
                    "reasons": [],
                }
            failures = _failures_from_detail(detail)
            comp = _comparator_fields(ctx, detail)
            identity = _identity_string(offer)
            entry = {
                "offer_url": offer.get("url"),
                "offer_title": offer.get("title") or "",
                "identity": identity,
                "detail_status": detail.get("status") or row.get("ask_estimate", {}).get("detail_status"),
                "publication_reason": proof.get("reason"),
                "comparator_url": comp["comparator_url"],
                "comparator_title": comp["comparator_title"],
                "comparator_condition": comp["comparator_condition"],
                "comparator_price": comp["comparator_price"],
                "comparator_shipping": comp["comparator_shipping"],
                "comparator_availability": comp["comparator_availability"],
                "getitem_fields_present": comp["getitem_fields_present"],
                "getitem_fields_missing": comp["getitem_fields_missing"],
                "sub_checks": failures,
                # Singular convenience mirrors for the first failure (full list retained above).
                "sub_check_failed": failures[0]["sub_check_failed"] if failures else None,
                "expected": failures[0]["expected"] if failures else None,
                "observed": failures[0]["observed"] if failures else None,
                "note": comp["note"],
            }
            if proof.get("reason") == "detail_check_failed":
                entry["comparator_candidates"] = build_comparator_candidates(
                    ctx, detail, identity, state=state, max_candidates=3
                )
            entries.append(entry)

        payload = {
            "entries": entries,
            "pr34_categorization_check": build_pr34_categorization_check(),
            "near_publish_diagnostic": {
                "dga452z": build_near_publish_diagnostic_dga452z(offers, research_rows),
            },
            "error": None,
        }
    except Exception as exc:
        payload = {
            "entries": entries,
            "pr34_categorization_check": None,
            "near_publish_diagnostic": {"dga452z": None},
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    path = Path(out_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload
