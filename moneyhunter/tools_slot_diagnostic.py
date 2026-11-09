"""Read-only tools getItem slot-allocation diagnostic. Never changes allocation."""
from __future__ import annotations

import json
import traceback
from pathlib import Path

from . import details, market, research_budget


def _lookup(rows, url):
    for row in rows or []:
        if row.get("url") == url:
            return row
    return None


def _identity_string(offer):
    try:
        ident = market.identity(offer)
    except Exception:
        return None
    if not ident:
        return None
    return str(getattr(ident, "match", None) or None)


def log_tool_slot_allocation(offers, research_rows, out_path="tools_slot_diagnostic.json", state=None):
    """
    For each tools offer, record whether getItem was requested/granted and why.
    Reuses details.SLOT_EVENTS / ENRICH_GROUPS captured during the existing path.
    Do not change any state, routing, gate, or slot-allocation logic.
    """
    entries = []
    try:
        events = list(details.SLOT_EVENTS)
        groups = list(details.ENRICH_GROUPS)
        run = (state or {}).get("detail_run") or {}
        reserved = run.get("reserved_tools", 2)
        used = run.get("calls", 0)
        usage = (state or {}).get("browse_usage") or {}
        total_budget = research_budget.DAILY_LIMIT
        total_used = usage.get("calls") if isinstance(usage.get("calls"), int) else None

        # Identity -> enrich group meta (tools lanes preferred).
        by_identity = {}
        for g in groups:
            if g.get("category") != "tools":
                continue
            key = g.get("identity") or ""
            by_identity.setdefault(key, {"offer_urls": [], "deduplicated": False, "lanes": []})
            by_identity[key]["offer_urls"].extend(g.get("offer_urls") or [])
            by_identity[key]["deduplicated"] = by_identity[key]["deduplicated"] or bool(g.get("deduplicated"))
            by_identity[key]["lanes"].append(g.get("lane"))
        for meta in by_identity.values():
            # unique preserve order
            seen = set(); urls = []
            for u in meta["offer_urls"]:
                if u not in seen:
                    seen.add(u); urls.append(u)
            meta["offer_urls"] = urls
            meta["same_identity_other_offers"] = max(0, len(urls) - 1)
            meta["deduplicated"] = len(urls) > 1 or meta["deduplicated"]

        # Events by identity (tools and overall).
        events_by_identity = {}
        granted_overall = []
        for ev in events:
            if ev.get("getitem_granted"):
                granted_overall.append(ev)
            if ev.get("category") == "tools" or (ev.get("identity") and "bare tool" in str(ev.get("identity") or "").lower()):
                events_by_identity.setdefault(ev.get("identity"), []).append(ev)
            elif ev.get("category"):
                events_by_identity.setdefault(ev.get("identity"), []).append(ev)

        research_by_url = {r.get("url"): r for r in (research_rows or []) if r.get("url")}

        tools_offers = [o for o in (offers or []) if o.get("category") == "tools"]
        # Count identity frequency across tools offers this scan.
        id_counts = {}
        id_for = {}
        for o in tools_offers:
            ident = _identity_string(o)
            id_for[o.get("url")] = ident
            if ident:
                id_counts[ident] = id_counts.get(ident, 0) + 1

        for offer in tools_offers:
            url = offer.get("url")
            title = offer.get("title") or ""
            ident = id_for.get(url)
            research = research_by_url.get(url) or {}
            group = by_identity.get(ident or "", {})
            same_other = max(0, id_counts.get(ident, 1) - 1) if ident else 0
            dedup = bool(group.get("deduplicated")) or same_other > 0

            # Default: lookup not considered.
            getitem_requested = False
            getitem_granted = False
            slot_index = None
            denial_reason = None
            note = None

            if not ident:
                denial_reason = "other"
                note = "exact_identity_not_supported; no detail lookup considered"
            elif url not in research_by_url and not research.get("ask_context") and not offer.get("ask_context"):
                # Not in research/enrich path this scan.
                denial_reason = "other"
                note = "tools offer not in asking enrich candidates this scan"
            else:
                # Match slot events for this identity.
                evs = [e for e in events if e.get("identity") == ident]
                granted = [e for e in evs if e.get("getitem_granted")]
                cache_hits = [e for e in evs if e.get("denial_reason") == "cache_hit"]
                denied = [e for e in evs if e.get("getitem_requested") and not e.get("getitem_granted") and e.get("denial_reason") != "cache_hit"]
                if granted:
                    getitem_requested = True
                    getitem_granted = True
                    slot_index = granted[0].get("slot_index")
                    note = granted[0].get("note")
                elif cache_hits:
                    getitem_requested = True
                    getitem_granted = False
                    denial_reason = "cache_hit"
                    note = cache_hits[0].get("note")
                elif denied:
                    getitem_requested = True
                    getitem_granted = False
                    denial_reason = denied[0].get("denial_reason") or "other"
                    note = denied[0].get("note")
                    if dedup and denial_reason in ("slots_exhausted", "budget_exhausted", "other"):
                        # Still report actual denial; note shared identity.
                        note = ((note + "; ") if note else "") + "identity shared with other offer(s) this scan"
                elif dedup and ident in by_identity:
                    # Grouped in enrich but no inspect event (ask snapshot not fresh / no query).
                    getitem_requested = False
                    denial_reason = "identity_deduplicated" if same_other > 0 else "other"
                    note = "identity grouped in enrich but no detail inspect event this scan (ask snapshot may be missing)"
                else:
                    getitem_requested = False
                    denial_reason = "other"
                    note = "no detail inspect event for this identity this scan"

                # If multiple offers share identity and only one inspect was issued, mark secondary as deduped.
                if dedup and ident and not getitem_granted and denial_reason not in ("cache_hit",):
                    urls = group.get("offer_urls") or []
                    if urls and url != urls[0] and getitem_requested is False:
                        denial_reason = "identity_deduplicated"
                        note = "same canonical identity as earlier offer; enrich groups before slot allocation"

            entries.append({
                "offer_title": title,
                "offer_url": url,
                "identity": ident or "none",
                "getitem_requested": bool(getitem_requested),
                "getitem_granted": bool(getitem_granted),
                "slot_index": slot_index,
                "denial_reason": denial_reason,
                "same_identity_other_offers": same_other,
                "deduplicated": bool(dedup),
                "note": note,
            })

        identity_groups = []
        for ident, meta in sorted(by_identity.items(), key=lambda kv: kv[0] or ""):
            related = [e for e in entries if e.get("identity") == ident]
            identity_groups.append({
                "identity": ident,
                "offer_count": len(meta.get("offer_urls") or []),
                "offer_urls": meta.get("offer_urls") or [],
                "deduplicated": bool(meta.get("deduplicated")),
                "lanes": meta.get("lanes") or [],
                "getitem_granted_any": any(e.get("getitem_granted") for e in related),
                "denial_reasons": sorted({e.get("denial_reason") for e in related if e.get("denial_reason")}),
            })

        getitem_calls = []
        for ev in events:
            if not ev.get("getitem_granted"):
                continue
            getitem_calls.append({
                "slot_index": ev.get("slot_index"),
                "category": ev.get("category"),
                "identity": ev.get("identity"),
                "comparator_item_id": ev.get("comparator_item_id"),
                "comparator_url": ev.get("comparator_url"),
                "note": ev.get("note"),
            })

        payload = {
            "entries": entries,
            "identity_groups": identity_groups,
            "getitem_calls": getitem_calls,
            "slot_events": events,
            "enrich_groups": groups,
            "slot_summary": {
                "tool_slots_reserved": reserved,
                "tool_slots_used": used,
                "total_getitem_budget": total_budget,
                "total_getitem_used": total_used,
                "detail_limit_per_scan": details.LIMIT,
                "non_tool_slot_cap": details.LIMIT - (reserved or 0),
            },
            "error": None,
        }
    except Exception as exc:
        payload = {
            "entries": entries,
            "identity_groups": [],
            "getitem_calls": [],
            "slot_summary": {},
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    path = Path(out_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload
