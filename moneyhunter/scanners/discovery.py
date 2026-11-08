"""Bounded official Browse acquisition, independent of consumer deal heat.

Up to four category-fair exact-product searches per scan, at most once per product/hour.
Retains up to three cheapest distinct seller offers per query for one hour.
No browser scraping, auctions, refurbished/new comparisons or invented stock.
"""
import datetime as dt
from .. import market, policy
from . import ebay
LAST_DIAGNOSTICS = {}

def age(ts, when):
    try: return (when-dt.datetime.fromisoformat(ts)).total_seconds()/3600
    except (TypeError, ValueError): return float('inf')

def scan(raws, state, when=None):
    global LAST_DIAGNOSTICS
    when = when or dt.datetime.now(dt.timezone.utc)
    p = policy.current(); cache = state['ask_cache']
    history = state.setdefault('discovery_queries', {})
    retained = state.setdefault('discovery_offers', {})
    health = {'status':'ready' if ebay.available() else 'unavailable_no_keys','queries':0,'candidates':0,'errors':[],
              'purpose':'Official active Buy It Now acquisition; NEW only, not sold evidence','query_budget':4}
    queries = {}
    for raw in raws:
        ident = market.identity(raw)
        if ident and 0 < raw.get('price',0) <= p['watch_ceiling']:
            queries.setdefault(market.cache_key(ident),ident)
    eligible = [(k,i) for k,i in queries.items() if age(history.get(k),when)>=1]
    from .. import variants, research_budget
    # Missing sizes in a feed can seed family discovery, NEVER a mixed-size valuation.
    for raw in raws:
        if raw.get('category')!='trainers' or not 0<raw.get('price',0)<=p['watch_ceiling']:continue
        seed=variants.trainer(raw,seed=True)
        if seed and getattr(seed,'discovery_seed',False):
            k=market.cache_key(seed)
            queries.setdefault(k,seed)
            if age(history.get(k),when)>=1:eligible.append((k,seed))
    eligible=list({k:(k,i) for k,i in eligible}.values())
    rotation=state.setdefault('research_rotation',{})
    ordered=research_budget.fair_order(eligible,lambda pair:pair[1].category,
        lambda pair:(history.get(pair[0],''),-int(cache.get(pair[0],{}).get('sample_count',0)>=5),-int(pair[1].identity.get('style_code') in variants.KNOWN_STYLE_GENDER),pair[0]),rotation.get('acquisition',0))
    health.update({'query_budget':4,'queries_by_category':{},'query_details':[]})
    # Price-led targets persist independently of today's feed. Keep one discovery
    # slot so unsupported/new identities are not starved by existing valuations.
    from .. import watchlist
    targets=[]
    query_history=state.setdefault('discovery_query_history',{})
    query_id=lambda i:i.category+':'+i.match.casefold()
    # Migrate existing query clocks, not timestamps of product observations.
    for key,e in state.get('value_watchlist',{}).items():
        q=e['category']+':'+e['query'].casefold()
        stamp=max(e.get('last_search_at',''),history.get(key,''))
        if stamp and stamp>query_history.get(q,''):query_history[q]=stamp
    target_reasons={};target_total=len(state.get('value_watchlist',{}))
    for key,e in state.get('value_watchlist',{}).items():
        reason=('not_usable' if e.get('target_status')!='usable_configured_cost_target' or not e.get('max_landed_buy') else 'stale_or_future' if not 0<=age(e.get('observed_at'),when)<6 else 'query_cooldown' if age(query_history.get(e['category']+':'+e['query'].casefold()),when)<1 else 'eligible')
        target_reasons[reason]=target_reasons.get(reason,0)+1
        if e.get('target_status')!='usable_configured_cost_target' or not e.get('max_landed_buy') or not 0<=age(e.get('observed_at'),when)<6 or age(query_history.get(e['category']+':'+e['query'].casefold()),when)<1:continue
        targets.append((key,watchlist.ident(e['identity_snapshot'])))
    distinct={}
    for key,i in targets:
        q=query_id(i)
        if q not in distinct or state['value_watchlist'][key]['max_landed_buy']<state['value_watchlist'][distinct[q][0]]['max_landed_buy']:distinct[q]=(key,i)
    health['target_selection']={'contexts_examined':target_total,'context_reasons':target_reasons,'eligible_distinct_queries':len(distinct),'duplicate_contexts_collapsed':len(targets)-len(distinct),'selection_limit':3}
    targets=research_budget.fair_order(list(distinct.values()),lambda pair:pair[1].category,
        lambda pair:(history.get(pair[0],''),pair[0]),rotation.get('acquisition',0))[:3]
    health['target_selection']['selected_price_queries']=len(targets)
    health['target_selection']['discovery_fallback_reason']=f'{len(targets)} fresh distinct target queries selected (up to 3); remaining slots are discovery because other contexts are cooled/unusable or duplicates' if targets else 'no fresh non-cooled usable target; see context_reasons'
    target_keys={key for key,_ in targets}
    pool=targets+[(key,i) for key,i in ordered if key not in target_keys]
    distinct_order=[];seen_queries=set()
    for key,i in pool:
        q=query_id(i)
        if q in seen_queries or age(query_history.get(q),when)<1:continue
        distinct_order.append((key,i));seen_queries.add(q)
    ordered=distinct_order
    health.update(price_led_queries=0,research_discovery_queries=0,persistent_watchlist=len(state.get('value_watchlist',{})))
    if cache.get('browse-blocked'): health['status']='paused_operator_review_required'
    elif ebay.available():
        for key,ident in ordered[:4]:
            if not research_budget.reserve(state,when,'acquisition'):
                health['status']='daily_budget_exhausted';break
            health['queries']+=1
            health.setdefault('query',ident.match)
            health['queries_by_category'][ident.category]=health['queries_by_category'].get(ident.category,0)+1
            rotation['acquisition']=rotation.get('acquisition',0)+1
            history[key]=when.isoformat(timespec='seconds')
            query_history[query_id(ident)]=history[key]
            try:
                target=state.get('value_watchlist',{}).get(key) if key in target_keys else None
                maximum=min(p['cap'],target['max_landed_buy']) if target else None
                # Price filter is item-only. Fixed delivery is always post-checked.
                count=state.setdefault('target_search_counts',{}).get(key,0)
                sort='newlyListed' if target and count%2 else 'price'
                state['target_search_counts'][key]=count+1
                if target:
                    items=ebay.active_items(ident.match,business_only=True,sort=sort,max_item_price=maximum)
                    health['price_led_queries']+=1
                    target.update(last_search_at=when.isoformat(timespec='seconds'),last_search_sort=sort,last_item_price_filter=maximum)
                else:
                    items=ebay.active_items(ident.match,business_only=True)
                    health['research_discovery_queries']+=1
                snapshot=market.summary(items,ident,when)
                health['matched_shipped_samples']=health.get('matched_shipped_samples',0)+snapshot['sample_count']
                health['query_details'].append({'query':ident.match,'category':ident.category,'samples':snapshot['sample_count'],'rejected':snapshot['rejected'],'sort':sort,'max_item_price':maximum,'max_landed_price':maximum,'target_status':target['target_status'] if target else 'discovery_research','ceiling_basis':'Item-price filter is necessary only; post-check fixed delivery; revalue against independent competition before any signal'})
                health['rejections']=snapshot['rejected']
                # Acquisition business-only results never replace all-seller competition.
                sellers=set();chosen=0
                for o in snapshot['offers']:
                    if chosen>=3:break
                    if not o.get('seller') or o['seller'].casefold() in sellers or 'FIXED_PRICE' not in o.get('buying_options',[]):continue
                    if o['listed_total']>p['watch_ceiling'] or maximum is not None and o['listed_total']>maximum:
                        health['above_landed_target']=health.get('above_landed_target',0)+1;continue
                    exact=market.identity({'title':o['title'],'category':ident.category})
                    if not exact:continue
                    sellers.add(o['seller'].casefold());chosen+=1
                    retained[o['url']]={'title':o['title'],'url':o['url'],'category':ident.category,'price':o['item_price'],
                        'thumb':o.get('image',''),'image_source_url':o['url'],'image_basis':'Own Browse listing image',
                        'inbound_delivery':o['shipping'],'delivery':'Fixed shipping quoted by Browse; checkout confirmation required',
                        'seller_type':'BUSINESS (documented acquisition filter)','buyer_fee_basis':'No private seller Buyer Protection charge; BUSINESS-filtered source',
                        'merchant':'eBay','source':'ebay_browse','source_observed_at':snapshot['observed_at'],
                        'acquisition_query':ident.match,'acquisition_mode':'value_led' if target else 'discovery_research','search_max_landed':maximum,'search_sort':sort,'source_filter':'FIXED_PRICE / NEW / GB / GBP / BUSINESS','acquisition_url':o['url'],'ebay_item_id':o['item_id'],'acquisition_seller':o['seller'],
                        'online_eligible':True,'offer_verified':False,'condition':'new','heat':0,'desc':'',
                        'end_at':o.get('end_at'),'availability_basis':'Active official Browse observation, not checkout guarantee'}
            except Exception as exc:
                code=getattr(exc,'code',None)
                health['errors'].append(f'Browse acquisition failed: {type(exc).__name__}'+(f' HTTP {code}' if code else ''))
                health['status']='partial_failure'
                if code in (401,403,429):
                    cache['browse-blocked']={'kind':'source_paused','date':when.date().isoformat(),'status':code}
                    health['status']='paused_operator_review_required';break
    retained={k:v for k,v in retained.items() if 0<=age(v.get('source_observed_at'),when)<1}
    retained=dict(sorted(retained.items(),key=lambda kv:kv[1].get('source_observed_at',''),reverse=True)[:60])
    state['discovery_offers']=retained
    state['discovery_query_history']={k:v for k,v in query_history.items() if age(v,when)<24*7}
    state['discovery_queries']={k:v for k,v in history.items() if age(v,when)<24*7}
    existing={r['url'] for r in raws}
    result=[r for r in retained.values() if r['url'] not in existing]
    health['candidates']=len(result);health['watchlist_products']=len(queries)
    LAST_DIAGNOSTICS=health
    return result

def status(raw, when=None):
    """Never send an eBay listing through the challenged public HTML path."""
    when=when or dt.datetime.now(dt.timezone.utc)
    if raw.get('source')!='ebay_browse': return 'unknown'
    if not 0<=age(raw.get('source_observed_at'),when)<.25: return 'unknown'
    if raw.get('end_at'):
        try:
            if dt.datetime.fromisoformat(raw['end_at'].replace('Z','+00:00'))<=when:return 'expired'
        except (TypeError,ValueError):return 'unknown'
    return 'live'  # explicitly an active API observation, not verified stock/checkout
