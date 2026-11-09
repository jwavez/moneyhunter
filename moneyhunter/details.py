"""Bounded official getItem checks. Missing/conflicting detail is NOT authentication.
Lowest asks remain visible: detail uncertainty cannot inflate a resale estimate.
"""
import datetime as dt
import re
from . import research_budget, variants
from .scanners import ebay
LIMIT=4
TTL_MINUTES=30

# Guide section 5 names. Additive side channel only — never drives status/reasons.
SUB_TITLE_MODEL='title_model_number_missing'
SUB_CONDITION='condition_mismatch'
SUB_PRICE='price_mismatch'
SUB_SHIP_UNKNOWN='shipping_unknown'
SUB_SHIP_MISMATCH='shipping_mismatch'
SUB_AVAIL='availability_unavailable'
SUB_VARIATION='variation_mismatch'
SUB_OTHER='other'

# Tool voltage tokens may be "18", "18.0v", "18 volt", etc. Decimal-aware.
_VOLTAGE_TOKEN=re.compile(r'(?<![\d.])(\d+(?:\.\d+)?)\s*-?\s*(?:volts?|v)\b',re.I)

def normalise_voltage(value):
    """Parse a voltage string to float volts, or None. Never raises."""
    try:
        if value is None:return None
        text=str(value).strip().lower()
        if not text:return None
        # Strip trailing unit: volts/volt/-volts/-volt/v with optional whitespace.
        text=re.sub(r'(?:\s*-?\s*volts?|\s*-?\s*v)\s*$','',text).strip()
        if not text:return None
        return float(text)
    except (TypeError,ValueError):
        return None

def extract_voltages(text):
    """Whole-token voltages from free text, including decimals like 18.0V / 21.6V."""
    try:
        if text is None:return []
        raw=str(text)
        found=[normalise_voltage(m.group(0)) for m in _VOLTAGE_TOKEN.finditer(raw)]
        nums=[n for n in found if n is not None]
        if nums:return nums
        whole=normalise_voltage(raw)
        return [whole] if whole is not None else []
    except (TypeError,ValueError):
        return []

def voltage_matches_expected(observed,expected=18):
    """True only when every parsed voltage equals expected. Empty/garbage -> False."""
    try:
        nums=extract_voltages(observed)
        return bool(nums) and all(n==float(expected) for n in nums)
    except (TypeError,ValueError):
        return False

def risky(ident):
    return ident.category in ('fragrance','trainers','tech','tools') or bool(re.search(r'\b(controller|headset|peripheral)\b',ident.match,re.I))

def _fail(sub_checks, name, reason, expected=None, observed=None, note=None):
    """Record an additive sub-check failure. Does not decide status."""
    entry={'sub_check_failed':name,'expected':expected,'observed':observed,'reason':reason}
    if note is not None:entry['note']=note
    sub_checks.append(entry)
    return reason

