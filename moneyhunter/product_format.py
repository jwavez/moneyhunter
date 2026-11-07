"""Physical-format guard independent of feed category or merchant branding."""
import re
STORES={'eneba','loaded','cdkeys','cdkeys.com','steam','epic games','epic games store','gog','gog.com','xbox','microsoft','nintendo eshop','playstation store'}
HARDWARE=re.compile(r'\b(keyboards?|keycaps?|key switches|controller|headset|mouse|console|racing wheel|camera|thermometer|digital piano|steam deck|laptop|notebook|tablet|monitor|television|earbuds|headphones|smartphone|speaker|drill|building set|building kit)\b',re.I)
EXPLICIT=re.compile(r'\b(pc[ -]?(?:game[ -]?)?key|cd[ -]?keys?|game[ -]?key|activation[ -]?(?:key|code)|download[ -]?code|digital[ -]?(?:code|key|download)|code in a box|gift[ -]?card|e[ -]?gift|software licen[cs]e|licen[cs]e|steam key|gog key|epic key)\b',re.I)
def reason(x):
    title=re.sub('[‐‑‒–—]','-',str(x.get('title','')));hardware=bool(HARDWARE.search(title)) or computer(title)
    if hardware and re.search(r'\b(keyboard|keycaps?|key switches)\b',title,re.I) and re.search(r'replacement|spare|keycaps?|key switches|keyboard keys',title,re.I) and not re.search(r'activation|download|licen[cs]e|game key|software',title,re.I):return None
    if EXPLICIT.search(title):return 'Digital key/code/licence is not a physical resale item'
    if not hardware and re.search(r'\b(digital|download|steam|gog|epic games|game pass|season pass|dlc|subscription|membership|licen[cs]e)\b',title,re.I):return 'Digital/nonphysical format; physical delivery and resale economics do not apply'
    if not hardware and str(x.get('merchant','')).strip().lower() in STORES:return 'Digital storefront format not confirmed physical'
    return None

def computer(title):return bool(re.search(r'\b(desktop|workstation|mini pc)\b',title,re.I) and re.search(r'\b(ryzen|intel|geforce|\d+gb|\d+tb)\b',title,re.I))

def normalize(x):
    x=dict(x)
    if reason(x):x.update(category='digital',online_eligible=False,physical_status='excluded_nonphysical');return x
    t=str(x.get('title',''))
    if computer(t):x['category']='tech'
    if re.search(r'\blego\b',t,re.I) and not re.search(r'(?<!\d)\d{5,6}(?!\d)',t) and re.search(r'\b(ps[45]|playstation|xbox|nintendo switch|pc (?:disc|dvd)|video game)\b',t,re.I):x['category']='gaming'
    return x

def partition(rows):
    physical=[];excluded=[]
    for raw in rows:
        x=normalize(raw);why=reason(raw)
        if why:excluded.append({k:raw.get(k) for k in ('title','url','price','merchant','source')}|{'category':'digital','reason':why})
        else:raw.update(x);physical.append(raw)
    return physical,excluded

def research_card(x):
    return {'title':str(x.get('title',''))[:250],'url':x.get('url'),'description':'EXCLUDED — NONPHYSICAL. '+str(reason(x) or 'Physical format not confirmed')+'. No physical postage, profit or LEGO-set advice applies.','fields':[]}
