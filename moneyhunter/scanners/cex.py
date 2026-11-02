"""CeX floor-price lookup. CeX's public JSON endpoint returned HTTP 403 from this
machine on 2 Nov 2026, so automatic lookup is disabled; enter the CeX cash price
by hand in data/comps.csv (floor column) after checking uk.webuy.com."""
import urllib.request

def available() -> bool:
    try:
        req = urllib.request.Request("https://wss2.cex.uk.webuy.io/v3/boxes?q=switch&firstRecord=1&count=1",
                                     headers={"User-Agent": "Mozilla/5.0"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False
