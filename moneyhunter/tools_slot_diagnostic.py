"""Read-only tools getItem slot-allocation diagnostic. Never changes allocation."""
from __future__ import annotations

import json
import traceback
from pathlib import Path

from . import details, market, publication, research_budget


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


def _classify_identity_events(evs):
    """One outcome per identity from its slot events. Prefer grant over denials."""
    if any(e.get("getitem_granted") for e in evs):
        return "granted", None
    reasons = [e.get("denial_reason") for e in evs if e.get("denial_reason")]
    if "cache_hit" in reasons:
        return "denied_cache_hit", None
    if "slots_exhausted" in reasons:
        return "denied_slots_exhausted", None
    if "not_risky_lowest" in reasons:
        return "denied_not_risky", None
    if any(e.get("getitem_requested") for e in evs) or reasons:
        note = next((e.get("note") for e in evs if e.get("note")), None)
        why = next((r for r in reasons if r), "unclassified_slot_event")
        return "denied_other", note or why
    return "denied_other", "identity present in slot log without classifiable outcome"


def _per_category_slot_summary(events):
    """Distinct identities per category.

    considered = all identities (includes inspect_skip / not_risky).
    wanted = identities that actually wanted a lookup (excludes not_risky_lowest).
    wanted == granted + denied_slots_exhausted + denied_cache_hit + denied_other
    denied_not_risky_lowest is tracked separately and is not part of wanted.
    """
    by_cat = {}
    for ev in events or []:
        cat = ev.get("category") or "unknown"
        ident = ev.get("identity") or f"anon:{ev.get('comparator_item_id') or ev.get('phase')}"
        by_cat.setdefault(cat, {}).setdefault(ident, []).append(ev)
    out = []
    for cat in sorted(by_cat):
        row = {
            "category": cat,
            "considered": 0,
            "wanted": 0,
            "granted": 0,
            "denied_slots_exhausted": 0,
            "denied_cache_hit": 0,
            "denied_not_risky_lowest": 0,
            "denied_other": 0,
            "denied_other_notes": [],
        }
        for ident, evs in by_cat[cat].items():
            bucket, note = _classify_identity_events(evs)
            row["considered"] += 1
            if bucket == "denied_not_risky":
                row["denied_not_risky_lowest"] += 1
                continue
            row["wanted"] += 1
            # Map classifier bucket names onto output fields.
            if bucket == "granted":
                row["granted"] += 1
            elif bucket == "denied_slots_exhausted":
                row["denied_slots_exhausted"] += 1
            elif bucket == "denied_cache_hit":
                row["denied_cache_hit"] += 1
            else:
                row["denied_other"] += 1
                if note:
                    row["denied_other_notes"].append({"identity": ident, "note": note})
        denied_sum = (
            row["denied_slots_exhausted"]
            + row["denied_cache_hit"]
            + row["denied_other"]
        )
        if row["wanted"] != row["granted"] + denied_sum:
            row["denied_other"] += row["wanted"] - row["granted"] - denied_sum
            row["denied_other_notes"].append(
                {"identity": None, "note": "adjusted to satisfy wanted == granted + denied_*"}
            )
        if not row["denied_other_notes"]:
            row.pop("denied_other_notes")
        out.append(row)
    return out


