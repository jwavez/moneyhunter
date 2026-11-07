"""Bounded official getItem checks. Missing/conflicting detail is NOT authentication.
Lowest asks remain visible: detail uncertainty cannot inflate a resale estimate.
"""
import datetime as dt
import re
from . import research_budget, variants
from .scanners import ebay
LIMIT=4
TTL_MINUTES=30

def risky(ident):
    return ident.category in ('fragrance','trainers','tech') or bool(re.search(r'\b(controller|headset|peripheral)\b',ident.match,re.I))

def assess(data,offer,ident,when):
    from . import market
    out={'item_id':offer['item_id'],'observed_at':when.isoformat(timespec='seconds'),'status':'incomplete','reasons':[],
        'gtin':data.get('gtin'),'mpn':data.get('mpn'),'aspects':data.get('localizedAspects',[])[:40],
        'checked_item_price':offer['item_price'],'identity_query':ident.match,'condition_id':data.get('conditionId'),'availability':data.get('estimatedAvailabilities',[]),'source_url':offer['url']}
    bad=[];missing=[]
    if data.get('primaryItemGroup') or data.get('itemGroupHref'):missing.append('variation listing requires unambiguous selected-variant price')
    if data.get('conditionId') is None:missing.append('condition missing')
    elif str(data.get('conditionId'))!='1000':bad.append('condition not NEW')
    if not market.matches(data.get('title',''),ident):bad.append('detail title contradicts exact identity')
    if market.money(data.get('price'))!=offer['item_price']:bad.append('price changed or currency unknown')
    avail=data.get('estimatedAvailabilities',[])
    if any(a.get('estimatedAvailabilityStatus')=='OUT_OF_STOCK' or a.get('estimatedAvailableQuantity')==0 for a in avail):bad.append('out of stock')
    if not any(a.get('estimatedAvailabilityStatus') in ('IN_STOCK','LIMITED_STOCK') or (a.get('estimatedAvailableQuantity') or 0)>0 for a in avail):missing.append('current availability not supplied')
    end=data.get('itemEndDate')
    if end:
        try:
            if dt.datetime.fromisoformat(end.replace('Z','+00:00'))<=when:bad.append('ended')
        except (ValueError,TypeError):missing.append('end date invalid')
    shipping=[market.money(a.get('shippingCost')) for a in data.get('shippingOptions',[]) if a.get('shippingCostType')=='FIXED']
    shipping=[n for n in shipping if n is not None]
    if not shipping:missing.append('fixed detail shipping not supplied')
    elif abs(min(shipping)-offer['shipping'])>.01:bad.append('delivered price changed')
    aspects={variants.clean(a.get('name','')).strip():str(a.get('value','')) for a in data.get('localizedAspects',[])}
    def values(*keys):return ' '.join(aspects.get(k,'') for k in keys).strip()
    v=getattr(ident,'variant',{})
    if ident.category=='fragrance':
        volume=values('volume','size','unit quantity')
        ml={int(n) for n in re.findall(r'(?<!\d)(\d{1,3})\s*ml\b',volume,re.I)}
        if not ml:missing.append('bottle volume aspect missing')
        elif ml!={v.get('ml')}:bad.append('bottle volume mismatch')
        kind=variants.clean(values('type','concentration','formulation'))
        concentration=variants.concentration(kind)
        wanted=v.get('concentration')
        if wanted=='aftershave lotion':
            if not ('aftershave' in kind or 'after shave' in kind):missing.append('aftershave type aspect missing')
            if concentration in ('edt','edp','parfum') or 'balm' in kind:bad.append('lotion versus fragrance/balm mismatch')
        elif concentration is None:missing.append('concentration aspect missing')
        elif concentration!=wanted:bad.append('concentration mismatch')
    elif ident.category=='trainers':
        size=values('uk shoe size','uk size')
        nums={float(n) for n in re.findall(r'(?<!\d)\d{1,2}(?:\.5)?(?!\d)',size)}
        if not nums:missing.append('explicit UK size aspect missing')
        elif nums!={v.get('uk_size')}:bad.append('UK size mismatch')
        department=variants.clean(values('department','gender')).strip()
        if department and ((v.get('department')=='men' and ('women' in department or 'girl' in department or 'boy' in department)) or (v.get('department')=='women' and department in ('men','mens','male'))):bad.append('department mismatch')
        style=values('style code','mpn','manufacturer part number') or str(data.get('mpn') or '')
        if not style:missing.append('style-colour code aspect missing')
        elif not re.search(r'(?<![a-z0-9])'+re.escape(v.get('style_code',''))+r'(?![a-z0-9])',style,re.I):bad.append('style-colour code mismatch')
    elif ident.category=='tech':
        model=values('model','mpn','manufacturer part number') or str(data.get('mpn') or '')
        compact=lambda s:re.sub(r'[^a-z0-9]','',s.lower())
        if not model:missing.append('model aspect missing')
        elif not re.search(r'(?<![a-z0-9])'+r'[\s-]*'.join(re.escape(c) for c in compact(v.get('model','')))+r'(?![a-z0-9])',model,re.I):bad.append('model aspect mismatch')
        colour=variants.clean(values('colour','color') or str(data.get('color') or '')).strip()
        if not colour:missing.append('colour aspect missing')
        elif colour not in (v.get('colour'), 'blue' if v.get('colour')=='glass blue' else v.get('colour')):bad.append('colour mismatch')
    out['status']='conflict' if bad else 'incomplete' if missing else 'verified_fields'
    out['reasons']=bad+missing
    out['meaning']='Declared listing fields checked, NOT authenticity, sold evidence or checkout guarantee'
    return out

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
    elif not state.get('browse_details_blocked') and not state.get('ask_cache',{}).get('browse-blocked') and ebay.available() and run['calls']<LIMIT and research_budget.reserve(state,when,'item-details'):
        run['calls']+=1
        try:
            cached=assess(ebay.item_details(low['item_id']),low,ident,when);cache[key]=cached
        except Exception as exc:
            code=getattr(exc,'code',None)
            cached={'status':'error','item_id':low['item_id'],'observed_at':when.isoformat(timespec='seconds'),'reasons':[type(exc).__name__+(f' HTTP {code}' if code else '')]}
            cache[key]=cached;run['errors'].append(cached['reasons'][0])
            if code in (401,403,429):state['browse_details_blocked']={'status':code,'observed_at':when.isoformat()}
    else:cached={'status':'awaiting_detail_budget','reasons':['Bounded getItem verification pending; cheap ask retained, not replaced by higher prices']}
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