def assess(data,offer,ident,when):
    from . import market
    out={'item_id':offer['item_id'],'observed_at':when.isoformat(timespec='seconds'),'status':'incomplete','reasons':[],
        'gtin':data.get('gtin'),'mpn':data.get('mpn'),'aspects':data.get('localizedAspects',[])[:40],
        'checked_item_price':offer['item_price'],'identity_query':ident.match,'condition_id':data.get('conditionId'),'availability':data.get('estimatedAvailabilities',[]),'source_url':offer['url']}
    bad=[];missing=[];sub_checks=[]
    # Retain already-fetched getItem fields for diagnostics — no extra API calls.
    out['title']=data.get('title')
    if data.get('primaryItemGroup') or data.get('itemGroupHref'):
        missing.append(_fail(sub_checks,SUB_VARIATION,'variation listing requires unambiguous selected-variant price',
                             expected='single selected variant',observed='variation group present'))
    if data.get('conditionId') is None:
        missing.append(_fail(sub_checks,SUB_CONDITION,'condition missing',expected='1000',observed=None))
    elif str(data.get('conditionId'))!='1000':
        bad.append(_fail(sub_checks,SUB_CONDITION,'condition not NEW',expected='1000',observed=str(data.get('conditionId'))))
    if not market.matches(data.get('title',''),ident):
        bad.append(_fail(sub_checks,SUB_TITLE_MODEL,'detail title contradicts exact identity',
                         expected=ident.match,observed=data.get('title')))
    if market.money(data.get('price'))!=offer['item_price']:
        bad.append(_fail(sub_checks,SUB_PRICE,'price changed or currency unknown',
                         expected=offer['item_price'],observed=market.money(data.get('price'))))
    avail=data.get('estimatedAvailabilities',[])
    if any(a.get('estimatedAvailabilityStatus')=='OUT_OF_STOCK' or a.get('estimatedAvailableQuantity')==0 for a in avail):
        bad.append(_fail(sub_checks,SUB_AVAIL,'out of stock',expected='IN_STOCK/LIMITED_STOCK or qty>0',observed=avail))
    if not any(a.get('estimatedAvailabilityStatus') in ('IN_STOCK','LIMITED_STOCK') or (a.get('estimatedAvailableQuantity') or 0)>0 for a in avail):
        missing.append(_fail(sub_checks,SUB_AVAIL,'current availability not supplied',expected='IN_STOCK/LIMITED_STOCK or qty>0',observed=avail or None))
    end=data.get('itemEndDate')
    if end:
        try:
            if dt.datetime.fromisoformat(end.replace('Z','+00:00'))<=when:
                bad.append(_fail(sub_checks,SUB_AVAIL,'ended',expected='end date in future',observed=end))
        except (ValueError,TypeError):
            missing.append(_fail(sub_checks,SUB_OTHER,'end date invalid',expected='parseable ISO end date',observed=end,note='end date invalid'))
    shipping=[market.money(a.get('shippingCost')) for a in data.get('shippingOptions',[]) if a.get('shippingCostType')=='FIXED']
    shipping=[n for n in shipping if n is not None]
    out['fixed_shipping']=min(shipping) if shipping else None
    if not shipping:
        missing.append(_fail(sub_checks,SUB_SHIP_UNKNOWN,'fixed detail shipping not supplied',expected='FIXED shippingCost',observed=None))
    elif abs(min(shipping)-offer['shipping'])>.01:
        bad.append(_fail(sub_checks,SUB_SHIP_MISMATCH,'delivered price changed',expected=offer['shipping'],observed=min(shipping)))
    aspects={variants.clean(a.get('name','')).strip():str(a.get('value','')) for a in data.get('localizedAspects',[])}
    def values(*keys):return ' '.join(aspects.get(k,'') for k in keys).strip()
    v=getattr(ident,'variant',{})
    if ident.category=='fragrance':
        volume=values('volume','size','unit quantity')
        ml={int(n) for n in re.findall(r'(?<!\d)(\d{1,3})\s*ml\b',volume,re.I)}
        if not ml:missing.append(_fail(sub_checks,SUB_VARIATION,'bottle volume aspect missing',expected=v.get('ml'),observed=volume or None))
        elif ml!={v.get('ml')}:bad.append(_fail(sub_checks,SUB_VARIATION,'bottle volume mismatch',expected=v.get('ml'),observed=sorted(ml)))
        kind=variants.clean(values('type','concentration','formulation'))
        concentration=variants.concentration(kind)
        wanted=v.get('concentration')
        if wanted=='aftershave lotion':
            if not ('aftershave' in kind or 'after shave' in kind):
                missing.append(_fail(sub_checks,SUB_VARIATION,'aftershave type aspect missing',expected='aftershave lotion',observed=kind or None))
            if concentration in ('edt','edp','parfum') or 'balm' in kind:
                bad.append(_fail(sub_checks,SUB_VARIATION,'lotion versus fragrance/balm mismatch',expected='aftershave lotion',observed=kind or concentration))
        elif concentration is None:
            missing.append(_fail(sub_checks,SUB_VARIATION,'concentration aspect missing',expected=wanted,observed=kind or None))
        elif concentration!=wanted:
            bad.append(_fail(sub_checks,SUB_VARIATION,'concentration mismatch',expected=wanted,observed=concentration))
    elif ident.category=='trainers':
        size=values('uk shoe size','uk size')
        nums={float(n) for n in re.findall(r'(?<!\d)\d{1,2}(?:\.5)?(?!\d)',size)}
        if not nums:missing.append(_fail(sub_checks,SUB_VARIATION,'explicit UK size aspect missing',expected=v.get('uk_size'),observed=size or None))
        elif nums!={v.get('uk_size')}:bad.append(_fail(sub_checks,SUB_VARIATION,'UK size mismatch',expected=v.get('uk_size'),observed=sorted(nums)))
        department=variants.clean(values('department','gender')).strip()
        if not department:missing.append(_fail(sub_checks,SUB_VARIATION,'department aspect missing',expected=v.get('department'),observed=None))
        if department and ((v.get('department')=='men' and ('women' in department or 'girl' in department or 'boy' in department)) or (v.get('department')=='women' and department in ('men','mens','male'))):
            bad.append(_fail(sub_checks,SUB_VARIATION,'department mismatch',expected=v.get('department'),observed=department))
        style=values('style code','mpn','manufacturer part number') or str(data.get('mpn') or '')
        if not style:missing.append(_fail(sub_checks,SUB_TITLE_MODEL,'style-colour code aspect missing',expected=v.get('style_code'),observed=None))
        elif not re.search(r'(?<![a-z0-9])'+re.escape(v.get('style_code',''))+r'(?![a-z0-9])',style,re.I):
            bad.append(_fail(sub_checks,SUB_TITLE_MODEL,'style-colour code mismatch',expected=v.get('style_code'),observed=style))
    elif ident.category=='tools':
        included=variants.clean(values('battery included','batteries included','charger included')).strip()
        if re.sub(r'\b(?:not included|not supplied|sold separately|no|false|0)\b','',included).strip():
            bad.append(_fail(sub_checks,SUB_VARIATION,'battery/charger inclusion contradicts bare tool',
                             expected='not included / no battery',observed=included))
        voltage=values('voltage')
        if voltage and not voltage_matches_expected(voltage,18):
            bad.append(_fail(sub_checks,SUB_VARIATION,'tool voltage mismatch',expected=18,observed=voltage))
        model=values('model','mpn','manufacturer part number') or str(data.get('mpn') or '')
        expected=v.get('model','')
        if not model:
            missing.append(_fail(sub_checks,SUB_TITLE_MODEL,'exact tool model aspect missing',expected=expected,observed=None))
        elif not re.search(r'(?<![a-z0-9])'+re.escape(expected)+(r'(?:-XJ)?' if v.get('brand')=='DeWalt' else '')+r'(?![-a-z0-9])',model,re.I):
            bad.append(_fail(sub_checks,SUB_TITLE_MODEL,'tool model mismatch',expected=expected,observed=model))
    elif ident.category=='tech':
        model=values('model','mpn','manufacturer part number') or str(data.get('mpn') or '')
        compact=lambda s:re.sub(r'[^a-z0-9]','',s.lower())
        if not model:
            missing.append(_fail(sub_checks,SUB_TITLE_MODEL,'model aspect missing',expected=v.get('model'),observed=None))
        elif not re.search(r'(?<![a-z0-9])'+r'[\s-]*'.join(re.escape(c) for c in compact(v.get('model','')))+r'(?![a-z0-9])',model,re.I) and compact(model)!=compact(v.get('manufacturer_model','')):
            bad.append(_fail(sub_checks,SUB_TITLE_MODEL,'model aspect mismatch',expected=v.get('model'),observed=model))
        declared_mpn=str(data.get('mpn') or values('mpn','manufacturer part number')).strip()
        if v.get('manufacturer_model') and declared_mpn and compact(declared_mpn) not in (compact(v['manufacturer_model']),compact(v['model'])):
            bad.append(_fail(sub_checks,SUB_TITLE_MODEL,'manufacturer MPN requires exact variant verification; suffix not inferred',
                             expected=v.get('manufacturer_model'),observed=declared_mpn))
        colour=variants.clean(values('colour','color') or str(data.get('color') or '')).strip()
        if not colour:
            missing.append(_fail(sub_checks,SUB_VARIATION,'colour aspect missing',expected=v.get('colour'),observed=None))
        elif colour not in (v.get('colour'), 'blue' if v.get('colour')=='glass blue' else v.get('colour')):
            bad.append(_fail(sub_checks,SUB_VARIATION,'colour mismatch',expected=v.get('colour'),observed=colour))
    out['status']='conflict' if bad else 'incomplete' if missing else 'verified_fields'
    out['reasons']=bad+missing
    out['sub_checks']=sub_checks
    out['meaning']='Declared listing fields checked, NOT authenticity, sold evidence or checkout guarantee'
    # Inventory of fields already returned by this getItem payload (no refetch).
    present=[];absent=[]
    for label,ok in (
        ('title',bool(data.get('title'))),
        ('conditionId',data.get('conditionId') is not None),
        ('price',bool(data.get('price'))),
        ('shippingOptions',bool(data.get('shippingOptions'))),
        ('estimatedAvailabilities',bool(data.get('estimatedAvailabilities'))),
        ('localizedAspects',bool(data.get('localizedAspects'))),
        ('mpn',bool(data.get('mpn'))),
        ('gtin',bool(data.get('gtin'))),
        ('itemEndDate',bool(data.get('itemEndDate'))),
    ):
        (present if ok else absent).append(label)
    out['getitem_fields_present']=present
    out['getitem_fields_missing']=absent
    return out

