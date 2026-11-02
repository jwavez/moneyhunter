"""PriceCharting public game pages (prices compiled from completed sales, mostly eBay).
Reads the public HTML page politely (1 req / 2 s, robots.txt allows /game/). USD shown on page
is converted with the GBP rate PriceCharting publishes on the same page."""
import re, time, urllib.request, datetime as dt
from .. import config as C

def fetch(slug: str) -> dict:
    url = "https://www.pricecharting.com/game/" + slug
    req = urllib.request.Request(url, headers={"User-Agent": C.USER_AGENT})
    s = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
    rate = float(re.search(r'GBP":([0-9.]+)', s).group(1))
    def price(i):
        m = re.search(rf'id="{i}_price">\s*<span class="price js-price">\s*\$([0-9,.]+)', s)
        return round(float(m.group(1).replace(",", "")) * rate, 2) if m else None
    vols = re.findall(r'volume:&nbsp;\s*(?:<[^>]+>\s*)*([0-9,]+) sales? per (day|week|month|year)', s)
    per = {"day": 90, "week": 90 / 7, "month": 3, "year": 90 / 365}
    v90 = [round(int(n.replace(",", "")) * per[u]) for n, u in vols]
    return {"url": url, "rate": rate, "cib": price("complete"), "new": price("new"), "loose": price("used"),
            "vol90_cib": v90[1] if len(v90) > 1 else None, "vol90_new": v90[2] if len(v90) > 2 else None,
            "date": dt.date.today().isoformat()}
