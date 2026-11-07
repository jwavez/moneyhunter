"""Read the existing Worker's public RSS research buffer, never sold evidence."""
import datetime as dt
import json
import math
import os
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from . import hotukdeals
from ..images import safe

URL = "https://moneyhunter-bot.moneyhunter.workers.dev/api/research-capture"
LAST_DIAGNOSTICS = {}


def scan(log=print, when=None):
    global LAST_DIAGNOSTICS
    when = when or dt.datetime.now(dt.timezone.utc)
    endpoint = os.getenv("MONEYHUNTER_CAPTURE_URL")
    LAST_DIAGNOSTICS = {"enabled": bool(endpoint), "added": 0, "duplicates": 0, "invalid": 0,
                        "status": "not_configured", "grades_computed": False}
    if not endpoint: return []
    if endpoint != URL: raise ValueError("capture endpoint is not the approved public Worker URL")
    try:
        with urlopen(Request(endpoint, headers={"User-Agent": "moneyhunter/0.1"}), timeout=12) as r:
            payload = json.loads(r.read(600000))
        if payload.get("schema_version") != 1 or payload.get("kind") != "feed_capture_only" or not isinstance(payload.get("items"), list):
            raise ValueError("invalid public capture schema")
        LAST_DIAGNOSTICS.update(status=payload.get("status", "unknown"), last_attempt=payload.get("last_attempt"), last_success=payload.get("last_success"))
        out = []
        for x in payload["items"][:300]:
            from .. import product_format as PF
            if PF.reason(x):continue
            x=PF.normalize(x)
            try:
                u = urlsplit(x["url"])
                pub = dt.datetime.fromisoformat(x["published_at"].replace("Z", "+00:00"))
                seen = dt.datetime.fromisoformat(x["last_seen"].replace("Z", "+00:00"))
                price = float(x["price"])
                if (u.scheme != "https" or u.hostname != "www.hotukdeals.com" or u.username or u.password or u.query or u.fragment or not u.path.startswith("/deals/")
                        or not isinstance(x["title"], str) or not x["title"] or len(x["title"]) > 200
                        or x.get("kind") != "feed_offer_only" or x["category"] not in ("lego", "gaming")
                        or not math.isfinite(price) or not 0 < price <= 60
                        or not -86400 <= (when-pub).total_seconds() <= 7*86400 or not 0 <= (when-seen).total_seconds() <= 7*86400
                        or not hotukdeals.online_status(x["title"])):
                    raise ValueError("invalid or stale captured offer")
                out.append({"title": x["title"], "url": x["url"], "price": price, "category": x["category"],
                    "merchant": str(x.get("merchant", ""))[:80], "delivery": "Captured RSS; delivery/current stock unverified",
                    "inbound_delivery": None, "online_eligible": True, "desc": "", "heat": None,
                    "thumb":safe(x.get("thumb","")),"pub": pub.isoformat(), "capture_first_seen": x.get("first_seen"), "capture_last_seen": seen.isoformat()})
            except (KeyError, ValueError, TypeError, OverflowError): LAST_DIAGNOSTICS["invalid"] += 1
        return out
    except Exception as exc:
        LAST_DIAGNOSTICS["status"] = "failed"
        log(f"[capture] Public research buffer unavailable: {type(exc).__name__}")
        return []


def merge(current, captured):
    """Current direct RSS wins a price conflict. Buffer cannot overwrite a fresh offer."""
    urls = {r["url"] for r in current}
    keys = {hotukdeals.dedupe_key(r["title"], r["price"]) for r in current}
    out = list(current)
    for r in captured:
        key = hotukdeals.dedupe_key(r["title"], r["price"])
        if r["url"] in urls or key in keys:
            LAST_DIAGNOSTICS["duplicates"] = LAST_DIAGNOSTICS.get("duplicates", 0) + 1
            continue
        urls.add(r["url"]); keys.add(key); out.append(r)
        LAST_DIAGNOSTICS["added"] = LAST_DIAGNOSTICS.get("added", 0) + 1
    return out
