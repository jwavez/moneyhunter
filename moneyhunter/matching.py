"""Strict comp matching. A comp only prices a deal when we are sure it is the SAME product.
Anything uncertain returns (None, reason) and the deal is shown as unpriced, never graded."""
import re

def norm(s: str) -> str:
    s = (s or "").lower().replace("&amp;", "&")
    s = re.sub(r"[’'`.]", "", s)
    return " " + re.sub(r"[^a-z0-9£+]+", " ", s).strip() + " "

def has(t: str, *words) -> bool:
    return any(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", t) for w in words)

KIDS = ("girls", "boys", "kids", "kid", "junior", "juniors", "infant", "infants", "toddler", "toddlers", "child", "childrens",
        "children", "youth", "baby", "younger", "older", "little kids", "big kids", "gs", "ps", "td", "jnr", "cadet")
BUNDLE = ("bundle", "pack of", "set of", "twin pack", "multipack", "multi pack", "combo", "bundled")
PREORDER = ("pre order", "preorder", "pre orders", "coming soon")
CONDITION = ("used", "resale", "amazon resale", "second hand", "secondhand", "pre owned", "preowned", "refurbished", "refurb", "renewed", "open box", "warehouse", "like new",
             "grade a", "grade b", "grade c", "b grade", "ex display", "damaged", "grey import", "import", "imported",
             "tester", "unboxed", "box damage", "damaged box", "damage", "no box", "spares", "faulty", "very good condition", "good condition")
EDITIONS = ("deluxe", "collectors", "collector", "limited edition", "special edition", "gold edition", "ultimate edition",
            "complete edition", "definitive edition", "game of the year", "goty", "steelbook", "launch edition", "day one",
            "directors cut", "remastered", "switch 2 edition", "nintendo switch 2", "switch 2", "digital", "code in a box",
            "download", "dlc", "season pass", "upgrade pack", "expansion", "dlc pass", "membership")
ACCESSORY = ("amiibo", "case", "controller", "skin", "charger", "stand", "dock", "headset", "figure", "plush", "lanyard",
             "keyring", "poster", "guide", "artbook", "soundtrack", "vinyl", "t shirt", "hoodie", "mug")
TOOL_KIT = ("kit", "battery", "batteries", "charger", "ah", "2ah", "4ah", "5ah", "p1", "p2", "d1", "d2", "m1", "m2",
            "case", "tstak", "makpac", "twin", "combo")
TOOL_BRANDS = ("dewalt", "makita", "milwaukee", "bosch", "ryobi", "hikoki", "einhell", "festool", "metabo")
TOOL_PARTS = ("chuck", "armature", "for cordless", "rotor", "stator", "gear", "clutch", "trigger", "carbon brushes", "gearbox", "replacement", "spare", "spares", "parts", "part", "housing", "motor", "switch", "brushes", "n438603")
NON_GENUINE = ("for dewalt", "for makita", "fit for", "fits", "compatible", "20v", "20v max", "2000rpm", "xcat", "type")
TOOL_EXTRAS = ("bit set", "bit holder", "tool bag", "bag", "set", "drills", "toughsystem", "with case", "in case", "impact driver with", "with")
PLATFORMS = ("ps4", "ps5", "xbox", "switch", "pc", "xbox one", "series x")

def _multipack(t):
    t = re.sub(r"(?<![a-z0-9])\d{3,4}\s?(pcs|pc|pieces|piece)(?![a-z0-9])", " ", t)   # LEGO piece counts are not multipacks
    return re.search(r"(?<![a-z0-9])(\d+)\s?x(?![a-z0-9])|(?<![a-z0-9])x\s?(\d+)(?![a-z0-9])|(?<![a-z0-9])\d+\s?(pack|pk|pcs|pairs)(?![a-z0-9])", t)

def _ml(t):
    return set(re.findall(r"(\d{2,4})\s?ml(?![a-z])", t))

def _kids_size(t):
    t = re.sub(r"u\.k\.?", "uk", t.lower())   # use the RAW title: norm() turns "4.5" into "45"
    m = re.search(r"(?<![a-z0-9])(?:uk\s?)?size\s?(\d{1,2}(?:\.5)?)(?![a-z0-9])|(?<![a-z0-9])uk\s?(\d{1,2}(?:\.5)?)(?![a-z0-9])", t)
    v = m and (m.group(1) or m.group(2))
    return v is not None and float(v) < 5   # UK 4.5 and under is kids/junior sizing [H]

def check(title: str, extra: str, comp) -> str:
    """Return '' if the comp is a safe match, else a plain-English reason it is not."""
    t, x, m = norm(title), norm(extra), norm(comp.match)
    words = m.split()
    cat = comp.category
    def word_ok(w):
        if cat == "tools" and re.search(r"\d", w):   # model numbers: body-only suffixes N/Z/ZJ/NT only
            return re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(n|z|zj|nt|zk)?(?![a-z0-9])", t) is not None
        return has(t, w)
    if not all(word_ok(w) for w in words):
        return "name differs"
    def guard(words_, label, scope=t):
        hit = [w for w in words_ if has(scope, w) and not has(m, w)]
        return f"{label} ({hit[0]})" if hit else ""
    r = guard(KIDS, "kids' size") if cat in ("trainers", "sportswear") else ""
    if not r and cat in ("trainers", "sportswear"):
        if _kids_size(title): r = "kids' size"
        elif has(x, "younger", "older", "junior", "infant", "kids", "girls", "boys"): r = "kids' size (description)"
    r = r or guard(BUNDLE, "bundle")
    if not r and _multipack(t) and not _multipack(m): r = "multipack"
    r = r or guard(PREORDER, "pre-order") or guard(CONDITION, "used/grey/refurbished")
    if not r and cat == "gaming":
        r = guard(EDITIONS, "different edition") or guard(ACCESSORY, "accessory, not the game") or guard(("console", "oled", "lite"), "console, not the game")
        if not r:
            want = [p for p in PLATFORMS if has(m, p)]
            other = [p for p in PLATFORMS if has(t, p) and p not in want and not any(p in w for w in want)]
            if want and other: r = f"other platform ({other[0]})"
    if not r and cat == "tools":
        r = guard(TOOL_KIT, "kit/batteries, comp is body only") or guard(TOOL_PARTS, "part/accessory, not the tool") \
            or guard(NON_GENUINE, "compatible/non-genuine") or guard(TOOL_EXTRAS, "comes with extras")
        if not r and not has(t, *TOOL_BRANDS): r = "no brand in title (possible clone)"
        if not r and re.search(r"(?<![a-z0-9])dck\d", t) and not re.search(r"dck\d", m): r = "kit/batteries, comp is body only (dck kit)"
    if not r and cat == "fragrance":
        a, b = _ml(t), _ml(m)
        if not a or not b: r = "bottle size (ml) not confirmed"
        elif a != b: r = f"different size ({'/'.join(sorted(a))}ml)"
        r = r or guard(("gift set", "set", "travel", "mini", "refill", "body spray", "deodorant", "aftershave balm"), "set/travel/refill")
    if not r and cat == "lego":
        if not re.search(r"(?<!\d)\d{4,6}(?!\d)", t): r = "no set number"
        elif not has(t, "lego"): r = "not LEGO-branded (compatible/other item)"
        elif len(set(re.findall(r"(?<!\d)\d{5,6}(?!\d)", t)) - set(re.findall(r"\d{5,6}", m))) > 0: r = "more than one set"
    return r

def find(title: str, comps: list, extra: str = ""):
    """Best strict match. Returns (comp, '') or (None, reason-of-closest-rejection)."""
    best, why = None, ""
    for c in comps:
        r = check(title, extra, c)
        if r == "name differs":
            continue
        if r:
            why = why or f"{c.match}: {r}"
            continue
        if best is None or len(c.match) > len(best.match):
            best = c
    return (best, "") if best else (None, why)
