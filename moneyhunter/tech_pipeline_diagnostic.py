"""Read-only tech pipeline diagnostic. Never changes gates, parsers, allocation, or routing."""
from __future__ import annotations

import json
import re
import traceback
from pathlib import Path

from . import details, market, matching as M, publication, variants

STAGES = (
    "identity_not_supported",
    "identity_ambiguous",
    "refurbished_excluded",
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

BRAND_KEYS = (
    "soundcore",
    "bose",
    "sony",
    "jbl",
    "sennheiser",
    "google",
    "samsung",
    "apple",
    "beats",
    "other",
    "unknown",
)

# Diagnostic colour vocabulary (label only; does not extend identity lanes).
COLOURS = (
    "glass blue",
    "smoky pink",
    "space black",
    "glacier white",
    "lavender purple",
    "blue dusk",
    "alpine sage",
    "graphite",
    "charcoal",
    "sandstone",
    "lavender",
    "black",
    "white",
    "blue",
    "purple",
    "pink",
    "yellow",
    "silver",
    "beige",
    "green",
    "red",
    "brown",
    "hazel",
    "iris",
    "grey",
    "gray",
)

SONY_MODEL_PATTERNS = (
    ("WH1000XM5", r"\bwh[ -]?1000xm5\b"),
    ("WH1000XM4", r"\bwh[ -]?1000xm4\b"),
    ("WFC710N", r"\bwf[ -]?c[ -]?710n\b"),
    ("WFC510", r"\bwf[ -]?c[ -]?510\b"),
    ("WHCH520", r"\bwh[ -]?ch[ -]?520\b"),
)

SOUNDCORE_MODEL_PATTERNS = (
    ("P40I", r"\bp40i\b"),
    ("R50I", r"\br50i\b"),
    ("Q21I", r"\bq21i\b"),
)

OTHER_MODEL_PATTERNS = (
    ("Pixel Buds Pro", r"\bpixel buds? pro\b"),
    ("Pixel Buds 2a", r"\bpixel buds? 2a\b"),
    ("Pixel Buds A-Series", r"\bpixel buds? a[ -]?series\b"),
    ("Pixel Buds", r"\bpixel buds?\b"),
    ("Galaxy Buds FE", r"\bgalaxy buds? fe\b"),
    ("Galaxy Buds2 Pro", r"\bgalaxy buds? ?2 pro\b"),
    ("Galaxy Buds2", r"\bgalaxy buds? ?2\b"),
    ("Galaxy Buds Pro", r"\bgalaxy buds? pro\b"),
    ("Galaxy Buds", r"\bgalaxy buds?\b"),
    ("AirPods Pro", r"\bairpods? pro\b"),
    ("AirPods Max", r"\bairpods? max\b"),
    ("AirPods", r"\bairpods?\b"),
    ("QuietComfort", r"\bquietcomfort\b|\bqc[ -]?\d{2}\b"),
    ("SoundLink", r"\bsoundlink\b"),
)


def _lookup(rows, url):
    for row in rows or []:
        if row.get("url") == url:
            return row
    return None


def parse_tech_brand(title):
    """Deterministic tech brand label (diagnostic only).

    Rule (Task 10-style):
    - Named brands / aliases → canonical key (soundcore/anker→soundcore; google/pixel buds→google;
      samsung/galaxy buds→samsung; apple/airpods→apple; beats→beats; etc.)
    - Identifiable audio/tech product language but not in the named list → "other"
    - Empty title or no brand/product signal → "unknown"
    """
    if title is None:
        return "unknown"
    raw = str(title).strip()
    if not raw:
        return "unknown"
    t = variants.clean(raw)
    # Multi-token / alias checks first.
    if M.has(t, "soundcore") or M.has(t, "anker"):
        return "soundcore"
    if M.has(t, "pixel buds") or M.has(t, "google"):
        return "google"
    if M.has(t, "galaxy buds") or M.has(t, "samsung"):
        return "samsung"
    if M.has(t, "airpods") or M.has(t, "apple"):
        return "apple"
    if M.has(t, "beats"):
        return "beats"
    if M.has(t, "sennheiser"):
        return "sennheiser"
    if M.has(t, "sony"):
        return "sony"
    if M.has(t, "bose"):
        return "bose"
    if M.has(t, "jbl"):
        return "jbl"
    # Identifiable consumer-audio / tech product language without a named brand.
    if re.search(
        r"\b(?:earbuds?|earphones?|headphones?|headset|buds?|speaker|bluetooth|anc|noise.?cancelling)\b",
        t,
        re.I,
    ):
        return "other"
    return "unknown"


def parse_tech_model(title, brand):
    """Best-effort model label from title. Diagnostic only."""
    if not title:
        return None
    t = variants.clean(str(title))
    patterns = []
    if brand == "sony":
        patterns = SONY_MODEL_PATTERNS
    elif brand == "soundcore":
        patterns = SOUNDCORE_MODEL_PATTERNS
    else:
        patterns = OTHER_MODEL_PATTERNS + SONY_MODEL_PATTERNS + SOUNDCORE_MODEL_PATTERNS
    for model, pat in patterns:
        if re.search(pat, t, re.I):
            return model
    return None


def parse_tech_colour(title):
    """Return colour string, 'ambiguous', or None. Diagnostic only."""
    if not title:
        return None
    t = variants.clean(str(title))
    if re.search(
        r"\b(?:black|white|blue|purple|pink|yellow|silver|beige|green|red|brown|hazel|iris)\b\s*(?:or|/|,|and)\s*\b(?:black|white|blue|purple|pink|yellow|silver|beige|green|red|brown|hazel|iris)\b",
        t,
    ) or re.search(r"\bseveral colours?\b|\bvarious colours?\b|\bassorted colours?\b|\bmulti[ -]?colou?r\b", t):
        return "ambiguous"
    found = []
    for colour in COLOURS:
        if M.has(t, colour):
            found.append(colour)
    # Deduplicate overlapping compound colours vs base tokens.
    if "glass blue" in found or "blue dusk" in found:
        found = [c for c in found if c != "blue"]
    if "smoky pink" in found:
        found = [c for c in found if c != "pink"]
    if "space black" in found:
        found = [c for c in found if c != "black"]
    if "glacier white" in found:
        found = [c for c in found if c != "white"]
    if "lavender purple" in found:
        found = [c for c in found if c not in ("lavender", "purple")]
    if len(found) > 1:
        return "ambiguous"
    if len(found) == 1:
        return found[0]
    return None


def parse_tech_condition(title, desc="", price=None):
    """new / refurbished / used / unknown from title/desc keywords."""
    text = variants.clean(" ".join(str(x or "") for x in (title, desc)))
    if re.search(r"\b(?:refurb(?:ished)?|renewed|open[ -]?box|warehouse)\b", text, re.I):
        return "refurbished"
    if re.search(r"\b(?:pre[ -]?owned|used)\b", text, re.I):
        return "used"
    if isinstance(price, (int, float)) and not isinstance(price, bool) and price > 0:
        return "new"
    if title and str(title).strip():
        return "new"
    return "unknown"


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
        for key in ("ask_estimate", "ask_context", "publication_proof", "ask_status", "title", "category"):
            if row.get(key) in (None, "") and research.get(key) is not None:
                row[key] = research[key]
        if row.get("price") is None and research.get("item_price") is not None:
            row["price"] = research.get("item_price")
    return row


def _refurb_or_used_excluded(offer):
    """True when existing pipeline BAD/refurb filters would reject the title/desc."""
    title = offer.get("title") or ""
    desc = offer.get("desc") or ""
    t = variants.clean(title)
    if M.has(t, *variants.BAD):
        return True
    if re.search(r"\b(?:ex[- ]display|damaged|refurbished|used condition)\b", desc, re.I):
        return True
    return False


def _identity_match_result(offer, brand, model, colour, condition):
    """Reflect existing market.identity behaviour; classify None without changing parser."""
    try:
        ident = market.identity(offer)
    except Exception:
        ident = None
    if ident:
        return "matched", str(getattr(ident, "match", None) or None), ident

    if condition in ("refurbished", "used") or _refurb_or_used_excluded(offer):
        return "refurbished_excluded", None, None

    title = offer.get("title") or ""
    t = variants.clean(title)
    # Ambiguity signals mirroring audio/Sony rejection modes.
    if colour == "ambiguous":
        return "ambiguous", None, None
    # Multiple Sony models
    sony_hits = [m for m, pat in SONY_MODEL_PATTERNS if re.search(pat, t, re.I)]
    if len(sony_hits) > 1:
        return "ambiguous", None, None
    audio_hits = [x for x in variants.AUDIO if re.search(x[2], t)]
    if len(audio_hits) > 1:
        return "ambiguous", None, None
    return "not_supported", None, None


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
        e.get("phase") == "inspect_skip" or e.get("denial_reason") == "not_risky_lowest" for e in evs
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
    sellers = None
    support = None
    if isinstance(estimate, dict):
        if isinstance(estimate.get("seller_count"), int):
            sellers = estimate["seller_count"]
        if isinstance(estimate.get("low_price_supporting_sellers"), int):
            support = estimate["low_price_supporting_sellers"]
    if sellers is None or support is None:
        by = {}
        for o in (ctx or {}).get("offers") or []:
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
            support = sum(1 for v in by.values() if v <= low * 1.1) if support is None else support
    return sellers or 0, support or 0


def _shipping_unknown(row, estimate, proof_reason):
    if proof_reason == "shipping_unknown":
        return True
    detail = (row.get("ask_context") or {}).get("lowest_detail") or {}
    for reason in detail.get("reasons") or []:
        if "shipping" in str(reason).lower() and "not supplied" in str(reason).lower():
            return True
    for sc in detail.get("sub_checks") or []:
        if sc.get("sub_check_failed") == details.SUB_SHIP_UNKNOWN:
            return True
    return False


def _economics_negative(estimate, proof_ok):
    if not isinstance(estimate, dict):
        return False
    if estimate.get("estimated_opportunity") or estimate.get("worth_reviewing"):
        return False
    if proof_ok:
        net = estimate.get("net")
        if isinstance(net, (int, float)) and net < 0:
            return True
    checks = " ".join(str(c) for c in (estimate.get("checks") or []))
    if re.search(r"net|roi|strong policy|£\d+", checks, re.I):
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
    return isinstance(price, (int, float)) and price > cap


def classify_failure_stage(offer, research, identity_result, ident, proof, estimate, getitem):
    """First failing stage in Task 9 vocabulary + refurbished_excluded."""
    ctx = (research or {}).get("ask_context") or offer.get("ask_context") or {}
    proof_ok = isinstance(proof, dict) and proof.get("ok") is True
    proof_reason = None if proof_ok else (proof or {}).get("reason")
    row = _merged_row(offer, research)

    if identity_result == "refurbished_excluded":
        return "refurbished_excluded", proof_reason or "refurbished_excluded", None
    if identity_result == "not_supported":
        return "identity_not_supported", proof_reason or "unsupported_exact_identity", None
    if identity_result == "ambiguous":
        return "identity_ambiguous", proof_reason or "ambiguous_primary_offer", None

    # Slot starvation is a detail-check hold (Task 10 invariant).
    if getitem.get("getitem_denied_slots_exhausted"):
        return "detail_check_pending", "detail_check_pending", None

    comparator_count = _comparator_count(row, estimate)
    ask_status = row.get("ask_status") or (research or {}).get("ask_status")
    if comparator_count <= 0 and not (ctx.get("offers") or []):
        return "no_comparators_found", proof_reason or "no_supported_resale_estimate", None

    if getitem.get("getitem_not_risky") or any(
        e.get("denial_reason") == "not_risky_lowest" for e in _slot_events_for(getattr(ident, "match", None))
    ):
        return "no_risky_lowest", proof_reason or "not_risky_lowest", None

    detail_status = None
    if isinstance(estimate, dict):
        detail_status = estimate.get("detail_status")
    detail_status = detail_status or ctx.get("detail_status")
    if proof_reason == "detail_check_pending" or detail_status in ("awaiting_detail_budget", "price_changed"):
        return "detail_check_pending", "detail_check_pending", None
    if proof_reason == "detail_check_failed" or detail_status in ("conflict", "incomplete", "error"):
        return "detail_check_failed", "detail_check_failed", None

    sellers, support = _seller_support(estimate, ctx)
    if proof_reason == "fewer_than_three_exact_independent_comparators" or (
        sellers and sellers < 3 and estimate
    ):
        return "comparator_depth_insufficient", proof_reason or "fewer_than_three_exact_independent_comparators", None
    if proof_reason == "low_price_not_supported" or (
        support is not None and support < 2 and estimate and sellers >= 3
    ):
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

    return "other", proof_reason, proof_reason or ask_status or "unclassified tech pipeline hold"


def _parse_readiness(brand, model, colour):
    named = brand not in ("other", "unknown")
    if named and model and colour and colour != "ambiguous":
        return "brand_model_colour_parseable"
    if named and model:
        return "brand_model_only_parseable"
    if named:
        return "brand_only_parseable"
    return "not_parseable"


def _dominant_stage(stages):
    if not stages:
        return None
    counts = {}
    for s in stages:
        counts[s] = counts.get(s, 0) + 1
    best, best_n = None, -1
    for stage in STAGES:
        n = counts.get(stage, 0)
        if n > best_n:
            best, best_n = stage, n
    return best


def log_tech_pipeline(offers, research_rows, out_path="tech_pipeline_diagnostic.json", state=None):
    """
    For each offer where category == "tech":
    - record offer title, URL, merchant price
    - record brand_parsed / model_parsed / colour_parsed / condition_parsed
    - record identity_match reflecting existing pipeline behaviour
    - record research model / failure stage / blocker / getItem / publication_qualified
    Read-only: never calls getItem; never changes gates/parsers/allocation/routing.
    """
    entries = []
    tech_offers = []
    try:
        for offer in offers or []:
            if offer.get("category") != "tech":
                continue
            research = _lookup(research_rows, offer.get("url"))
            row = _merged_row(offer, research)
            title = offer.get("title") or row.get("title") or ""
            price = _merchant_price(offer, research)
            brand = parse_tech_brand(title)
            model = parse_tech_model(title, brand)
            colour = parse_tech_colour(title)
            condition = parse_tech_condition(title, offer.get("desc") or "", price)
            identity_result, canonical, ident = _identity_match_result(
                offer, brand, model, colour, condition
            )
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
            if qualified:
                stage, blocker, note = "publication_qualified", None, None
            comparator_count = _comparator_count(row, estimate)
            readiness = _parse_readiness(brand, model, colour)

            entry = {
                "offer_title": title,
                "offer_url": offer.get("url"),
                "merchant_price": price,
                "brand_parsed": brand,
                "model_parsed": model,
                "colour_parsed": colour,
                "condition_parsed": condition,
                "identity_match": identity_result,
                "canonical_identity": canonical,
                "research_model_generated": bool(model_generated),
                "failure_stage": stage,
                "blocker": blocker,
                "getitem_granted": getitem["getitem_granted"],
                "getitem_cached": getitem["getitem_cached"],
                "getitem_denied_slots_exhausted": getitem["getitem_denied_slots_exhausted"],
                "getitem_not_risky": getitem["getitem_not_risky"],
                "comparator_count": comparator_count,
                "publication_qualified": bool(qualified),
                "parse_readiness": readiness,
            }
            if brand in ("apple", "beats"):
                entry["note"] = (
                    "Apple / AirPods and Beats are recorded for coverage diagnostics but remain "
                    "excluded from automatic pricing identity lanes"
                )
            if note and stage == "other":
                entry["note"] = ((entry.get("note") + "; ") if entry.get("note") else "") + str(note)
            entries.append(entry)
            tech_offers.append(
                {
                    "offer_title": title,
                    "offer_url": offer.get("url"),
                    "merchant_price": price,
                    "brand_parsed": brand,
                    "model_parsed": model,
                    "colour_parsed": colour,
                    "condition_parsed": condition,
                }
            )

        by_brand = {k: 0 for k in BRAND_KEYS}
        by_condition = {"new": 0, "refurbished": 0, "used": 0, "unknown": 0}
        by_stage = {s: 0 for s in STAGES}
        by_parse_readiness = {
            "brand_model_colour_parseable": 0,
            "brand_model_only_parseable": 0,
            "brand_only_parseable": 0,
            "not_parseable": 0,
        }
        for e in entries:
            by_brand[e["brand_parsed"]] = by_brand.get(e["brand_parsed"], 0) + 1
            by_condition[e["condition_parsed"]] = by_condition.get(e["condition_parsed"], 0) + 1
            by_stage[e["failure_stage"]] = by_stage.get(e["failure_stage"], 0) + 1
            by_parse_readiness[e["parse_readiness"]] = by_parse_readiness.get(e["parse_readiness"], 0) + 1

        brand_comparison = {}
        for brand in BRAND_KEYS:
            subset = [e for e in entries if e["brand_parsed"] == brand]
            stages = [e["failure_stage"] for e in subset]
            brand_comparison[brand] = {
                "offers": len(subset),
                "parseable_as_audio_identity": sum(
                    1 for e in subset if e["parse_readiness"] == "brand_model_colour_parseable"
                ),
                "models_generated": sum(1 for e in subset if e["research_model_generated"]),
                "comparators_found": sum(1 for e in subset if (e.get("comparator_count") or 0) > 0),
                "publication_qualified": sum(1 for e in subset if e["publication_qualified"]),
                "dominant_failure_stage": _dominant_stage(stages),
            }

        payload = {
            "entries": entries,
            "tech_offers": tech_offers,
            "aggregate": {
                "total_offers": len(entries),
                "by_brand": by_brand,
                "by_condition": by_condition,
                "by_stage": by_stage,
                "by_parse_readiness": by_parse_readiness,
                "publication_qualified_count": sum(1 for e in entries if e["publication_qualified"]),
                "above_budget_count": sum(1 for e in entries if e["failure_stage"] == "above_budget"),
            },
            "brand_comparison": brand_comparison,
            "error": None,
            "brand_other_vs_unknown_rule": (
                "other = identifiable audio/tech product language without a named brand; "
                "unknown = empty title or no brand/product signal"
            ),
        }
    except Exception as exc:
        payload = {
            "entries": entries,
            "tech_offers": tech_offers,
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
