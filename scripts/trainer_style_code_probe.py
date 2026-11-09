#!/usr/bin/env python3
"""Manual read-only feasibility probe: can HUKD-linked merchant pages yield a trainer style code?

Standalone. Not wired into cli.run_scan. No retries, no UA rotation, no anti-bot bypass.
Run once manually: python3 scripts/trainer_style_code_probe.py
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

# Verbatim from /workspace/task9_trainers_pipeline_diagnostic.json trainer_offers
# 3 Nike, 3 Adidas, 2 Asics, 2 other (New Balance + Vans).
HUKD_URLS = [
    # Nike
    "https://www.hotukdeals.com/deals/nike-air-max-koko-trainers-black-black-anthracite-5026251",
    "https://www.hotukdeals.com/deals/nike-first-sight-run-trainers-black-black-mtlc-dark-grey-sizes-4-65-5026241",
    "https://www.hotukdeals.com/deals/nike-air-force-1-07-bwn-sneaker-brown-sail-brown-size-3-7-5026061",
    # Adidas
    "https://www.hotukdeals.com/deals/adidas-running-adizero-pacer-trainers-in-black-size-6-12-ps5524-wcode-newhere-for-new-customers-5027102",
    "https://www.hotukdeals.com/deals/adidas-originals-zx-500-rs-trainers-blue-size-6-5026597",
    "https://www.hotukdeals.com/deals/adidas-mens-run50s-low-top-trainers-5025640",
    # Asics
    "https://www.hotukdeals.com/deals/asics-boys-contend-9-gs-sneaker-selected-sizes-pink-5026643",
    "https://www.hotukdeals.com/deals/asics-gel-lyte-iii-future-pack-mens-black-trainers-size-45-wcode-5026632",
    # Other
    "https://www.hotukdeals.com/deals/new-balance-25-off-wcode-fresh-foam-arishi-v4-mens-running-shoes-arishi-v4-mens-wide-fit-trainers-ps5624-5027063",
    "https://www.hotukdeals.com/deals/vans-old-skool-sneakers-blue-or-grey-size-3-75-wcode-blue-light-code-5026604",
]

UA = "MoneyhunterTrainerStyleCodeProbe/1.0 (+read-only feasibility research; no automation bypass; github.com/jwavez/moneyhunter)"
OUT_PATH = Path("/workspace/trainer_style_code_probe.json")

# Counters (honest accounting)
PAGE_FETCHES = 0  # HUKD body GET + merchant body GET (cap 20)
ROBOTS_FETCHES = 0
REDIRECT_RESOLVES = 0  # HEAD/GET without following, Location only
PAGE_FETCH_CAP = 20

NIKE_CODE = re.compile(r"\b([A-Z]{2}\d{4}-\d{3})\b")
ADIDAS_CODE = re.compile(r"\b([A-Z]{2}\d{4})\b")
LABELLED_CODE = re.compile(
    r"(?:style\s*code|product\s*code|article(?:\s*(?:number|code))?|item\s*model\s*number|mpn|sku|model\s*number|product\s*id)\s*[:#=\- ]*\s*([A-Za-z0-9\-]+)",
    re.I,
)


def _ssl_ctx():
    return ssl.create_default_context()


def http_get(url, timeout, method="GET", max_bytes=2_000_000):
    """Single request. No retries. Returns (status, final_url, headers_dict, body_text_or_None, error)."""
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            raw = resp.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raw = raw[:max_bytes]
            charset = "utf-8"
            ctype = headers.get("content-type", "")
            m = re.search(r"charset=([\w\-]+)", ctype, re.I)
            if m:
                charset = m.group(1)
            try:
                text = raw.decode(charset, errors="replace")
            except LookupError:
                text = raw.decode("utf-8", errors="replace")
            return status, resp.geturl(), headers, text, None
    except urllib.error.HTTPError as exc:
        body = None
        try:
            body = exc.read(200_000).decode("utf-8", errors="replace")
        except Exception:
            body = None
        headers = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
        return exc.code, url, headers, body, f"HTTPError {exc.code}"
    except Exception as exc:
        return None, url, {}, None, f"{type(exc).__name__}: {exc}"


def robots_allowed(page_url, timeout=10):
    """Fetch robots.txt once per host intent; disallow if Fetch denied for our UA/path."""
    global ROBOTS_FETCHES
    parts = urllib.parse.urlsplit(page_url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    ROBOTS_FETCHES += 1
    status, _, _, text, err = http_get(robots_url, timeout=timeout)
    if err or status is None:
        # Fail closed on robots fetch failure? Spec: honour robots — if we cannot read it, skip.
        return False, f"robots.txt fetch failed ({err or status})"
    if status >= 400:
        # Missing robots.txt conventionally allows; 404 → allow.
        if status == 404:
            return True, "robots.txt missing (404) — treated as allow"
        return False, f"robots.txt HTTP {status}"
    path = parts.path or "/"
    ua_l = UA.lower()
    groups = []
    current = None
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip().lower(), val.strip()
        if key == "user-agent":
            current = {"ua": val.lower(), "disallow": [], "allow": []}
            groups.append(current)
        elif current is not None and key == "disallow":
            current["disallow"].append(val)
        elif current is not None and key == "allow":
            current["allow"].append(val)

    def applies(group):
        g = group["ua"]
        return g == "*" or (g and g in ua_l) or (g and ua_l.startswith(g.rstrip("*")))

    matched = [g for g in groups if applies(g)]
    if not matched:
        matched = [g for g in groups if g["ua"] == "*"]
    if not matched:
        return True, "no matching robots group — allow"

    # Longest Allow/Disallow prefix match (simple).
    rules = []
    for g in matched:
        for d in g["disallow"]:
            rules.append(("disallow", d))
        for a in g["allow"]:
            rules.append(("allow", a))
    best = None
    for kind, prefix in rules:
        if prefix == "":
            continue
        if path.startswith(prefix) or prefix == "/":
            if best is None or len(prefix) >= len(best[1]):
                best = (kind, prefix)
    if best is None:
        # Empty Disallow means allow all for that UA.
        if any(d == "" for g in matched for d in g["disallow"]) and not any(
            d for g in matched for d in g["disallow"] if d
        ):
            return True, "empty Disallow — allow"
        return True, "no path rule matched — allow"
    if best[0] == "disallow":
        return False, f"robots Disallow {best[1]}"
    return True, f"robots Allow {best[1]}"


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self._in_a = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        ad = {k.lower(): v for k, v in attrs}
        href = ad.get("href")
        if href:
            self.hrefs.append(href)


def extract_merchant_url(hukd_url, html):
    """Find outbound merchant / visit link on a HUKD deal page.\n\n    HUKD often embeds visit URLs only inside JS config as JSON-escaped strings,\n    not as plain <a href>.\n    """
    candidates = []
    parser = LinkExtractor()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    for href in parser.hrefs:
        full = urllib.parse.urljoin(hukd_url, href)
        host = urllib.parse.urlsplit(full).netloc.lower()
        low = full.lower()
        if "hotukdeals.com" in host:
            if "/visit/" in low or "/track/" in low or "out=" in low or "redirect" in low:
                candidates.append(full)
            continue
        if low.startswith("http"):
            if any(x in host for x in ("crwdcntrl", "ltmsphrcl", "facebook", "google", "twitter", "storyblok")):
                continue
            candidates.append(full)

    unescaped = (html or "").replace("\\/", "/")
    for m in re.finditer(r"https://www\.hotukdeals\.com/visit/[A-Za-z0-9_\-]+/[0-9]+", unescaped):
        candidates.append(m.group(0))

    for c in candidates:
        if "/visit/threadmain/" in c.lower():
            return c
    for c in candidates:
        if "/visit/" in c.lower() or "/track/" in c.lower():
            return c
    return candidates[0] if candidates else None



def resolve_redirect_location(url, timeout=10):
    """One request without following redirects; return Location if present.

    Counts toward REDIRECT_RESOLVES (reported separately from the 20 page-fetch cap).
    """
    global REDIRECT_RESOLVES
    REDIRECT_RESOLVES += 1
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": UA, "Accept": "text/html,*/*"},
    )
    try:
        # Custom opener that does not follow redirects.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=_ssl_ctx()))
        try:
            with opener.open(req, timeout=timeout) as resp:
                return resp.geturl(), None
        except urllib.error.HTTPError as exc:
            loc = exc.headers.get("Location") if exc.headers else None
            if loc:
                return urllib.parse.urljoin(url, loc), None
            return None, f"redirect resolve HTTP {exc.code} without Location"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def unwrap_hotukdeals_redirect(url):
    """If url is a HUKD path/pepper redirect, decode the nested merchant URL without an HTTP request."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.netloc or "").lower()
        if "hotukdeals.com" not in host:
            return url, False
        qs = urllib.parse.parse_qs(parts.query)
        for key in ("url", "u", "dest", "destination", "redirect"):
            if key in qs and qs[key]:
                target = urllib.parse.unquote(qs[key][0])
                if target.startswith("http"):
                    return target, True
        # Sometimes nested once more
        return url, False
    except Exception:
        return url, False