def _dga452z_publication_status(offers, research_rows, events):
    """Read-only publication/card outcome for Makita DGA452Z this scan."""
    empty = {
        "in_this_scan": False,
        "identity": None,
        "getitem_granted_this_scan": None,
        "slot_index_this_scan": None,
        "publication_qualified": None,
        "publication_blocker": None,
        "research_model_value": None,
        "publication_estimate_value": None,
        "conclusion": None,
    }
    matches = []
    for offer in offers or []:
        title = offer.get("title") or ""
        ident = _identity_string(offer) or ""
        if "DGA452Z" in title.upper() or "DGA452Z" in ident.upper():
            matches.append(offer)
    if not matches:
        return empty

    # Prefer an offer that has ask/publication context.
    research_by_url = {r.get("url"): r for r in (research_rows or []) if r.get("url")}
    offer = matches[0]
    for o in matches:
        if o.get("ask_estimate") or (research_by_url.get(o.get("url")) or {}).get("ask_estimate"):
            offer = o
            break
    research = research_by_url.get(offer.get("url")) or {}
    row = dict(offer)
    if not row.get("ask_estimate") and research.get("ask_estimate"):
        row["ask_estimate"] = research["ask_estimate"]
    if not row.get("ask_context") and research.get("ask_context"):
        row["ask_context"] = research["ask_context"]
    if not row.get("publication_proof") and research.get("publication_proof"):
        row["publication_proof"] = research["publication_proof"]

    ident = _identity_string(row) or "Makita DGA452Z bare tool 18V"
    evs = [e for e in (events or []) if e.get("identity") == ident]
    granted = [e for e in evs if e.get("getitem_granted")]
    getitem_granted = bool(granted)
    slot_index = granted[0].get("slot_index") if granted else None

    proof = row.get("publication_proof")
    if not isinstance(proof, dict):
        proof = publication.proof(row)
    qualified = proof.get("ok") is True
    blocker = None if qualified else proof.get("reason")

    estimate = None
    model = row.get("ask_estimate") or {}
    if isinstance(model, dict):
        for key in ("estimated_resale", "suggested_listing", "competition_low"):
            if isinstance(model.get(key), (int, float)):
                estimate = model.get(key)
                break
    if estimate is None and qualified and isinstance(proof.get("listing"), (int, float)):
        estimate = proof.get("listing")

    conclusion = None
    if isinstance(model, dict) and model.get("signal"):
        conclusion = model.get("signal")
    try:
        from . import presentation
        fields = presentation.fields(row, legacy=row)
        if fields and len(fields) >= 3:
            conclusion = fields[2].get("value") or conclusion
    except Exception:
        pass
    if conclusion:
        # Keep a short operator-facing label when possible.
        upper = str(conclusion).upper()
        if "SKIP" in upper:
            short = "SKIP"
        elif "CHECK" in upper or "VERIFY" in upper or "WORTH REVIEWING" in upper:
            short = "CHECK"
        elif "NOT A BUY" in upper:
            short = "NOT A BUY"
        elif "BUY" in upper:
            short = "BUY"
        else:
            short = None
        if short:
            conclusion = short + ((" — " + str(conclusion)[:180]) if short not in str(conclusion) else "")

    research_model_value = estimate
    publication_estimate_value = estimate if qualified else None
    return {
        "in_this_scan": True,
        "identity": ident,
        "getitem_granted_this_scan": getitem_granted,
        "slot_index_this_scan": slot_index,
        "publication_qualified": qualified,
        "publication_blocker": blocker,
        "research_model_value": research_model_value,
        "publication_estimate_value": publication_estimate_value,
        "conclusion": conclusion,
    }


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
            seen = set(); urls = []
            for u in meta["offer_urls"]:
                if u not in seen:
                    seen.add(u); urls.append(u)
            meta["offer_urls"] = urls
            meta["same_identity_other_offers"] = max(0, len(urls) - 1)
            meta["deduplicated"] = len(urls) > 1 or meta["deduplicated"]

        research_by_url = {r.get("url"): r for r in (research_rows or []) if r.get("url")}

        tools_offers = [o for o in (offers or []) if o.get("category") == "tools"]
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

            getitem_requested = False
            getitem_granted = False
            slot_index = None
            denial_reason = None
            note = None

            if not ident:
                denial_reason = "other"
                note = "exact_identity_not_supported; no detail lookup considered"
            elif url not in research_by_url and not research.get("ask_context") and not offer.get("ask_context"):
                denial_reason = "other"
                note = "tools offer not in asking enrich candidates this scan"
            else:
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
                        note = ((note + "; ") if note else "") + "identity shared with other offer(s) this scan"
                elif dedup and ident in by_identity:
                    getitem_requested = False
                    denial_reason = "identity_deduplicated" if same_other > 0 else "other"
                    note = "identity grouped in enrich but no detail inspect event this scan (ask snapshot may be missing)"
                else:
                    getitem_requested = False
                    denial_reason = "other"
                    note = "no detail inspect event for this identity this scan"

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

        tool_grants = sum(1 for c in getitem_calls if c.get("category") == "tools")
        per_category = _per_category_slot_summary(events)
        dga_status = _dga452z_publication_status(offers, research_rows, events)

        payload = {
            "entries": entries,
            "identity_groups": identity_groups,
            "getitem_calls": getitem_calls,
            "slot_events": events,
            "enrich_groups": groups,
            "per_category_slot_summary": per_category,
            "dga452z_publication_status": dga_status,
            "slot_summary": {
                "tool_slots_reserved": reserved,
                "tool_slots_used": tool_grants,
                "shared_daily_getitem_budget": total_budget,
                "total_getitem_used": total_used,
                "detail_limit_per_scan": details.LIMIT,
                "non_tool_slot_cap": details.LIMIT - (reserved or 0),
                "total_wanted": sum(r.get("wanted", 0) for r in per_category),
                "total_granted": sum(r.get("granted", 0) for r in per_category),
                "notes": [
                    "tool_slots_reserved is a minimum floor within the 4-slot cap, not a maximum; rotation may grant tools more than 2",
                    "non_tool_slot_cap is a minimum floor for trainers+tech combined within the 4-slot cap, not a hard maximum",
                    "primary rotation is tools→trainers→tech; fragrance (and lego/gaming/other) only receive leftover Phase-3 slots",
                ],
            },
            "error": None,
        }
    except Exception as exc:
        payload = {
            "entries": entries,
            "identity_groups": [],
            "getitem_calls": [],
            "per_category_slot_summary": [],
            "dga452z_publication_status": {
                "in_this_scan": False,
                "identity": None,
                "getitem_granted_this_scan": None,
                "slot_index_this_scan": None,
                "publication_qualified": None,
                "publication_blocker": None,
                "research_model_value": None,
                "publication_estimate_value": None,
                "conclusion": None,
            },
            "slot_summary": {},
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    path = Path(out_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload
