"""One-off dry run: live eBay active comps for a few stored comps. Logs matched/rejected titles. No Discord."""
import sys
from moneyhunter import comps as CP, matching as M
from moneyhunter.scanners import ebay
names = sys.argv[1:] or ["samba og", "76449", "dcd796"]
cs = {c.match: c for c in CP.load()}
for n in names:
    c = cs[n]; items = ebay.search_new_gb(c.match)
    print(f"\n=== {n} ({c.category}) stored £{c.low}-£{c.high}, {len(items)} listings ===")
    for it in sorted(items, key=lambda i: i["price"]):
        r = M.check(it["title"], "", c)
        print(f"  {'OK ' if not r else 'REJ'} £{it['price']:8.2f}  {it['title'][:90]}  {('['+r+']') if r else ''}")
    lc = ebay.active_comp(c, items, M.check)
    print(f"  -> live comp: {'none (too few)' if not lc else f'£{lc.low}-£{lc.high} | {lc.evidence}'}")
