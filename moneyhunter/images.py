"""Approved exact-product image metadata, bounded header checks and publication holds."""
import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit
HOSTS={'images.hotukdeals.com','static.pepper.com','i.ebayimg.com'}

def safe(value):
    if not isinstance(value,str) or len(value)>2000:return ''
    try:
        u=urlsplit(html.unescape(value.strip()))
        if u.scheme!='https' or u.hostname not in HOSTS or u.username or u.password or u.port not in (None,443):return ''
        if re.search(r'logo|avatar|placeholder|banner|\.svg(?:$|\?)',u.path,re.I):return ''
        if not u.path or u.path=='/':return ''
        path=u.path
        return urlunsplit((u.scheme,u.netloc,path,u.query,''))
    except (ValueError,TypeError):return ''

class _Images(HTMLParser):
    def __init__(self):super().__init__();self.urls=[]
    def handle_starttag(self,tag,attrs):
        if tag=='img':self.urls.append(dict(attrs).get('src',''))

def feed(item,ns):
    candidates=[]
    for name in ('media:content','media:thumbnail','enclosure'):
        el=item.find(name,ns)
        if el is not None:candidates.append(el.get('url',''))
    p=_Images();p.feed(html.unescape(item.findtext('description') or ''));candidates+=p.urls
    return next((v for x in candidates if (v:=safe(x))), '')

def enrich(raws):
    """Own-source photo first; exact new LEGO set reference only if own photo absent."""
    from . import market
    refs={}
    for r in raws:
        r['thumb']=safe(r.get('thumb',''))
        if r['thumb']:
            r.setdefault('image_source_url',r['url']);r.setdefault('image_basis','Own offer/feed product image')
            ident=market.identity(r)
            if ident and ident.category=='lego':
                ids=re.findall(r'(?<!\d)\d{5,6}(?!\d)',ident.match)
                if len(ids)==1:refs.setdefault(ids[0],r)
    for r in raws:
        if r['thumb']:continue
        ident=market.identity(r)
        if not ident or ident.category!='lego':continue
        ids=re.findall(r'(?<!\d)\d{5,6}(?!\d)',ident.match)
        ref=refs.get(ids[0]) if len(ids)==1 else None
        if ref and market.matches(r['title'],market.identity(ref)):
            r.update(thumb=ref['thumb'],image_source_url=ref.get('image_source_url',ref['url']),image_basis='Reference product image for same exact LEGO set, not actual listing-condition evidence')
    return raws

# A source URL is not proof that a browser/Discord can retrieve an actual image.
# No redirects, arbitrary hosts, credentials, unbounded reads or network retries.
import datetime as dt
import urllib.request
import urllib.error
MAX_FETCHES=32
TTL_SECONDS=20*60
NEGATIVE_SECONDS=5*60
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def signature(body):
    return (body.startswith(b'\xff\xd8\xff') or body.startswith(b'\x89PNG\r\n\x1a\n') or
            body.startswith((b'GIF87a',b'GIF89a')) or (body.startswith(b'RIFF') and body[8:12]==b'WEBP'))

def probe(url):
    url=safe(url)
    if not url:return False,'unsafe_url'
    req=urllib.request.Request(url,headers={'User-Agent':'moneyhunter/0.1 image-publication-check','Accept':'image/jpeg,image/png,image/webp,image/gif'})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req,timeout=3) as response:
            kind=response.headers.get('Content-Type','').split(';')[0].lower()
            good=response.status==200 and kind in ('image/jpeg','image/png','image/webp','image/gif') and signature(response.read(4096))
            return good, 'http200_image' if good else 'non_image_or_status'
    except urllib.error.HTTPError as e:return False,'http_'+str(e.code)
    except (urllib.error.URLError,OSError,TimeoutError,ValueError):return False,'unavailable'

