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
    ('boss bottled aftershave lotion', r'\bboss\b.*\bbottled\b', 'aftershave lotion', ('infinite','night','elixir','intense','balm')),
    ('boss bottled infinite', r'\bboss\b.*\bbottled infinite\b', 'edp', ('night','elixir','absolu','tonic')),
    ('boss bottled', r'\bboss\b.*\bbottled\b', 'edt', ('infinite','night','elixir','absolu','tonic','intense','oud','pacific','triumph','unlimited')),
    ('armani acqua di gio profondo', r'\b(?:armani|giorgio)\b.*\bacqua di gio profondo\b', 'parfum', ('lights','intense')),
    ('armani because it s you', r'\barmani\b.*\bbecause it s you\b', 'edp', ('stronger',)),
    ('ariana grande mod blush', r'\bariana grande\b.*\bmod blush\b', 'edp', ('vanilla',)),
    ('gucci guilty for him', r'\bgucci guilty\b.*\b(?:for him|pour homme)\b', 'edt', ('absolute','elixir','love','black','intense')),
    ('issey miyake l eau d issey pour homme sport', r'\bissey miyake\b.*\beau d issey pour homme sport\b', 'edt', ('intense','vetiver')),
]
BAD = ('used','refurbished','renewed','open box','ex display','damaged','tester','testers','decant','sample','miniature','gift set','giftset','bundle','multipack','replica','compatible','replacement','parts only','box only','empty box')
ADIDAS_STYLE_CODES={'IH4316','KK2683','LA1823','KI6121'}  # source-declared articles in the bounded current-feed review
KNOWN_STYLE_GENDER = {'IM9013-001':'women'}

def clean(title):
    import unicodedata
    return M.norm(unicodedata.normalize('NFKD', title).encode('ascii','ignore').decode())

def make(cat, query, variant, **extra):
    return SimpleNamespace(category=cat,match=query,identity={'condition':'new',**variant},name_terms=[],variant=variant,**extra)

def concentration(t):
    if M.has(t,'aftershave lotion','after shave lotion'):
        return None if M.has(t,'edt','edp','eau de toilette','eau de parfum','parfum') else 'aftershave lotion'
    t=re.sub(r'eau de parfum', 'edp', t)
    t=re.sub(r'eau de toilette', 'edt', t)
    found=[v for v in ('edp','edt','parfum') if M.has(t,v)]
    return found[0] if len(found)==1 else None

def trainer(raw, seed=False):
    title=raw.get('title',''); t=clean(title)
    brand="Nike" if M.has(t,"nike") else "adidas" if M.has(t,"adidas") else None
    if not brand or M.has(t,*BAD,*M.KIDS,'junior','youth','infant','gs','socks','insole','shoelaces','custom','shirt','hoodie','trousers','jacket','shorts','bikini','leggings','tee','tracksuit'): return None
    # Description codes only form a family discovery query, never a size valuation.
    pattern=r'[A-Z]{2}\d{4}-\d{3}' if brand=='Nike' else r'[A-Z]{2}\d{4}'
    text=title+' '+(raw.get('desc','') if seed else '')
    codes=set(re.findall(r'\b'+pattern+r'\b',text,re.I))
    # A labelled primary article declaration can complete an otherwise exact feed
    # title. Never select a size or attach arbitrary six-character prose codes.
    if not seed:
        body=re.sub(r'<[^>]+>',' ',raw.get('desc',''))
        codes.update(re.findall(r'(?:style code|article(?: number| code)?|item model number|manufacturer part number|mpn)\s*[:#=-]?\s*('+pattern+r')\b',body,re.I))
        for e in raw.get('identity_evidence',[]):
            if e.get('source_url')==raw.get('url') and e.get('brand')==brand and re.fullmatch(pattern,e.get('code',''),re.I):codes.add(e['code'])
    codes={s.upper() for s in codes}
    if len(codes)!=1:return None
    code=next(iter(codes))
    if brand=='adidas' and code not in ADIDAS_STYLE_CODES:return None
    sizes=re.findall(r'\buk\s*(?:size\s*)?(\d{1,2}(?:\.5)?)\b',title,re.I)+re.findall(r'\b(\d{1,2}(?:\.5)?)\s*uk\b',title,re.I)
    multi=re.search(r'\buk\s*(?:size\s*)?\d+(?:\.5)?\s*(?:[-/,&]|or|to)\s*\d',title,re.I) or M.has(t,'sizes','choose size','various sizes','select size')
    genders=[g for g,terms in [('women',('women','womens','woman','ladies')),('men',('men','mens','man')),('unisex',('unisex',))] if M.has(t,*terms)]
    expected=KNOWN_STYLE_GENDER.get(code)
    if len(genders)>1 or (expected and genders and genders[0] not in (expected,'unisex')):return None
    gender=expected or (genders[0] if genders else None)
    if seed and (multi or len(set(sizes))!=1 or not gender):
        return make('trainers',brand+' '+code,{'style_code':code},discovery_seed=True)
    if multi or len(set(sizes))!=1 or not gender:return None
    size=float(sizes[0])
    if not 2<=size<=15:return None
    return make('trainers',f'{brand} {code} UK {size:g}',{'brand':brand,'style_code':code,'uk_size':size,'department':gender})

def identity(raw):
    title=raw.get('title',''); cat=raw.get('category'); t=clean(title)
    if M.has(t,*BAD) or re.search(r'\b(?:ex[- ]display|damaged|refurbished|used condition)\b',raw.get('desc',''),re.I):return None
    if cat=='tools':
        # Only verified bare-tool models; battery/charger/kits are separate identities.
        models={'DUB185Z':('Makita','blower'),'DTD152Z':('Makita','impact driver'),'DGA452Z':('Makita','angle grinder'),'DJV182Z':('Makita','jigsaw'),'DCF887N':('DeWalt','impact driver'),'DCV100':('DeWalt','blower'),'DCS382N':('DeWalt','reciprocating saw'),'DCS565N':('DeWalt','circular saw')}
        found=[]
        for model,(brand,kind) in models.items():
            if re.search(r'\b'+model+(r'(?:-XJ)?' if brand=='DeWalt' else '')+r'(?![-a-z0-9])',title,re.I) and M.has(t,brand.lower()):found.append((model,brand,kind))
        if len(found)!=1 or M.has(t,'kit','charger','batteries','with battery','battery included','case only','housing','spares','replacement','bit holder') or re.search(r'\b(?:BL\d+|DT\d+|DUB186|DCF887[DP]\d)\b',title,re.I):return None
        if M.has(t,'tool bag','carry case','carrying case') or re.search(r'(?:with|plus|\+|and)\s+(?:a\s+)?(?:case|bag)\b',title,re.I):return None
        model,brand,kind=found[0]
        if any(int(n)!=18 for n in re.findall(r'(?<!\d)(\d+)\s*v\b',title,re.I)):return None
        battery_text=re.sub(r'no batter(?:y|ies)|without batter(?:y|ies)|batter(?:y|ies) (?:not included|sold separately)|battery powered','',t)
        if M.has(battery_text,'battery','batteries') or re.search(r'\d+(?:\.\d+)?\s*ah\b',battery_text):return None
        # DCF887N-XJ is the manufacturer's UK bare-tool page; never alias kits.
        remainder=re.sub(r'\b'+model+r'(?:-XJ)?\b','',title,flags=re.I)
        if re.search(r'\b(?:DUB|DCF|DCV|DCB|DCS|DTD|DGA|DJV|BL|DT)\d+',remainder,re.I):return None
        if not M.has(t,'bare','bare unit','body only','tool only','naked') and not re.search(r'\b'+model+(r'(?:-XJ)?' if brand=='DeWalt' else '')+r'(?![-a-z0-9])',title,re.I):return None
        return make(cat,f'{brand} {model} bare tool 18V',{'brand':brand,'model':model,'voltage':18,'contents':'bare tool; no battery/charger','region':'GB listing; warranty unverified'})
    if cat=='trainers':return trainer(raw)
    if cat=='tech':
        extended=audio(raw)
        if extended:return extended
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
        if M.has(t,'refill','refills','body spray','deodorant','gift','set') or re.search(r'\b\d+\s*[x×]\s*\d+',title,re.I):return None
        volumes=set(re.findall(r'\b(\d{1,3})\s*ml\b',title,re.I))
        if len(volumes)!=1:return None
        volume=int(next(iter(volumes)))
        if not 30<=volume<=250:return None
        conc=concentration(t)
        for family,pattern,wanted,banned in SCENTS:
            found=re.search(pattern,t)
            between=re.split(r'\b(?:aftershave|after shave|edp|edt|parfum|eau|\d+\s*ml)\b',t[found.end():],maxsplit=1)[0] if found else ''
            between=re.sub(r'\b(?:for him|for men|pour homme|spray|fragrance|perfume|new|sealed|mens|men)\b','',between).strip()
            if found and not between and conc==wanted and not M.has(t,*banned):
                bottle='refillable' if M.has(t,'refillable') else 'not stated'
                return make(cat,(f'{family} {volume}ml' if conc=='aftershave lotion' else f'{family} {conc.upper()} {volume}ml')+(' refillable' if bottle=='refillable' else ''),
                    {'family':family,'concentration':conc,'ml':volume,'bottle_format':bottle})
    return None

