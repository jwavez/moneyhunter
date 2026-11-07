"""Validated, review-only sold observations. No scraping, network calls or invented sales.
Prices must be GBP seller-receivable item+postage (excluding buyer-only fees).
Public store: never include buyer/seller contact details, tokens or private financial data.
"""
import datetime as dt
import json
import math
import os
import re
import statistics
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from . import config as C

IDENTITY = {"gaming": ("platform", "edition", "format"),
            "trainers": ("sku", "size", "gender"), "sportswear": ("sku", "size", "gender"),
            "fragrance": ("concentration", "ml"), "lego": ("set_number",),
            "tools": ("model", "contents"), "tech": ("model", "capacity")}
BASE_IDENTITY = ("condition", "variant")

def number(v, name, zero=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or (not zero and v == 0):
        raise ValueError(f"{name}: finite {'nonnegative' if zero else 'positive'} number required")
    return float(v)

def date(v, today):
    try: d = dt.date.fromisoformat(v)
    except (TypeError, ValueError): raise ValueError("ISO date required") from None
    if d > today: raise ValueError("future evidence date")
    return d

def public_url(v):
    if not isinstance(v, str): raise ValueError("public HTTPS source URL required")
    u = urlsplit(v)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.fragment:
        raise ValueError("public HTTPS URL without credentials/fragment required")
    if u.query:
        allowed = {"_nkw", "LH_Sold", "LH_Complete", "LH_PrefLoc", "_sop", "_sacat", "id", "search", "q", "sku"}
        if set(parse_qs(u.query, keep_blank_values=True)) - allowed:
            raise ValueError("only public search/product URL parameters allowed; no tokens")
    if u.hostname in ("localhost", "127.0.0.1", "::1") or not re.search(r"[a-z]", u.hostname):
        raise ValueError("public source host required")
    return v

def _keys(obj, allowed):
    if not isinstance(obj, dict) or set(obj) - set(allowed):
        raise ValueError("unknown fields: use documented public evidence schema only")

def validate(record, today=None):
    today = today or dt.date.today()
    _keys(record, ("id", "match", "category", "identity", "reviewed", "reviewed_at", "observations", "velocity", "floor", "offers"))
    if record.get("reviewed") is not True: raise ValueError("human review attestation required")
    date(record.get("reviewed_at"), today)
    if not re.fullmatch(r"[a-z0-9_-]{1,80}", record.get("id", "")): raise ValueError("invalid public record id")
    cat = record.get("category")
    if cat not in IDENTITY: raise ValueError("unsupported category")
    match = record.get("match")
    if not isinstance(match, str) or not 3 <= len(match) <= 160: raise ValueError("specific match required")
    identity = record.get("identity", {})
    _keys(identity, (*BASE_IDENTITY, *IDENTITY[cat]))
    if not all(isinstance(identity.get(k), str) and 0 < len(identity[k]) <= 100 for k in (*BASE_IDENTITY, *IDENTITY[cat])):
        raise ValueError("complete exact variant identity required")
    if identity["condition"] not in ("new", "used", "refurbished"): raise ValueError("invalid condition")
    obs = record.get("observations")
    if not isinstance(obs, list) or not 1 <= len(obs) <= 1000: raise ValueError("1-1000 actual sold observations required")
    urls = set()
    for o in obs:
        _keys(o, ("url", "sold_at", "listed_at", "price", "currency", "kind", "identity"))
        url = public_url(o.get("url"))
        if url in urls: raise ValueError("duplicate sold observation URL")
        urls.add(url)
        sold = date(o.get("sold_at"), today)
        if o.get("listed_at") and date(o["listed_at"], today) > sold: raise ValueError("listing starts after sale")
        number(o.get("price"), "sold price")
        if o.get("currency") != "GBP" or o.get("kind") != "sold" or o.get("identity") != identity:
            raise ValueError("only actual GBP sold observations of this exact identity accepted")
    vel = record.get("velocity")
    if vel:
        _keys(vel, ("observed_at", "active", "url"))
        date(vel.get("observed_at"), today); public_url(vel.get("url"))
        if type(vel.get("active")) is not int or vel["active"] < 0: raise ValueError("actual active listing count required")
    floor = record.get("floor")
    if floor:
        _keys(floor, ("amount", "exit_cost", "currency", "kind", "observed_at", "url", "identity"))
        number(floor.get("amount"), "floor"); number(floor.get("exit_cost"), "floor exit cost", True)
        date(floor.get("observed_at"), today); public_url(floor.get("url"))
        if floor.get("kind") != "cash" or floor.get("currency") != "GBP" or floor.get("identity") != identity:
            raise ValueError("floor must be cash, GBP and exact identity; never voucher value")
    for offer in record.get("offers", []):
        _keys(offer, ("url", "source_url", "observed_at", "price", "delivery", "online", "in_stock", "identity"))
        public_url(offer.get("url")); public_url(offer.get("source_url")); date(offer.get("observed_at"), today)
        number(offer.get("price"), "offer price"); number(offer.get("delivery"), "delivery", True)
        if offer.get("online") is not True or offer.get("in_stock") is not True or offer.get("identity") != identity:
            raise ValueError("offer must be exact variant, online and in stock")
    return record

def read_records(path):
    if not Path(path).exists(): return []
    with open(path) as f: doc = json.load(f)
    _keys(doc, ("schema_version", "records"))
    if type(doc.get("schema_version")) is not int or doc["schema_version"] != 1 or not isinstance(doc.get("records"), list):
        raise ValueError("unsupported evidence schema")
    records = [validate(r) for r in doc["records"]]
    if len({r["id"] for r in records}) != len(records): raise ValueError("duplicate evidence record id")
    sold_urls = [o["url"] for r in records for o in r["observations"]]
    if len(set(sold_urls)) != len(sold_urls): raise ValueError("sold observation reused across records")
    return records

def atomic_write(path, doc):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".evidence-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f: json.dump(doc, f, indent=2, allow_nan=False); f.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def ingest(incoming, store):
    # Validate every record before touching destination; update by reviewed record id.
    additions = read_records(incoming)
    merged = {r["id"]: r for r in read_records(store)}
    merged.update({r["id"]: r for r in additions})
    records = sorted(merged.values(), key=lambda r: r["id"])
    urls = [o["url"] for r in records for o in r["observations"]]
    if len(set(urls)) != len(urls): raise ValueError("sold observation reused across records")
    atomic_write(store, {"schema_version": 1, "records": records})
    return len(additions)

def load(path, today=None):
    from .comps import Comp
    today = today or dt.date.today()
    out = []
    for r in read_records(path):
        observations = [o for o in r["observations"] if 0 <= (today - date(o["sold_at"], today)).days <= C.MAX_COMP_AGE_DAYS]
        if not observations: continue
        prices = sorted(o["price"] for o in observations)
        # Lower quartile of exact-condition realised sales; no mixed boxed/sealed ranges.
        low = prices[int((len(prices)-1)*0.25)]; high = statistics.median(prices)
        # Conservative age: every observation supporting this valuation must still be fresh.
        sold_at = min(date(o["sold_at"], today) for o in observations)
        vel, floor = r.get("velocity"), r.get("floor")
        velocity_at = date(vel["observed_at"], today) if vel else None
        sold_in_window = [o for o in r["observations"] if 0 <= (today-date(o["sold_at"], today)).days <= 90]
        # Sample turnover, not extrapolated marketplace-wide sales. All samples need listing dates.
        days = [(date(o["sold_at"], today) - date(o["listed_at"], today)).days for o in observations if o.get("listed_at")]
        dts = statistics.median(days) if len(days) == len(observations) and len(days) >= C.MIN_COMPS else None
        snapshot_sales = [o for o in sold_in_window if 0 <= (velocity_at-date(o["sold_at"], today)).days <= 90] if vel else []
        st = (len(snapshot_sales) / max(1, vel["active"]) * 100) if vel else None
        out.append(Comp(r["match"].lower(), r["category"], low, high,
            f"{len(observations)} reviewed exact-variant GBP sold observations", "reviewed evidence " + r["id"],
            max(0, floor["amount"] - floor["exit_cost"]) if floor else None, floor["url"] if floor else "",
            len(observations), st, dts, sold_at, "sold", r["identity"],
            date(floor["observed_at"], today) if floor else None, velocity_at,
            [o["url"] for o in observations], r.get("offers", [])))
    return out
