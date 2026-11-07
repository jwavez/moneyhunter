"""Persistent exact-product asking watchlist, not stock or purchase approvals."""
import datetime as dt
import math
from types import SimpleNamespace
from . import market, asking, details, research_budget, policy
from .scanners import ebay

def ident(snapshot):
    cat=snapshot['category'];query=snapshot['query']
    if cat=='gaming':query=market.canonical_game(query)
    fields=dict(snapshot.get('identity') or {'condition':'new'})
    i=SimpleNamespace(category=cat,match=query,identity=fields,name_terms=snapshot.get('name_terms',[]))
    variant={k:v for k,v in fields.items() if k!='condition'}
    if cat in ('tech','fragrance','trainers') and variant:i.variant=variant
    return i

def hours(ts,when):
    try:return (when-dt.datetime.fromisoformat(ts)).total_seconds()/3600
    except (TypeError,ValueError):return float('inf')

def migrate(state,when):
    """Union real fresh same-identity game observations; never refresh their clocks."""
    cache=state['ask_cache'];groups={}
    for old,s in list(cache.items()):
        if s.get('kind')!='active_ask' or s.get('category')!='gaming' or not s.get('offers') or not 0<=hours(s.get('observed_at'),when)<6:continue
        i=ident(s);groups.setdefault(market.cache_key(i),(i,[]))[1].append(s)
    for key,(i,ss) in groups.items():
        offers={}
        for s in ss:
            for o in s['offers']:
                if not market.matches(o.get('title',''),i):continue
                o={**o,'observed_at':o.get('observed_at',s['observed_at'])}
                if o['item_id'] not in offers or o['observed_at']>offers[o['item_id']]['observed_at']:offers[o['item_id']]=o
        xs=sorted(o['listed_total'] for o in offers.values())
        if not xs:continue
        old=min(s['observed_at'] for s in ss)
        spread=xs[-1]>xs[0]*1.5
        cache[key]={**ss[0],'query':i.match,'observed_at':old,'date':old[:10],
            'offers':sorted(offers.values(),key=lambda o:o['listed_total'])[:50],'sample_count':len(xs),
            'listed_total_low':xs[0],'listed_total_high':xs[-1],'listed_total_median':ebay._pct(xs,.5),
            'listed_total_p25':ebay._pct(xs,.25),'listed_total_p75':ebay._pct(xs,.75),
            'status':'small_sample' if len(xs)<3 else 'wide_spread' if spread else 'indicative_only',
            'canonicalized_at':when.isoformat(timespec='seconds'),'migration_basis':'Real source observations; oldest clock retained, per-offer times preserved'}

def refresh_stale(state,when,budget=2):
    health={'queries':0,'budget':budget,'errors':[]}
    old=[e for e in state.get('value_watchlist',{}).values() if hours(e.get('observed_at'),when)>=2 and hours(e.get('last_research_at'),when)>=.5]
    ordered=research_budget.fair_order(old,lambda e:e['category'],lambda e:e.get('observed_at',''))
    for e in ordered[:budget]:
        if state['ask_cache'].get('browse-blocked') or not ebay.available() or not research_budget.reserve(state,when,'persistent-research'):break
        health['queries']+=1;e['last_research_at']=when.isoformat(timespec='seconds')
        try:
            i=ident(e['identity_snapshot']);state['ask_cache'][market.cache_key(i)]=market.summary(ebay.active_items(i.match),i,when)
        except Exception as exc:
            code=getattr(exc,'code',None);health['errors'].append(type(exc).__name__+(f' HTTP {code}' if code else ''))
            if code in (401,403,429):state['ask_cache']['browse-blocked']={'kind':'source_paused','date':when.date().isoformat(),'status':code};break
    return health