def matches(title, ident):
    got=identity({'category':ident.category,'title':title})
    if not got:return False
    if getattr(ident,'discovery_seed',False):return got.variant.get('style_code')==ident.variant.get('style_code')
    return got.variant==ident.variant


# Bounded declared model/colour families; no default colour or regional-name alias.
AUDIO=(('Soundcore','P40I',r'\bsoundcore\b.*\bp40i\b',('black','white','blue','purple'),'A3955'),
       ('Soundcore','R50I',r'\bsoundcore\b.*\br50i\b',('black','white','blue'),'A3949'),
       ('Soundcore','Q21I',r'\bsoundcore\b.*\bq21i\b',('black','white','blue'),None),
       ('Xiaomi','Redmi Buds 6 Pro',r'\b(?:xiaomi|redmi)\b.*\bbuds 6 pro\b',('space black','glacier white','lavender purple'),None),
       ('Google','Pixel Buds 2a',r'\bgoogle\b.*\bpixel buds 2a\b',('hazel','iris'),None),
       ('Bose','SoundLink Flex 2nd Gen',r'\bbose\b.*\bsoundlink flex\b.*\b(?:2nd gen|second generation|2nd generation)\b',('black','blue dusk','sandstone','alpine sage'),None))
def audio(raw):
    title=raw.get('title','');t=clean(title)
    if M.has(t,*BAD,'case only','charging case','earpad','ear pads','cover','replacement','left only','right only','single earbud','silicone','skin'):return None
    found=[x for x in AUDIO if re.search(x[2],t)]
    if len(found)!=1:return None
    brand,model,_,colours,mpn=found[0]
    if model=='R50I':
        body=re.sub(r'<[^>]+>',' ',raw.get('desc',''))
        declared=title+' '+' '.join(re.findall(r'(?:mpn|manufacturer part number|item model number)\s*[:#=-]?\s*(A\d{4})\b',body,re.I))
        declared+=' '+' '.join(e.get('code','') for e in raw.get('identity_evidence',[]) if e.get('brand')=='Soundcore' and e.get('source_url')==raw.get('url') and e.get('code')=='A3949')
        # Manufacturer uses R50i across distinct hardware; marketing name alone
        # cannot decide A3949 versus A3959/NC, or establish regional equivalence.
        if not re.search(r'\bA3949\b',declared,re.I) or re.search(r'\b(?:A3959|ANC|NC)\b',declared,re.I):return None
    cs=[c for c in colours if M.has(t,c)]
    if len(cs)!=1 or any(M.has(t,c) and c not in set(' '.join(cs).split()) for c in ('black','white','blue','purple','pink','yellow','silver','beige','green','red','brown','hazel','iris')) or re.search(r'\b(?:black|white|blue|purple|pink|hazel|iris)\b\s*(?:or|/)\s*\b(?:black|white|blue|purple|pink|hazel|iris)\b',t):return None
    return make('tech',f'{brand} {model} {cs[0]}',{'brand':brand,'model':model,'colour':cs[0],'edition':'standard',**({'manufacturer_model':mpn} if mpn else {})})

def attach_source_identity(raw):
    if raw.get('category')=='tech':
        ident=audio(raw)
        if ident and ident.variant.get('model')=='R50I' and 'A3949' not in raw.get('title','').upper():raw['identity_evidence']=[{'brand':'Soundcore','code':'A3949','source_url':raw.get('url'),'basis':'Explicit source MPN/model declaration; no regional marketing-name equivalence inferred'}]
        return raw
    if raw.get('category')!='trainers':return raw
    ident=trainer(raw)
    if ident and ident.variant.get('style_code') not in raw.get('title','').upper():
        raw['identity_evidence']=[{'brand':ident.variant['brand'],'code':ident.variant['style_code'],'source_url':raw.get('url'),'basis':'Explicit source-description article/model declaration; retailer variant still needs verification'}]
    return raw
