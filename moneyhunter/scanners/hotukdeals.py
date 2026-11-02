"""hotukdeals public RSS scanner (tag feeds + trending/new)."""
import re, urllib.request, xml.etree.ElementTree as ET
from .. import config as C

NS = {"pepper": "http://www.pepper.com/rss", "media": "http://search.yahoo.com/mrss/"}

def _fetch(path: str) -> bytes:
    req = urllib.request.Request(C.HUKD + path, headers={"User-Agent": C.USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def _price(s: str):
    m = re.search(r"£\s?([\d,]+(?:\.\d{1,2})?)", s or "")
    return float(m.group(1).replace(",", "")) if m else None

def classify(title: str, hint: str):
    t = title.lower()
    for cat, kws in C.CATEGORY_KEYWORDS.items():
        if any(k in t for k in kws):
            return cat
    return None if hint == "any" else hint

def delivery_speed(title: str, merchant: str) -> str:
    t = (title + " " + merchant).lower()
    if "in store" in t or "instore" in t: return "In-store only (no car: skip unless walkable)"
    if "c&c" in t or "click & collect" in t or "click and collect" in t: return "Click & collect / delivery option (check)"
    if "amazon" in t: return "Next day likely (Prime) [H]"
    return "Retailer delivery, check ETA"

def dedupe_key(title: str, price: float) -> str:
    t = re.sub(r"[^a-z0-9 ]", " ", title.lower())
    t = re.sub(r"\b(w ?code|with code|free c ?c|sold by.*|fba)\b", " ", t)
    return " ".join(t.split()[:8]) + f"|{price:.2f}"

def scan(log=print) -> list:
    out, seen, keys = [], set(), set()
    for hint, paths in C.FEEDS.items():
        for p in paths:
            try:
                root = ET.fromstring(_fetch(p))
            except Exception as e:
                log(f"[hotukdeals] {p}: {type(e).__name__}")
                continue
            for it in root.iter("item"):
                link = (it.findtext("link") or "").strip()
                if link in seen: continue
                seen.add(link)
                title = (it.findtext("title") or "").strip()
                heat = None
                m = re.match(r"(-?\d+)°\s*-\s*(.*)", title)
                if m: heat, title = int(m.group(1)), m.group(2)
                mer = it.find("pepper:merchant", NS)
                merchant = mer.get("name", "") if mer is not None else ""
                price = _price(mer.get("price", "")) if mer is not None else None
                if price is None: price = _price(it.findtext("description") or "")
                th = it.find("media:thumbnail", NS)
                thumb = th.get("url", "").replace("/re/150x150/", "/re/300x300/") if th is not None else ""
                cat = classify(title, hint)
                if price is None or cat is None: continue
                k = dedupe_key(title, price)
                if k in keys: continue
                keys.add(k)
                out.append({"title": title, "url": link, "price": price, "merchant": merchant,
                            "category": cat, "heat": heat, "thumb": thumb, "feed": p,
                            "delivery": delivery_speed(title, merchant)})
    return out