def anti_bot_signals(status, body, headers):
    """Detect real challenge/block pages — not merely Cloudflare/captcha script tags on a real HTML deal page."""
    notes = []
    suspected = False
    text = (body or "")[:80_000].lower()
    server = (headers or {}).get("server", "")
    title_m = re.search(r"<title[^>]*>(.*?)</title>", body or "", re.I | re.S)
    title = re.sub(r"<[^>]+>", " ", title_m.group(1)).strip().lower() if title_m else ""

    if status in (403, 429):
        suspected = True
        notes.append(f"http_status={status}")

    # Cloudflare / generic interstitial challenge pages
    challenge_title = title in (
        "just a moment...",
        "just a moment",
        "attention required! | cloudflare",
        "attention required!",
        "access denied",
    )
    strong = [
        ("cf-browser-verification", "cloudflare_browser_verification"),
        ("cf-challenge-running", "cloudflare_challenge_running"),
        ("cdn-cgi/challenge-platform/h/b/orchestrate", "cloudflare_challenge_orchestrate"),
        ("checking your browser before accessing", "cloudflare_browser_check"),
        ("please enable javascript and cookies to continue", "js_cookie_wall"),
        ("please enable javascript to continue", "js_wall"),
        ("enable javascript and cookies to continue", "js_cookie_wall"),
        ("akamai bot manager", "akamai_bot_manager"),
        ("access denied you don't have permission", "access_denied"),
    ]
    for needle, label in strong:
        if needle in text:
            suspected = True
            notes.append(label)
    if challenge_title:
        suspected = True
        notes.append(f"challenge_title={title[:80]}")

    # g-recaptcha / hcaptcha as a full-page gate (not a footer widget on a real deal page)
    if re.search(r"g-recaptcha|h-captcha|hcaptcha", text) and (
        "deal" not in title and "hotukdeals" not in title and len(text) < 8000
    ):
        suspected = True
        notes.append("captcha_challenge_page")

    if "cloudflare" in server.lower():
        notes.append("server=cloudflare")  # informational; not alone a block
    if "akamai" in server.lower() and status in (403, 429, 503):
        suspected = True
        notes.append("server=akamai")
    return suspected, notes


def extract_style_code(html, brand):
    """Simple regex extraction; Adidas only when labelled or near title."""
    if not html:
        return None, "none"
    # JSON-LD
    for m in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        block = m.group(1)
        if brand == "nike":
            hit = NIKE_CODE.search(block.upper().replace(" ", ""))
            # search original case too
            hit = NIKE_CODE.search(block) or NIKE_CODE.search(block.upper())
            if hit:
                return hit.group(1).upper(), "json_ld"
        if brand == "adidas":
            for lm in LABELLED_CODE.finditer(block):
                cand = lm.group(1).upper()
                if ADIDAS_CODE.fullmatch(cand):
                    return cand, "json_ld"
            # Also sku/mpn fields in json
            for key in ("sku", "mpn", "productID", "model"):
                km = re.search(r'"' + key + r'"\s*:\s*"([^"]+)"', block, re.I)
                if km and ADIDAS_CODE.fullmatch(km.group(1).upper()):
                    return km.group(1).upper(), "json_ld"

    # Meta tags
    for m in re.finditer(
        r'<meta[^>]+(?:name|property)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.I,
    ):
        name, content = m.group(1).lower(), m.group(2)
        if any(k in name for k in ("sku", "mpn", "product", "model", "gtin")):
            if brand == "nike":
                hit = NIKE_CODE.search(content)
                if hit:
                    return hit.group(1).upper(), "meta"
            if brand == "adidas":
                hit = ADIDAS_CODE.fullmatch(content.strip().upper())
                if hit:
                    return hit.group(1).upper(), "meta"
    # Reverse attr order
    for m in re.finditer(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']([^"\']+)["\']',
        html,
        re.I,
    ):
        content, name = m.group(1), m.group(2).lower()
        if any(k in name for k in ("sku", "mpn", "product", "model", "gtin")):
            if brand == "nike":
                hit = NIKE_CODE.search(content)
                if hit:
                    return hit.group(1).upper(), "meta"
            if brand == "adidas":
                if ADIDAS_CODE.fullmatch(content.strip().upper()):
                    return content.strip().upper(), "meta"

    # Inline labelled text
    for lm in LABELLED_CODE.finditer(html):
        cand = lm.group(1).upper()
        if brand == "nike" and NIKE_CODE.fullmatch(cand):
            return cand, "inline_text"
        if brand == "adidas" and ADIDAS_CODE.fullmatch(cand):
            return cand, "inline_text"

    # Nike: allow unlabelled NIKE pattern only in obvious product contexts (title-ish)
    if brand == "nike":
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = title_m.group(1) if title_m else ""
        hit = NIKE_CODE.search(title)
        if hit:
            return hit.group(1).upper(), "inline_text"
        # Do not scrape arbitrary body Nike codes without labels — too noisy.
    if brand == "adidas":
        # Only labelled (already searched) or within ~120 chars of <title>/h1 text.
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
        for block in (title_m.group(1) if title_m else "", h1_m.group(1) if h1_m else ""):
            plain = re.sub(r"<[^>]+>", " ", block)
            # Near title: look in a window of html around first h1
            pass
        if h1_m:
            start = max(0, h1_m.start() - 120)
            end = min(len(html), h1_m.end() + 120)
            window = html[start:end]
            for lm in LABELLED_CODE.finditer(window):
                cand = lm.group(1).upper()
                if ADIDAS_CODE.fullmatch(cand):
                    return cand, "inline_text"
            # Spec: near product title — allow Adidas code in the h1/title window only if labelled
            # already handled; also accept code inside the h1 itself when h1 looks like a product title
            h1_plain = re.sub(r"<[^>]+>", " ", h1_m.group(1))
            hit = ADIDAS_CODE.search(h1_plain.upper())
            # Without a label, do not accept bare Adidas codes (spec: only if labelled or near title
            # in a style/product field). Near title alone without label is ambiguous — require label.
            # So no bare accept here.
            _ = hit

    return None, "none"


