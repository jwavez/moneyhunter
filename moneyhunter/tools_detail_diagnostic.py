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


def log_tool_detail_failures(offers, research_rows, out_path="tools_detail_diagnostic.json"):
    """
    For each tool offer where publication reason is detail_check_pending or detail_check_failed:
    - record offer title and URL
    - record the exact identity string
    - record the comparator listing that was checked
    - record each failed detail sub-check with expected vs observed
    - record which getItem fields were present vs missing
    Write the list to out_path as JSON.
    Do not change any state, route, gate, or parser.
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
            entries.append(
                {
                    "offer_url": offer.get("url"),
                    "offer_title": offer.get("title") or "",
                    "identity": _identity_string(offer),
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
            )
        payload = {"entries": entries, "error": None}
    except Exception as exc:
        payload = {
            "entries": entries,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    path = Path(out_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload
