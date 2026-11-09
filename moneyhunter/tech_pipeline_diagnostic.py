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

# Audio brands (canonical keys). Longest aliases matched first in parse_tech_brand.
AUDIO_BRAND_KEYS = (
    "soundcore",
    "bose",
    "sony",
    "jbl",
    "sennheiser",
    "google",
    "samsung",
    "apple",
    "beats",
    "bowers_wilkins",
    "skullcandy",
    "nothing",
    "cmf",
    "sonos",
    "marshall",
    "jvc",
    "tcl",
    "technics",
    "shure",
    "akg",
)

# Multi-category brands: is_audio only with an audio model / audio keyword (not Watch).
MULTI_CATEGORY_AUDIO_BRANDS = frozenset({"apple", "samsung", "google", "sony", "marshall"})

# Dedicated audio brands: always is_audio when brand matches.
DEDICATED_AUDIO_BRANDS = frozenset(AUDIO_BRAND_KEYS) - MULTI_CATEGORY_AUDIO_BRANDS

NON_AUDIO_BRAND_KEYS = (
    "hp",
    "dell",
    "lenovo",
    "asus",
    "acer",
    "microsoft",
    "razer",
    "logitech",
    "corsair",
    "honor",
)

BRAND_KEYS = AUDIO_BRAND_KEYS + NON_AUDIO_BRAND_KEYS + ("other", "unknown")

AUDIO_KEYWORD_RE = re.compile(
    r"\b(?:headphones?|earbuds?|earphones?|in-ear|over-ear|headset|speaker)\b",
    re.I,
)

# Colour vocabulary (Part D). Longer compounds first.
COLOURS = (
    "space black",
    "space grey",
    "space gray",
    "starlight",
    "midnight",
    "black",
    "white",
    "green",
    "blue",
    "red",
    "grey",
    "gray",
    "silver",
    "gold",
    "purple",
    "pink",
    "orange",
    "yellow",
    "brown",
    "beige",
    "cream",
    "navy",
)

# Bounded model patterns per audio brand (first/closest-to-brand match wins).
# Capturing group 1 is the model string when present; else whole match.
AUDIO_MODEL_PATTERNS = {
    "soundcore": [
        r"\b(Space\s+One|Space\s+Q|Space\s+A\d+|Liberty\s+\d+\w*|R50[iI]|R60[iI]|P31[iI]|P40[iI]|Q\d+\w*|Life\s+[A-Z]\d+|Sleep\s+A\d+|Motion\s+\d+|Boom\s+2|Select\s+\d+\w*)\b",
    ],
    "bose": [
        r"\b(SoundLink\s+\w+(?:\s+\d+(?:nd|rd|th)?\s+Gen)?|QuietComfort\s+(?:Ultra|SC|45|35|SE)?|QC\s+Ultra|QC\d+|Sport\s+Earbuds)\b",
    ],
    "sony": [
        # Spec base + deviation: allow letter infix so WF-C510 / WH-CH520 / WH-1000XM5 match.
        r"\b(WH-?(?:[A-Z]{0,3})?\d+[\w-]*|WF-?(?:[A-Z]{0,3})?\d+[\w-]*|WI-?(?:[A-Z]{0,3})?\d+[\w-]*|LinkBuds\s+\w*|SRS-?\w+|MDR-?\w+|Pulse\s+\w+)\b",
    ],
    "jbl": [
        r"\b(Tune\s+\d+\w*|Flip\s+\d+|Charge\s+\d+|Go\s+\d+|PartyBox\s+\d+\w*|Live\s+\d+\w*|Quantum\s+\d+\w*|Wave\s+\w+)\b",
    ],
    "samsung": [
        r"\b(Galaxy\s+Buds\d*\w*(?:\s+(?:Pro|Plus|Live|FE))?|Galaxy\s+Watch\s+\d+\w*)\b",
    ],
    "apple": [
        r"\b(AirPods\s+(?:Max|Pro|4|\d+\w*)|AirPods\b|Beats\s+\w+|HomePod(?:\s+(?:Mini|2))?|Watch\s+(?:Ultra\s*\d*|Series\s+\d+|SE))\b",
    ],
    "beats": [
        r"\b(Studio\s+\w+|Solo\s+\d+\w*|Powerbeats\s+\w+|Fit\s+Pro|Beats\s+\w+)\b",
    ],
    "bowers_wilkins": [
        r"\b(PX[78]\s+S\d+[a-z]?|Px[78]\s+S\d+[a-z]?|PI\d\s+S\d+\w*|Zeppelin\s+\w*)\b",
    ],
    "skullcandy": [
        r"\b(Crusher\s+\w+|Hesh\s+\w+|Indy\s+\w*|Smokin['\u2019]?\s*Buds\s+\w+|Push\s+\w+|Grind\s+\w+|Dime\s+\d+)\b",
    ],
    "nothing": [
        r"\b(Phone\s+\(\d\)(?:\s+Pro)?|Headphone\s+\(\d\)(?:\s+Pro)?|Ear\s+\(\d\)(?:\s+Pro)?|Ear\s+Stick|Buds\s+\w+)\b",
    ],
    "cmf": [
        r"\b(Buds\s+[\w ]+|Headphone\s+Pro|Neckband\s+Pro|Watch\s+Pro(?:\s+\d)?)\b",
    ],
    "sonos": [
        r"\b(Ace|Era\s+\d+\w*|Roam\s+\d*|Move\s+\d*|Beam\s*\(?Gen\s*\d?\)?|Arc|Sub\s+\w*)\b",
    ],
    "marshall": [
        r"\b(Major\s+[IVX]+|Emberton\s+[IVX]*|Stanmore\s+[IVX]*|Woburn\s+[IVX]*|Willen|Kilburn\s+[IVX]*)\b",
    ],
    "jvc": [
        r"\b(Gumy\s+Band\s+\w+|Gumy\s+\w+|HA-?\w+)\b",
    ],
    "tcl": [
        r"\b(CrystalClip|MOVEAUDIO\s+\w+|SOCL\s+\w+)\b",
    ],
    "technics": [
        r"\b(EAH-\w+|AZ\d+\w*)\b",
    ],
    "shure": [
        r"\b(AONIC\s+\w+|SE\d+\w*|SRH\d+\w*)\b",
    ],
    "akg": [
        r"\b(K\d+\w*|N\d+\w*|Y\d+\w*)\b",
    ],
    "google": [
        # Spec table omitted google; keep bounded Pixel Buds only (no generic fallback).
        r"\b(Pixel\s+Buds(?:\s+(?:Pro|2a|A-Series|A\s+Series))?)\b",
    ],
    "sennheiser": [
        # Spec table omitted sennheiser; no generic fallback — model stays null unless extended later.
    ],
}

# Watch models are recorded but force is_audio false for multi-category brands.
WATCH_MODEL_RE = re.compile(r"\b(?:Galaxy\s+Watch|Watch\s+(?:Ultra|Series|SE)|Watch\s+Pro)\b", re.I)

# Legacy aliases kept for identity_match multi-model ambiguity checks (existing pipeline vocab).
SONY_MODEL_PATTERNS = (
    ("WH1000XM5", r"\bwh[ -]?1000xm5\b"),
    ("WH1000XM4", r"\bwh[ -]?1000xm4\b"),
    ("WFC710N", r"\bwf[ -]?c[ -]?710n\b"),
    ("WFC510", r"\bwf[ -]?c[ -]?510\b"),
    ("WHCH520", r"\bwh[ -]?ch[ -]?520\b"),
)


def _lookup(rows, url):
    for row in rows or []:
        if row.get("url") == url:
            return row
    return None


def _norm_ws(s):
    return re.sub(r"\s+", " ", str(s or "").strip())


def _nothing_brand_match(raw_title, t):
    """Guard plain-English 'nothing'.

    Deviation vs bare title-start: require a product-shaped continuation so
    "Nothing has changed in this SIM deal" is not a brand hit. Allowed shapes:
    Nothing (, CMF by Nothing, Nothing CMF, Nothing Ear|Headphone|Phone|Buds,
    or title-start Nothing followed immediately by those product tokens.
    """
    if re.search(r"(?i)\bcmf\s+by\s+nothing\b", t):
        return True
    if re.search(r"(?i)\bnothing\s*\(", t) or re.search(r"(?i)\bnothing\s*\(", raw_title or ""):
        return True
    if re.search(r"(?i)\bnothing\s+cmf\b", t):
        return True
    if re.search(r"(?i)\bnothing\s+(?:ear|headphone|phone|buds)\b", t):
        return True
    if re.match(r"(?i)^\s*nothing\s*(?:\(|cmf|ear|headphone|phone|buds)\b", raw_title or ""):
        return True
    return False


def _apple_brand_match(raw_title, t):
    """Apple brand with anti-false-positive guards (Big Apple / Honor / iD Mobile)."""
    if re.search(r"(?i)\bbig\s+apple\b", t):
        return False
    # Prefer clear Apple product tokens.
    if re.search(r"(?i)\b(?:airpods?|homepod|iphone|ipad|macbook|imac|apple\s+watch)\b", t):
        return True
    if not re.search(r"(?i)\bapple\b", t):
        return False
    # Reject when another phone brand is the subject.
    if re.search(r"(?i)\b(?:honor|id\s*mobile|huawei|xiaomi|oneplus)\b", t):
        return False
    return True


def parse_tech_brand(title):
    """Deterministic tech brand label (diagnostic only).

    Audio aliases longest-first; non-audio tech brands labelled but excluded from audio scoring.
    other = brand not in either list (still a product signal); unknown = empty / no brand signal.

    Deviations (Task 12):
    - nothing: guarded against plain English (title-start / Nothing ( / CMF by Nothing / Nothing CMF /
      Nothing Ear|Headphone|Phone|Buds).
    - apple: requires Apple product token or bare Apple without Big Apple / Honor / iD Mobile subjects.
    - Multi-category is_audio handled separately in classify_is_audio (not here).
    """
    if title is None:
        return "unknown"
    raw = str(title).strip()
    if not raw:
        return "unknown"
    t = variants.clean(raw)

    # Longest-first audio aliases.
    # Deviation: variants.clean strips '&', so also match "bowers wilkins".
    if re.search(r"(?i)\bbowers\s*(?:&|and)?\s*wilkins\b|\bb\s*&\s*w\b", t) or re.search(
        r"(?i)\bbowers\s+wilkins\b", t
    ):
        return "bowers_wilkins"
    if M.has(t, "soundcore") or M.has(t, "anker"):
        return "soundcore"
    if M.has(t, "skullcandy"):
        return "skullcandy"
    if M.has(t, "sennheiser"):
        return "sennheiser"
    if _nothing_brand_match(raw, t):
        return "nothing"
    if M.has(t, "cmf"):
        return "cmf"
    if M.has(t, "sonos"):
        return "sonos"
    if M.has(t, "marshall"):
        return "marshall"
    if M.has(t, "technics"):
        return "technics"
    if M.has(t, "sennheiser"):
        return "sennheiser"
    if M.has(t, "pixel buds") or M.has(t, "google"):
        return "google"
    if M.has(t, "galaxy buds") or M.has(t, "galaxy watch") or M.has(t, "samsung"):
        return "samsung"
    if M.has(t, "beats"):
        # Beats as its own brand key when not already routed via Apple alias above.
        return "beats"
    if _apple_brand_match(raw, t) or M.has(t, "airpods"):
        return "apple"
    if M.has(t, "bose"):
        return "bose"
    if M.has(t, "sony"):
        return "sony"
    if M.has(t, "jbl"):
        return "jbl"
    if M.has(t, "jvc"):
        return "jvc"
    if M.has(t, "tcl"):
        return "tcl"
    if M.has(t, "shure"):
        return "shure"
    if M.has(t, "akg"):
        return "akg"

    # Non-audio tech brands (label only; no model extraction).
    for brand in NON_AUDIO_BRAND_KEYS:
        if M.has(t, brand):
            return brand

    # Identifiable consumer-audio / tech product language without a named brand.
    if re.search(
        r"\b(?:earbuds?|earphones?|headphones?|headset|buds?|speaker|bluetooth|anc|noise.?cancelling|"
        r"laptop|desktop|macbook|iphone|tablet|monitor|keyboard|mouse)\b",
        t,
        re.I,
    ):
        return "other"
    return "unknown"


def _brand_token_offset(title, brand):
    """Character offset of the brand token in the (cleaned) title; 0 if unknown."""
    t = variants.clean(str(title or ""))
    aliases = {
        "soundcore": (r"soundcore", r"anker"),
        "bowers_wilkins": (r"bowers\s*(?:&|and)?\s*wilkins", r"bowers\s+wilkins", r"b\s*&\s*w"),
        "nothing": (r"nothing",),
        "cmf": (r"cmf",),
        "google": (r"google", r"pixel"),
        "samsung": (r"samsung", r"galaxy"),
        "apple": (r"apple", r"airpods"),
        "beats": (r"beats",),
    }
    pats = aliases.get(brand, (re.escape(brand),))
    best = None
    for pat in pats:
        m = re.search(rf"\b{pat}\b", t, re.I)
        if m and (best is None or m.start() < best):
            best = m.start()
    return 0 if best is None else best


def parse_tech_model(title, brand):
    """Bounded model label from title for audio brands. Diagnostic only."""
    if not title or brand not in AUDIO_MODEL_PATTERNS:
        return None
    patterns = AUDIO_MODEL_PATTERNS.get(brand) or []
    if not patterns:
        return None
    raw = str(title)
    brand_off = _brand_token_offset(raw, brand)
    best = None  # (distance, start, model)
    for pat in patterns:
        for m in re.finditer(pat, raw, re.I):
            model = _norm_ws(m.group(1) if m.lastindex else m.group(0))
            if not model:
                continue
            dist = abs(m.start() - brand_off)
            cand = (dist, m.start(), model)
            if best is None or cand < best:
                best = cand
    return None if best is None else best[2]


def parse_tech_colour(title, brand=None, model=None):
    """Return colour string, 'ambiguous', or None. Diagnostic only (Task 12 Part D).

    Colour words must appear outside the brand/model span so 'Red Bull' is not a colour.
    """
    if not title:
        return None
    raw = str(title)
    t = variants.clean(raw)
    # Build a mask of brand/model spans on the cleaned title where possible.
    masked = t
    spans = []
    if brand and brand not in ("other", "unknown"):
        # Mask brand aliases on cleaned text.
        alias_map = {
            "bowers_wilkins": [r"bowers\s*(?:&|and)?\s*wilkins", r"bowers\s+wilkins", r"b\s*&\s*w"],
            "soundcore": [r"soundcore", r"anker"],
            "nothing": [r"nothing"],
            "google": [r"google"],
            "samsung": [r"samsung", r"galaxy"],
            "apple": [r"apple", r"airpods"],
            "skullcandy": [r"skullcandy"],
        }
        for pat in alias_map.get(brand, [re.escape(brand.replace("_", " "))]):
            for m in re.finditer(rf"\b{pat}\b", masked, re.I):
                spans.append((m.start(), m.end()))
    if model:
        mpat = re.escape(_norm_ws(model)).replace(r"\ ", r"\s+")
        for m in re.finditer(mpat, masked, re.I):
            spans.append((m.start(), m.end()))
    # Also mask known brand phrases that contain colour-looking words.
    for m in re.finditer(r"\bred\s+bull\b", masked, re.I):
        spans.append((m.start(), m.end()))

    def covered(start, end):
        return any(s <= start and end <= e for s, e in spans)

    # Explicit multi-colour marketing language / "black or silver" style.
    colour_word = (
        r"black|white|green|blue|red|grey|gray|silver|gold|purple|pink|orange|yellow|brown|"
        r"beige|cream|navy|starlight|midnight"
    )
    if re.search(
        rf"\b(?:{colour_word})\b\s*(?:or|/|,|and)\s*\b(?:{colour_word})\b",
        t,
        re.I,
    ) or re.search(
        r"\bseveral colours?\b|\bvarious colours?\b|\bassorted colours?\b|\bmulti[ -]?colou?r\b|"
        r"\ball colours?\b|\b\d+\s+colours?\b|\b2 colours?\b",
        t,
        re.I,
    ):
        return "ambiguous"

    found = []
    for colour in COLOURS:
        pat = rf"\b{re.escape(colour)}\b"
        for m in re.finditer(pat, t, re.I):
            if covered(m.start(), m.end()):
                continue
            found.append(colour.casefold())
            break

    # Deduplicate compound vs base.
    compounds = {
        "space black": ("black",),
        "space grey": ("grey", "gray"),
        "space gray": ("grey", "gray"),
    }
    for compound, bases in compounds.items():
        if compound in found:
            found = [c for c in found if c not in bases and c != compound] + [compound]

    # Normalise gray→grey for single-colour reporting consistency when only gray matched.
    uniq = []
    for c in found:
        if c not in uniq:
            uniq.append(c)
    if "grey" in uniq and "gray" in uniq:
        uniq = [c for c in uniq if c != "gray"]

    if len(uniq) > 1:
        return "ambiguous"
    if len(uniq) == 1:
        return uniq[0]
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


def classify_is_audio(title, brand, model):
    """Task 12 is_audio with multi-category tension resolved.

    Deviation from naive 'audio-list brand OR keyword':
    - Dedicated audio brands → always True.
    - Multi-category (apple/samsung/google/sony/marshall) → True only if an audio model
      pattern matches (AirPods/HomePod/Beats/Galaxy Buds/etc., NOT Watch) OR an audio keyword
      matches; Galaxy Watch / Apple Watch → False.
    - Non-audio brands (hp/dell/…) → False.
    - other/unknown → True only on audio keyword.
    """
    t = variants.clean(str(title or ""))
    if brand in NON_AUDIO_BRAND_KEYS:
        return False
    if brand in DEDICATED_AUDIO_BRANDS:
        return True
    if brand in MULTI_CATEGORY_AUDIO_BRANDS:
        if model and WATCH_MODEL_RE.search(str(model)):
            return False
        if model and not WATCH_MODEL_RE.search(str(model)):
            # Model extracted via audio brand patterns — treat as audio unless Watch.
            # Exception: Apple Phone/Mac model strings are not in apple audio patterns.
            return True
        if AUDIO_KEYWORD_RE.search(t):
            # Keyword alone: still reject clear non-audio Apple/Samsung form-factors.
            if re.search(r"(?i)\b(?:macbook|imac|iphone|ipad|galaxy\s+s\d+|galaxy\s+z|galaxy\s+tab|pixel\s+\d+)\b", t):
                return False
            if WATCH_MODEL_RE.search(t):
                return False
            return True
        return False
    # other / unknown
    if AUDIO_KEYWORD_RE.search(t):
        if re.search(r"(?i)\b(?:macbook|imac|iphone|ipad|laptop|desktop|tablet|sim\b)\b", t):
            return False
        return True
    return False


def brand_audio_or_not(brand):
    if brand in AUDIO_BRAND_KEYS:
        return "audio"
    if brand in NON_AUDIO_BRAND_KEYS:
        return "non_audio"
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
    if colour == "ambiguous":
        return "ambiguous", None, None
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
    - record is_audio / brand_audio_or_not and audio_subset aggregates (Task 12)
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
            colour = parse_tech_colour(title, brand=brand, model=model)
            condition = parse_tech_condition(title, offer.get("desc") or "", price)
            is_audio = classify_is_audio(title, brand, model)
            brand_kind = brand_audio_or_not(brand)
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
                "is_audio": bool(is_audio),
                "brand_audio_or_not": brand_kind,
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
                    "is_audio": bool(is_audio),
                    "failure_stage": stage,
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

        audio_entries = [e for e in entries if e["is_audio"]]
        by_brand_audio = {k: 0 for k in AUDIO_BRAND_KEYS}
        by_parse_readiness_audio = {
            "brand_model_colour_parseable": 0,
            "brand_model_only_parseable": 0,
            "brand_only_parseable": 0,
            "not_parseable": 0,
        }
        by_condition_audio = {"new": 0, "refurbished": 0, "used": 0, "unknown": 0}
        for e in audio_entries:
            if e["brand_parsed"] in by_brand_audio:
                by_brand_audio[e["brand_parsed"]] += 1
            by_parse_readiness_audio[e["parse_readiness"]] = (
                by_parse_readiness_audio.get(e["parse_readiness"], 0) + 1
            )
            by_condition_audio[e["condition_parsed"]] = by_condition_audio.get(e["condition_parsed"], 0) + 1
        audio_new_publishable_pipeline = sum(
            1
            for e in audio_entries
            if e["condition_parsed"] == "new"
            and e["parse_readiness"] == "brand_model_colour_parseable"
        )

        brand_comparison = {}
        for brand in BRAND_KEYS:
            subset = [e for e in entries if e["brand_parsed"] == brand]
            stages = [e["failure_stage"] for e in subset]
            brand_comparison[brand] = {
                "offers": len(subset),
                "parseable_as_audio_identity": sum(
                    1
                    for e in subset
                    if e["is_audio"] and e["parse_readiness"] == "brand_model_colour_parseable"
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
                "audio_subset": {
                    "total_audio_offers": len(audio_entries),
                    "by_brand_audio": by_brand_audio,
                    "by_parse_readiness_audio": by_parse_readiness_audio,
                    "by_condition_audio": by_condition_audio,
                    "audio_new_publishable_pipeline": audio_new_publishable_pipeline,
                },
            },
            "brand_comparison": brand_comparison,
            "error": None,
            "brand_other_vs_unknown_rule": (
                "other = brand not in the audio or non-audio lists (product language present); "
                "unknown = empty title or no brand/product signal"
            ),
            "is_audio_rule": (
                "dedicated audio brands always is_audio; multi-category apple/samsung/google/sony/marshall "
                "require audio model or audio keyword and exclude Watch/MacBook/iPhone form-factors; "
                "non-audio brands false; other/unknown require audio keyword"
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