def publishable(row,now=None):
    if row.get('category')!='lego':return True
    now=now or dt.datetime.now(dt.timezone.utc)
    try:return bool(safe(row.get('thumb'))) and row.get('image_status')=='verified' and row.get('image_verified_url')==safe(row.get('thumb')) and dt.datetime.fromisoformat(row.get('image_verified_until',''))>now
    except (ValueError,TypeError):return False

def metadata(row):
    from .publication import metadata as pricing_metadata
    return {**pricing_metadata(row),'_mh_product_category':row.get('category'),'_mh_image_basis':row.get('image_basis'), '_mh_image_verified_url':row.get('image_verified_url'),
            '_mh_image_verified_until':row.get('image_verified_until'), '_mh_image_status':row.get('image_status'),
            '_mh_image_candidates':row.get('image_candidates',[])}

def prepare(raws,state,when=None):
    """Bounded real-image intake; missing photos remain pending and never acknowledge alerts."""
    now=when or dt.datetime.now(dt.timezone.utc);clock=now.timestamp();cache=state.setdefault('product_images_v1',{})
    paused=state.setdefault('product_image_paused_hosts',{})
    report={'checked':0,'cached':0,'verified':0,'pending':0,'budget':MAX_FETCHES}
    def checked(url):
        url=safe(url)
        if not url or urlsplit(url).hostname in paused:return None
        rec=cache.get(url,{})
        if rec.get('expires',0)>clock:report['cached']+=1;return rec if rec.get('ok') else None
        if report['checked']>=MAX_FETCHES:return None
        report['checked']+=1;ok,status=probe(url)
        if status in ('http_401','http_403'):paused[urlsplit(url).hostname]=status
        rec={'ok':ok,'status':status,'checked_at':now.isoformat(),'expires':clock+(TTL_SECONDS if ok else NEGATIVE_SECONDS)};cache[url]=rec
        return rec if ok else None
    def variants(url):
        url=safe(url)
        return list(dict.fromkeys([url.replace('/re/150x150/','/re/300x300/'),url.replace('/re/300x300/','/re/150x150/')])) if url else []
    lego=[r for r in raws if r.get('category')=='lego']
    for r in lego:
        choices=list(dict.fromkeys(variants(r.get('thumb'))+[u for old in r.get('image_candidates',[]) for u in variants(old)]))[:4];r['image_candidates']=choices
        r['thumb']=next((u for u in choices if checked(u)), '')
    enrich(raws)  # only validated original photos can now be exact-set references
    from . import market
    for r in lego:
        if not r['thumb']:
            ident=market.identity(r)
            if ident:
                offers=(o for snap in state.get('ask_cache',{}).values() for o in snap.get('offers',[]) if o.get('image') and market.matches(o.get('title',''),ident))
                for o in offers:
                    choices=variants(o['image']);r['image_candidates']+=choices
                    chosen=next((u for u in choices if checked(u)), '')
                    if chosen:
                        r.update(thumb=chosen,image_source_url=o['url'],image_basis='Reference product image for same exact LEGO set, not actual listing-condition evidence');break
        rec=cache.get(r.get('thumb'),{})
        good=bool(r.get('thumb')) and urlsplit(r['thumb']).hostname not in paused and rec.get('ok') and rec.get('expires',0)>clock
        r['image_candidates']=list(dict.fromkeys(([r['thumb']] if good else [])+r.get('image_candidates',[])))[:4]
        r.update(image_status='verified' if good else 'pending_photo',image_verified_url=r['thumb'] if good else '',
                 image_checked_at=rec.get('checked_at') if good else None,
                 image_verified_until=dt.datetime.fromtimestamp(rec['expires'],dt.timezone.utc).isoformat() if good else None)
        report['verified' if good else 'pending']+=1
        if not good:r['thumb']=''
    report['paused_hosts']=dict(paused)
    state['product_images_v1']={u:r for u,r in cache.items() if r.get('expires',0)>clock-86400}
    return report