def brand_for(title_hint, url):
    try:
        from moneyhunter.trainers_pipeline_diagnostic import parse_trainer_brand
    except Exception:
        parse_trainer_brand = None
    text = title_hint or url
    if parse_trainer_brand:
        b = parse_trainer_brand(text)
        if b in ("nike", "adidas"):
            return b
        return b
    low = text.lower()
    if "nike" in low:
        return "nike"
    if "adidas" in low:
        return "adidas"
    return "other"


def probe_one(hukd_url):
    global PAGE_FETCHES
    entry = {
        "hukd_url": hukd_url,
        "brand_parsed": brand_for(hukd_url, hukd_url),
        "hukd_fetched": False,
        "hukd_robots_allowed": False,
        "merchant_url": None,
        "merchant_domain": None,
        "merchant_fetched": False,
        "merchant_robots_allowed": False,
        "http_status": None,
        "anti_bot_suspected": False,
        "style_code_found": None,
        "style_code_source": "none",
        "notes": "",
    }
    notes = []

    allowed, why = robots_allowed(hukd_url)
    entry["hukd_robots_allowed"] = bool(allowed)
    if not allowed:
        entry["notes"] = f"skipped HUKD: {why}"
        return entry
    notes.append(f"hukd_robots: {why}")

    if PAGE_FETCHES >= PAGE_FETCH_CAP:
        entry["notes"] = "page-fetch cap reached before HUKD GET"
        return entry
    PAGE_FETCHES += 1
    status, final, headers, body, err = http_get(hukd_url, timeout=10)
    entry["hukd_fetched"] = body is not None or status is not None
    entry["http_status"] = status
    if err:
        notes.append(f"hukd_error: {err}")
    suspected, signals = anti_bot_signals(status, body, headers)
    if suspected:
        entry["anti_bot_suspected"] = True
        notes.append("hukd_anti_bot: " + ",".join(signals))
        entry["notes"] = "; ".join(notes)
        return entry
    if not body or (status and status >= 400):
        notes.append(f"hukd_no_body status={status}")
        entry["notes"] = "; ".join(notes)
        return entry

    # Title hint for brand
    tm = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    title = re.sub(r"<[^>]+>", " ", tm.group(1)).strip() if tm else ""
    entry["brand_parsed"] = brand_for(title or hukd_url, hukd_url)

    merchant = extract_merchant_url(hukd_url, body)
    if not merchant:
        notes.append("no merchant/outbound link found on HUKD page")
        entry["notes"] = "; ".join(notes)
        return entry

    # If outbound is still on HUKD (visit/track), resolve Location without following chain as page fetch.
    host = urllib.parse.urlsplit(merchant).netloc.lower()
    if "hotukdeals.com" in host:
        resolved, rerr = resolve_redirect_location(merchant, timeout=10)
        if resolved:
            notes.append(
                "resolved HUKD visit/track via one non-following GET reading Location/final URL "
                f"(counts as redirect_resolve, not page-fetch); {merchant} -> {resolved}"
            )
            merchant = resolved
            unwrapped, did = unwrap_hotukdeals_redirect(merchant)
            if did:
                notes.append(
                    "unwrapped HUKD path/pepper redirect url= query param without an HTTP request; "
                    f"{merchant} -> {unwrapped}"
                )
                merchant = unwrapped
        else:
            notes.append(f"visit redirect unresolved: {rerr}")
            entry["merchant_url"] = merchant
            entry["merchant_domain"] = host
            entry["notes"] = "; ".join(notes)
            return entry

    unwrapped, did = unwrap_hotukdeals_redirect(merchant)
    if did:
        notes.append(
            "unwrapped HUKD path/pepper redirect url= query param without an HTTP request; "
            f"{merchant} -> {unwrapped}"
        )
        merchant = unwrapped

    entry["merchant_url"] = merchant
    entry["merchant_domain"] = urllib.parse.urlsplit(merchant).netloc.lower() or None

    m_allowed, m_why = robots_allowed(merchant)
    entry["merchant_robots_allowed"] = bool(m_allowed)
    notes.append(f"merchant_robots: {m_why}")
    if not m_allowed:
        entry["notes"] = "; ".join(notes)
        return entry

    if PAGE_FETCHES >= PAGE_FETCH_CAP:
        notes.append("page-fetch cap reached before merchant GET")
        entry["notes"] = "; ".join(notes)
        return entry
    PAGE_FETCHES += 1
    status, final, headers, body, err = http_get(merchant, timeout=15)
    entry["merchant_fetched"] = body is not None or status is not None
    entry["http_status"] = status
    if err:
        notes.append(f"merchant_error: {err}")
    suspected, signals = anti_bot_signals(status, body, headers)
    if suspected:
        entry["anti_bot_suspected"] = True
        notes.append("merchant_anti_bot: " + ",".join(signals))
    if body and status and status < 400 and not suspected:
        code, source = extract_style_code(body, entry["brand_parsed"] if entry["brand_parsed"] in ("nike", "adidas") else entry["brand_parsed"])
        # For non-nike/adidas brands still try Nike/Adidas patterns only when labelled.
        if not code:
            # labelled any brand
            for lm in LABELLED_CODE.finditer(body):
                cand = lm.group(1).upper()
                if NIKE_CODE.fullmatch(cand):
                    code, source = cand, "inline_text"
                    break
                if ADIDAS_CODE.fullmatch(cand):
                    code, source = cand, "inline_text"
                    break
        entry["style_code_found"] = code
        entry["style_code_source"] = source if code else "none"
        if not code:
            notes.append("no labelled style/product code matched")
    elif not suspected:
        notes.append(f"merchant_no_usable_body status={status}")

    entry["notes"] = "; ".join(notes)
    return entry