def build(state,when,inspect=True):
    entries=state.setdefault('value_watchlist',{})
    pairs={}
    for s in list(state['ask_cache'].values()):
        if s.get('kind')!='active_ask' or not s.get('offers') or not 0<=hours(s.get('observed_at'),when)<6:continue
        i=ident(s);key=market.cache_key(i)
        # Prefer canonical union over fragmented old snapshots without modifying their observations.
        if key not in pairs or len(s['offers'])>len(pairs[key][1]['offers']):pairs[key]=(i,s)
    ordered=research_budget.fair_order(pairs.items(),lambda kv:kv[1][0].category,lambda kv:kv[0])
    for key,(i,s) in ordered:
        if inspect:
            s=details.inspect_snapshot(s,i,state,when);state['ask_cache'][key]=s
        sellers={}
        for o in s['offers']:
            seller=str(o.get('seller') or '').casefold()
            if seller and (seller not in sellers or o['listed_total']<sellers[seller]['listed_total']):sellers[seller]=o
        offers=sorted(sellers.values(),key=lambda o:o['listed_total'])
        if not offers:continue
        low=offers[0]['listed_total'];support=sum(o['listed_total']<=low*1.1 for o in offers)
        adequate=len(sellers)>=5 and support>=2
        detail_ok=not details.risky(i) or s.get('detail_status')=='verified_fields'
        coupon=any(o.get('available_coupons') for o in offers if o['listed_total']<=low*1.1)
        resale=math.floor(low*.97*100)/100
        status='usable_configured_cost_target' if adequate and detail_ok and not coupon and i.category!='fragrance' else 'research_only'
        reason=[]
        if not adequate:reason.append('insufficient independent price depth')
        if not detail_ok:reason.append('lowest comparator detail '+s.get('detail_status','pending'))
        if coupon:reason.append('effective coupon competition unknown')
        if i.category=='fragrance':reason.append('conditional/unvalidated perfume transport: no actionable buy ceiling')
        maximum=asking.max_cost(resale,i.category) if status=='usable_configured_cost_target' else None
        if maximum is not None and maximum<=0:status='no_positive_ceiling';reason.append('No positive Strong landed acquisition ceiling')
        prior=entries.get(key,{})
        entries[key]={**prior,'key':key,'category':i.category,'query':i.match,'identity':i.identity,
            'identity_snapshot':{'category':i.category,'query':i.match,'identity':i.identity,'name_terms':getattr(i,'name_terms',[])},
            'first_seen':prior.get('first_seen',when.isoformat(timespec='seconds')),'last_seen':when.isoformat(timespec='seconds'),
            'observed_at':s['observed_at'],'valid_until':(dt.datetime.fromisoformat(s['observed_at'])+dt.timedelta(hours=6)).isoformat(timespec='seconds'),
            'competition_low':low,'estimated_resale':resale,'seller_count':len(sellers),'low_supporting_sellers':support,
            'max_landed_buy':maximum,'target_status':status,'checks':reason,
            'cost_basis':'Configured business fees/postage/packaging/returns, not an actual parcel quote. Financial search ceiling only; not purchase approval.',
            'lowest_detail':s.get('lowest_detail'),'sources':[{'item_id':o['item_id'],'seller':o.get('seller'),'url':o['url'],'delivered':o['listed_total'],'observed_at':o.get('observed_at',s['observed_at'])} for o in offers[:5]]}
    for e in entries.values():
        if not 0<=hours(e.get('observed_at'),when)<6:e.update(target_status='stale_research_only',max_landed_buy=None)
    state['value_watchlist']=dict(sorted(((k,e) for k,e in entries.items() if hours(e.get('last_seen'),when)<24*7),key=lambda kv:kv[1]['last_seen'],reverse=True)[:150])
    entries=state['value_watchlist']
    unique=lambda xs:len({(e['category'],e['query'].casefold()) for e in xs})
    return {'products':unique(entries.values()),'identity_contexts':len(entries),
        'usable_targets':unique(e for e in entries.values() if e['target_status']=='usable_configured_cost_target'),
        'by_category':{c:{'products':unique(e for e in entries.values() if e['category']==c),
            'identity_contexts':sum(e['category']==c for e in entries.values()),
            'usable_targets':unique(e for e in entries.values() if e['category']==c and e['target_status']=='usable_configured_cost_target')}
            for c in sorted({e['category'] for e in entries.values()})}}
