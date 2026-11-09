"""Read-only tools publication diagnostic. Never changes gates, routes, or state."""
from __future__ import annotations

import json
import traceback
from pathlib import Path


def _identity_string(offer):
    """Reuse market.identity; never invent a new matcher."""
    try:
        from . import market
        ident = market.identity(offer)
    except Exception:
        return "none"
    if not ident:
        return "none"
    return str(getattr(ident, "match", None) or "none")


def _lookup(rows, url):
    for row in rows or []:
        if row.get("url") == url:
            return row
    return None


def _publication_state(offer, research_row, publication_rows):
    """Reuse existing publication proof / hold reason fields only."""
    proof = offer.get("publication_proof")
    if not isinstance(proof, dict) and research_row is not None:
        proof = research_row.get("publication_proof")
    if not isinstance(proof, dict):
        pub = _lookup(publication_rows, offer.get("url"))
        if pub is not None:
            proof = pub.get("publication_proof") if isinstance(pub.get("publication_proof"), dict) else pub
    if not isinstance(proof, dict):
        return False, None, None
    ok = proof.get("ok") is True
    if ok:
        return True, None, None
    # Existing publication.proof deny payload uses field name "reason".
    if "reason" in proof:
        return False, "reason", proof.get("reason")
    if "hold_reason" in proof:
        return False, "hold_reason", proof.get("hold_reason")
    return False, None, None


def log_tool_publication_reasons(offers, research_rows, publication_rows, out_path="tools_diagnostic.json"):
    """
    For each offer where category == 'tools':
    - record offer title
    - record exact identity string (or "none")
    - record whether a research model was generated
    - record the specific publication gate that failed
    - record the blocker field name from the existing code
    Write the list to out_path as JSON.
    Do not change any state, route, or gate.
    """
    entries = []
    try:
        for offer in offers or []:
            if offer.get("category") != "tools":
                continue
            research = _lookup(research_rows, offer.get("url"))
            qualified, blocker_field, blocker_reason = _publication_state(
                offer, research, publication_rows
            )
            model_generated = bool(
                offer.get("ask_estimate")
                or (research or {}).get("ask_estimate")
            )
            entries.append(
                {
                    "title": offer.get("title") or "",
                    "identity": _identity_string(offer),
                    "model_generated": bool(model_generated),
                    "publication_qualified": bool(qualified),
                    "blocker_field": blocker_field,
                    "blocker_reason": blocker_reason,
                    "url": offer.get("url"),
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
