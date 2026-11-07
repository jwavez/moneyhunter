"""Explicit, bounded NEW UK variants. Missing attributes are not guessed.

Manufacturer references and permitted aliases are documented in CATEGORY_COVERAGE.md.
Trainer family queries are discovery-only: every accepted item still needs one UK size.
"""
import re
from types import SimpleNamespace
from . import matching as M

TECH = {
    'WHCH520': ('black', 'white', 'blue', 'beige'),
    'WFC510': ('black', 'white', 'blue', 'yellow'),
    'WFC710N': ('black', 'white', 'pink', 'glass blue'),
    'WH1000XM4': ('black','silver','blue'),
    'WH1000XM5': ('black','silver','blue','smoky pink'),
}
# Specific family/flanker, concentration, explicit single bottle volume.
SCENTS = [
    ('boss bottled infinite', r'\bboss\b.*\bbottled infinite\b', 'edp', ('night','elixir','absolu','tonic')),
    ('boss bottled', r'\bboss\b.*\bbottled\b', 'edt', ('infinite','night','elixir','absolu','tonic','intense','oud','pacific','triumph','unlimited')),
    ('armani acqua di gio profondo', r'\b(?:armani|giorgio)\b.*\bacqua di gio profondo\b', 'parfum', ('lights','intense')),
    ('armani because it s you', r'\barmani\b.*\bbecause it s you\b', 'edp', ('stronger',)),
    ('ariana grande mod blush', r'\bariana grande\b.*\bmod blush\b', 'edp', ('vanilla',)),
    ('gucci guilty for him', r'\bgucci guilty\b.*\b(?:for him|pour homme)\b', 'edt', ('absolute','elixir','love','black','intense')),
    ('issey miyake l eau d issey pour homme sport', r'\bissey miyake\b.*\beau d issey pour homme sport\b', 'edt', ('intense','vetiver')),
]
BAD = ('used','refurbished','renewed','open box','ex display','damaged','tester','testers','decant','sample','miniature','gift set','giftset','bundle','multipack','replica','compatible','replacement','parts only','box only','empty box')
KNOWN_STYLE_GENDER = {'IM9013-001':'women'}

def clean(title):
    import unicodedata
    return M.norm(unicodedata.normalize('NFKD', title).encode('ascii','ignore').decode())

def make(cat, query, variant, **extra):
    return SimpleNamespace(category=cat,match=query,identity={'condition':'new',**variant},name_terms=[],variant=variant,**extra)

def concentration(t):
    t=re.sub(r'eau de parfum', 'edp', t)
    t=re.sub(r'eau de toilette', 'edt', t)
    found=[v for v in ('edp','edt','parfum') if M.has(t,v)]
    return found[0] if len(found)==1 else None

def trainer(raw, seed=False):
    title=raw.get('title',''); t=clean(title)
    if not M.has(t,'nike') or M.has(t,*BAD,*M.KIDS,'junior','youth','infant','gs','socks','insole','shoelaces','custom','shirt','hoodie','trousers','jacket','shorts','bikini','leggings','tee','tracksuit'): return None
    # Description codes only form a family discovery query, never a size valuation.
    text=title+' '+(raw.get('desc','') if seed else '')
    codes=set(re.findall(r'\b[A-Z]{2}\d{4}-\d{3}\b', text, re.I))
    codes={s.upper() for s in codes}
    if len(codes)!=1:return None
    code=next(iter(codes))
    sizes=re.findall(r'\buk\s*(?:size\s*)?(\d{1,2}(?:\.5)?)\b',title,re.I)+re.findall(r'\b(\d{1,2}(?:\.5)?)\s*uk\b',title,re.I)
    multi=re.search(r'\buk\s*(?:size\s*)?\d+(?:\.5)?\s*(?:[-/,&]|or|to)\s*\d',title,re.I) or M.has(t,'sizes','choose size','various sizes','select size')
    genders=[g for g,terms in [('women',('women','womens','woman','ladies')),('men',('men','mens','man')),('unisex',('unisex',))] if M.has(t,*terms)]
    expected=KNOWN_STYLE_GENDER.get(code)
    if len(genders)>1 or (expected and genders and genders[0] not in (expected,'unisex')):return None
    gender=expected or (genders[0] if genders else None)
    if seed and (multi or len(set(sizes))!=1 or not gender):
        return make('trainers','Nike '+code,{'style_code':code},discovery_seed=True)
    if multi or len(set(sizes))!=1 or not gender:return None
    size=float(sizes[0])
    if not 2<=size<=15:return None
    return make('trainers',f'Nike {code} UK {size:g}',{'brand':'Nike','style_code':code,'uk_size':size,'department':gender})