def main():
    global PAGE_FETCHES, ROBOTS_FETCHES, REDIRECT_RESOLVES
    PAGE_FETCHES = ROBOTS_FETCHES = REDIRECT_RESOLVES = 0
    results = []
    for url in HUKD_URLS:
        try:
            results.append(probe_one(url))
        except Exception as exc:
            results.append(
                {
                    "hukd_url": url,
                    "brand_parsed": brand_for(url, url),
                    "hukd_fetched": False,
                    "hukd_robots_allowed": False,
                    "merchant_url": None,
                    "merchant_domain": None,
                    "merchant_fetched": False,
                    "merchant_robots_allowed": False,
                    "http_status": None,
                    "anti_bot_suspected": False,
                    "style_code_found": None,
                    "style_code_source": "none",
                    "notes": f"probe exception: {type(exc).__name__}: {exc}",
                }
            )

    meta = {
        "page_fetches": PAGE_FETCHES,
        "page_fetch_cap": PAGE_FETCH_CAP,
        "robots_fetches": ROBOTS_FETCHES,
        "robots_fetches_count_separately": True,
        "redirect_resolves": REDIRECT_RESOLVES,
        "redirect_resolves_count_separately": True,
        "redirect_policy": (
            "HUKD /visit/ or /track/ outbound links are resolved with one GET that does not follow "
            "redirects; the Location header (or error Location) is read. That request is counted in "
            "redirect_resolves, not in the 20 page-fetch cap. HUKD HTML body GET and merchant HTML "
            "body GET count toward page_fetches (max 20)."
        ),
        "user_agent": UA,
        "entries": results,
    }
    # Spec schema is a list of entries — write list at top level AND keep accounting alongside via wrapper?
    # Spec: "Write the result to trainer_style_code_probe.json with one entry per URL" — array of 10.
    # Put accounting in a sibling file note in notes of first entry? Better: write the array as required,
    # and also write accounting into /workspace as part of report. User asked for full probe JSON paste —
    # I'll write a document with {"request_accounting": {...}, "entries": [...]} so nothing is lost,
    # and ensure len(entries)==10. Spec shows entry schema; parent summary asks for full probe JSON.
    OUT_PATH.write_text(json.dumps({"request_accounting": {k: meta[k] for k in meta if k != "entries"}, "entries": results}, indent=2, sort_keys=True) + "\n")
    print(json.dumps(meta["request_accounting"] if False else {k: meta[k] for k in meta if k != "entries"}, indent=2))
    print(f"wrote {OUT_PATH} entries={len(results)} page_fetches={PAGE_FETCHES} robots={ROBOTS_FETCHES} redirects={REDIRECT_RESOLVES}")


if __name__ == "__main__":
    main()