def map_reason_to_sub_check(reason):
    """Fallback mapper for cached detail rows written before sub_checks existed."""
    text=str(reason or '')
    rules=(
        (SUB_CONDITION,('condition missing','condition not NEW')),
        (SUB_PRICE,('price changed or currency unknown',)),
        (SUB_SHIP_UNKNOWN,('fixed detail shipping not supplied',)),
        (SUB_SHIP_MISMATCH,('delivered price changed',)),
        (SUB_AVAIL,('out of stock','current availability not supplied','ended')),
        (SUB_TITLE_MODEL,('detail title contradicts exact identity','exact tool model aspect missing','tool model mismatch','model aspect missing','model aspect mismatch','style-colour code','manufacturer MPN')),
        (SUB_VARIATION,('variation listing','bottle volume','concentration','aftershave','UK size','department','battery/charger','tool voltage','colour')),
    )
    for name,needles in rules:
        if any(n.lower() in text.lower() for n in needles):
            return name
    return SUB_OTHER

def inspect_snapshot(snapshot,ident,state,when):
    if not risky(ident) or not snapshot.get('offers'):return snapshot
    low=min(snapshot['offers'],key=lambda o:o['listed_total'])
    cache=state.setdefault('item_detail_cache',{})
    key=low['item_id']+'::'+ident.match
    cached=cache.get(key)
    try:fresh=0<=(when-dt.datetime.fromisoformat(cached['observed_at'])).total_seconds()<TTL_MINUTES*60
    except (TypeError,KeyError,ValueError):fresh=False
    run=state.setdefault('detail_run',{'calls':0,'cached':0,'errors':[]})
    if fresh and cached.get('checked_item_price') not in (None,low['item_price']):fresh=False
    if fresh:run['cached']+=1
    elif not state.get('browse_details_blocked') and not state.get('ask_cache',{}).get('browse-blocked') and ebay.available() and run['calls']<(LIMIT if ident.category=='tools' else LIMIT-run.get('reserved_tools',0)) and research_budget.reserve(state,when,'item-details'):
        run['calls']+=1
        try:
            cached=assess(ebay.item_details(low['item_id']),low,ident,when);cache[key]=cached
        except Exception as exc:
            code=getattr(exc,'code',None)
            cached={'status':'error','item_id':low['item_id'],'observed_at':when.isoformat(timespec='seconds'),'reasons':[type(exc).__name__+(f' HTTP {code}' if code else '')],
                    'sub_checks':[{'sub_check_failed':SUB_OTHER,'expected':None,'observed':None,'reason':type(exc).__name__+(f' HTTP {code}' if code else ''),'note':'getItem error; no extra retry'}]}
            cache[key]=cached;run['errors'].append(cached['reasons'][0])
            if code in (401,403,429):state['browse_details_blocked']={'status':code,'observed_at':when.isoformat()}
    else:cached={'status':'awaiting_detail_budget','reasons':['Bounded getItem verification pending; cheap ask retained, not replaced by higher prices'],
                 'sub_checks':[{'sub_check_failed':SUB_OTHER,'expected':'verified_fields within detail budget','observed':'awaiting_detail_budget','reason':'Bounded getItem verification pending; cheap ask retained, not replaced by higher prices','note':'no getItem this pass; not a parser failure'}]}
    # A cached check is tied to its actual price and identity; re-assess when prices change.
    if cached.get('status')=='verified_fields' and cached.get('checked_item_price') not in (None,low['item_price']):cached={**cached,'status':'price_changed'}
    cache=dict(sorted(cache.items(),key=lambda x:x[1].get('observed_at',''),reverse=True)[:400]);state['item_detail_cache']=cache
    return {**snapshot,'detail_required':True,'lowest_detail':cached,'detail_status':cached['status']}


def for_acquisition(snapshot,raw,ident,state,when):
    """Verify the actual independent low after own-listing/seller exclusion."""
    from . import asking
    if not risky(ident):return snapshot
    ids={asking.item_id(v) for v in [raw.get('url'),raw.get('acquisition_url'),raw.get('ebay_item_id')] if asking.item_id(v)}
    seller=str(raw.get('acquisition_seller') or '').casefold()
    independent=[o for o in snapshot.get('offers',[]) if asking.item_id(o.get('item_id')) not in ids and not (seller and str(o.get('seller') or '').casefold()==seller)]
    checked=inspect_snapshot({**snapshot,'offers':independent},ident,state,when)
    return {**snapshot,**{k:checked[k] for k in ('detail_required','lowest_detail','detail_status') if k in checked}}
