"""Discord webhook poster. Reads MONEYHUNTER_DISCORD_WEBHOOK; never prints it.
If unset or dry_run=True, prints the embed JSON instead."""
import json, os, time, urllib.request, urllib.error

ENV = "MONEYHUNTER_DISCORD_WEBHOOK"
COLORS = {"A": 0x2ECC71, "B": 0xF1C40F, "R": 0xE74C3C, "T": 0x3498DB}

def post(embeds: list, content: str = "", dry_run: bool = False, components: list = None, url: str = None) -> int:
    url = url or os.getenv(ENV)
    payload=build_payload(embeds,content,components)
    if payload is None:
        print("[discord] HOLD: supported price or required image missing/invalid; no message sent")
        return 0
    if components:url=url and url+("&" if "?" in url else "?")+"with_components=true"
    if dry_run or os.getenv("MONEYHUNTER_DISABLE_SEND") == "1" or not url:
        print(f"[discord] DRY RUN ({'no webhook set' if not url else 'dry-run flag'}): {len(embeds)} embed(s)")
        print(json.dumps(payload, indent=2, ensure_ascii=False)[:4000])
        return 0
    data = json.dumps(payload).encode()
    for _ in range(3):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "moneyhunter/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status
        except urllib.error.HTTPError as e:
            if e.code == 429:   # Discord rate limit: 30 msgs/min per webhook [S]
                time.sleep(float(json.loads(e.read() or b"{}").get("retry_after", 2)))
                continue
            print(f"[discord] HTTP {e.code}")
            return e.code
        except (urllib.error.URLError, TimeoutError, OSError):
            print("[discord] Delivery failed (network/timeout); will retry on a future scan")
            return 0
    return 429


def build_payload(embeds,content="",components=None):
    """The single final serializer used by real sends AND no-send acceptance exports."""
    from .images import publishable
    from . import publication
    from . import product_format as PF
    for e in embeds:
        product=e.get('_mh_product_card') or e.get('_mh_product_category') or (e.get('url') and e.get('title'))
        if product and (not publication.valid_proof(e.get('_mh_price_proof')) or f"£{e['_mh_price_proof']['listing']:.2f}" not in json.dumps({k:v for k,v in e.items() if not k.startswith('_mh_')},ensure_ascii=False)):return None
        if any(not publication.allowed(r) for r in e.get('_mh_product_rows',[])):return None
        if PF.reason({'title':e.get('title','')}):return None
        if e.get('_mh_product_category')=='lego' or __import__('re').search(r'\blego\b[^\n]*\b\d{5,6}\b',str(e.get('title',''))+'\n'+str((e.get('author') or {}).get('name','')),__import__('re').I):
            row={'category':'lego','thumb':(e.get('image') or {}).get('url'),'image_status':e.get('_mh_image_status'),
                 'image_verified_url':e.get('_mh_image_verified_url'),'image_verified_until':e.get('_mh_image_verified_until')}
            if not publishable(row):return None
    clean=[]
    for e in embeds[:10]:
        item={k:v for k,v in e.items() if not k.startswith('_mh_')}
        if (e.get('_mh_image_basis') or '').startswith('Reference') and 'reference' not in item.get('description','').lower():item['description']=item.get('description','')+'\nImage: exact-set reference, not proof of listing condition.'
        clean.append(item)
    payload={'username':'MONEYHUNTER','content':content,'embeds':clean,'allowed_mentions':{'parse':[]}}
    if os.getenv('MONEYHUNTER_AVATAR_URL'):payload['avatar_url']=os.environ['MONEYHUNTER_AVATAR_URL']
    if components:payload['components']=components
    return payload
