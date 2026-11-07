"""hotukdeals public RSS scanner (tag feeds + trending/new)."""
import re, urllib.request, xml.etree.ElementTree as ET
import datetime as dt
from email.utils import parsedate_to_datetime
from .. import config as C

NS = {"pepper": "http://www.pepper.com/rss", "media": "http://search.yahoo.com/mrss/"}

def _fetch(path: str) -> bytes:
    req = urllib.request.Request(C.HUKD + path, headers={"User-Agent": C.USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def _price(s: str):
    # Independently implemented ambiguity rule inspired by changedetection.io;
    # see docs/OPEN_SOURCE_RESEARCH.md. Never mistake a "was" price for today's offer.
    import html
    text = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    amounts = {float(v.replace(",", "")) for v in re.findall(r"£\s*([\d,]+(?:\.\d{1,2})?)(?![\d.])", text)}
    return amounts.pop() if len(amounts) == 1 else None

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
    import hashlib
    return hashlib.sha256(" ".join(t.split()).encode()).hexdigest()[:24] + f"|{price:.2f}"

LAST_DIAGNOSTICS = {}
_STATUS = {}
CHECK_BUDGET = 24  # shared graded/WATCH/trending page-check budget per scan

def online_status(title, description=""):
    t = (title + " " + description).lower()
    if re.search(r"in.?store only|instore|in store|collection only|c&c only|click (?:&|and) collect only|limited stores|local only|pre.?order|coming soon|out of stock|sold out|tester", t):
        return False
    return True

def delivery_cost(title, description=""):
    t = (title + " " + description).lower()
    # Explicit delivery only, never assume Prime/membership or a basket threshold is met.
    if re.search(r"free (?:delivery|shipping|postage)|(?:delivery|shipping|postage) free", t) and not re.search(r"(?:over|spend|prime|members|minimum|orders of)", t):
        return 0.0
    m = re.search(r"(?:delivery|shipping|postage)[: ]+£\s?(\d+(?:\.\d{1,2})?)|£\s?(\d+(?:\.\d{1,2})?)\s+(?:delivery|shipping|postage)", t)
    return float(m[1] or m[2]) if m else None

def scan(log=print) -> list:
    global LAST_DIAGNOSTICS
    _STATUS.clear()
    LAST_DIAGNOSTICS = {"feeds_ok": 0, "feeds_failed": 0, "feed_items": 0, "duplicates": 0, "old_dropped": 0, "age_unknown": 0, "missing_price_or_category": 0, "ambiguous_price": 0}
    out, seen, keys, by_link = [], set(), set(), {}
    for hint, paths in C.FEEDS.items():
        for p in paths:
            try:
                root = ET.fromstring(_fetch(p))
            except Exception as e:
                log(f"[hotukdeals] {p}: {type(e).__name__}")
                LAST_DIAGNOSTICS["feeds_failed"] += 1
                continue
            LAST_DIAGNOSTICS["feeds_ok"] += 1
            for it in root.iter("item"):
                LAST_DIAGNOSTICS["feed_items"] += 1
                link = (it.findtext("link") or "").strip()
                if link in seen:
                    LAST_DIAGNOSTICS["duplicates"] += 1
                    m0 = re.match(r"(-?\d+)°", (it.findtext("title") or "").strip())
                    if m0 and link in by_link: by_link[link]["heat"] = int(m0.group(1))   # heat only shows in trending
                    continue
                seen.add(link)
                title = (it.findtext("title") or "").strip()
                heat = None
                m = re.match(r"(-?\d+)°\s*-\s*(.*)", title)
                if m: heat, title = int(m.group(1)), m.group(2)
                mer = it.find("pepper:merchant", NS)
                merchant = mer.get("name", "") if mer is not None else ""
                price = _price(mer.get("price", "")) if mer is not None else None
                desc_html = it.findtext("description") or ""
                if price is None:
                    price = _price(desc_html)
                    if price is None and len(set(re.findall(r"£\s*([\d,]+(?:\.\d{1,2})?)", desc_html))) > 1:
                        LAST_DIAGNOSTICS["ambiguous_price"] += 1
                # Retain direct item links solely for acquisition exclusion; never follow redirects.
                acquisition_urls = []
                for u in re.findall(r'https://[^\s<>"\x27]+', desc_html):
                    direct = u.replace("&amp;", "&")
                    if re.match(r"https://(?:www\.)?ebay\.(?:co\.uk|com)/itm/", direct):
                        acquisition_urls.append(direct.split("?")[0].split("#")[0])
                desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", desc_html)).strip()[:800]
                from .. import images
                thumb = images.feed(it,NS)
                cat = classify(title, hint)
                if cat is None and heat is not None: cat = "other"   # keep trending items for #trending / #price-errors
                if price is None or cat is None:
                    LAST_DIAGNOSTICS["missing_price_or_category"] += 1
                    continue
                k = dedupe_key(title, price)
                if k in keys:
                    LAST_DIAGNOSTICS["duplicates"] += 1
                    continue
                pub = (it.findtext("pubDate") or "").strip()
                try:
                    age = (dt.datetime.now(dt.timezone.utc) - parsedate_to_datetime(pub).astimezone(dt.timezone.utc)).total_seconds() / 86400
                    if age > C.MAX_FEED_AGE_DAYS or age < -1:
                        LAST_DIAGNOSTICS["old_dropped"] += 1
                        continue
                except (TypeError, ValueError, OverflowError):
                    LAST_DIAGNOSTICS["age_unknown"] += 1
                keys.add(k)
                by_link[link] = {}; out.append(by_link[link])
                by_link[link].update({"title": title, "url": link, "price": price, "merchant": merchant,
                            "category": cat, "acquisition_urls": sorted(set(acquisition_urls)), "heat": heat, "thumb": thumb, "feed": p,
                            "delivery": delivery_speed(title, merchant), "desc": desc,
                            "inbound_delivery": delivery_cost(title, desc), "online_eligible": online_status(title, desc),
                            "pub": (it.findtext("pubDate") or "").strip()})
    return out

def live_status(url: str) -> str:
    """Three-state expiry check. Errors/unrecognised pages never count as live."""
    if url in _STATUS: return _STATUS[url]
    if len(_STATUS) >= CHECK_BUDGET: return "unknown"
    LAST_DIAGNOSTICS["page_requests"] = LAST_DIAGNOSTICS.get("page_requests", 0) + 1
    try:
        req = urllib.request.Request(url, headers={"User-Agent": C.USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read(400000).decode("utf-8", "replace")
        if re.search(r'"isExpired"\s*:\s*true', html): status = "expired"
        elif re.search(r'"isExpired"\s*:\s*false', html): status = "live"
        else: status = "unknown"
    except Exception:
        status = "unknown"
    _STATUS[url] = status
    return status

def is_live(url: str) -> bool:
    return live_status(url) == "live"
