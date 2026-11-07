"""Product images from the item's own approved feed/API metadata; never download URLs."""
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
        path=u.path.replace('/re/150x150/','/re/300x300/') if u.hostname=='images.hotukdeals.com' else u.path
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
            r.update(thumb=ref['thumb'],image_source_url=ref['url'],image_basis='Reference product image for same exact LEGO set, not actual listing-condition evidence')
    return raws