def identity(raw):
    title=raw.get('title',''); cat=raw.get('category'); t=clean(title)
    if M.has(t,*BAD) or re.search(r'\b(?:ex[- ]display|damaged|refurbished|used condition)\b',raw.get('desc',''),re.I):return None
    if cat=='trainers':return trainer(raw)
    if cat=='tech':
        if not M.has(t,'sony') or M.has(t,'case','cover','earpad','ear pads','headband','charger','charging case','cable','parts','spares','left only','right only','single earbud','one piece','limited edition'):return None
        compact=re.sub(r'[^a-z0-9]','',title.lower())
        patterns={'WHCH520':r'wh[ -]?ch[ -]?520','WFC510':r'wf[ -]?c[ -]?510','WFC710N':r'wf[ -]?c[ -]?710n','WH1000XM4':r'wh[ -]?1000xm4','WH1000XM5':r'wh[ -]?1000xm5'}
        models=[m for m in TECH if re.search(r'\b'+patterns[m]+r'\b',title,re.I)]
        if len(models)!=1:return None
        model=models[0]
        # Long colour names must not also count their suffix as a second variant.
        colours=[c for c in TECH[model] if M.has(t,c)]
        if model=='WFC710N' and M.has(t,'blue') and 'glass blue' not in colours:colours.append('glass blue')
        all_colours=('black','white','blue','yellow','pink','silver','beige')
        selected=set(' '.join(colours).split())
        if len(colours)!=1 or any(M.has(t,c) and c not in selected for c in all_colours):return None
        colour=colours[0]
        return make(cat,f'Sony {model} {colour}',{'brand':'Sony','model':model,'colour':colour,'edition':'standard'})
    if cat=='fragrance':
        if M.has(t,'refill','refills','body spray','deodorant','after shave','aftershave','gift','set') or re.search(r'\b\d+\s*[x×]\s*\d+',title,re.I):return None
        volumes=set(re.findall(r'\b(\d{1,3})\s*ml\b',title,re.I))
        if len(volumes)!=1:return None
        volume=int(next(iter(volumes)))
        if not 30<=volume<=250:return None
        conc=concentration(t)
        for family,pattern,wanted,banned in SCENTS:
            found=re.search(pattern,t)
            between=re.split(r'\b(?:edp|edt|parfum|eau|\d+\s*ml)\b',t[found.end():],maxsplit=1)[0] if found else ''
            between=re.sub(r'\b(?:for him|for men|pour homme|spray|fragrance|perfume|new|sealed|mens|men)\b','',between).strip()
            if found and not between and conc==wanted and not M.has(t,*banned):
                bottle='refillable' if M.has(t,'refillable') else 'not stated'
                return make(cat,f'{family} {conc.upper()} {volume}ml'+(' refillable' if bottle=='refillable' else ''),
                    {'family':family,'concentration':conc,'ml':volume,'bottle_format':bottle})
    return None

def matches(title, ident):
    got=identity({'category':ident.category,'title':title})
    if not got:return False
    if getattr(ident,'discovery_seed',False):return got.variant.get('style_code')==ident.variant.get('style_code')
    return got.variant==ident.variant
