"""Mandatory evidence-backed resale estimate. No target/RRP or missing-price bypass."""
import datetime as dt
import math
import re
from urllib.parse import urlsplit
from . import product_format as PF

def number(x):return isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x) and x>0

def proof(row,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    deny=lambda why:{'ok':False,'reason':why}
    if PF.reason(row):return deny('nonphysical')
    if row.get('offer_ambiguity'):return deny('ambiguous_primary_offer')
    m=row.get('ask_estimate')
    if m and condition_blocked(row):return deny('condition_mismatch_new_comparators')
    if m:
        try:age=(now-dt.datetime.fromisoformat(m['observed_at'])).total_seconds()/3600
        except (ValueError,KeyError,TypeError):return deny('missing_observation_time')
        if not 0<=age<6:return deny('stale_or_future_estimate')
        if m.get('model')!='competitor-asks-v1' or not number(m.get('suggested_listing')) or not number(m.get('estimated_resale')):return deny('missing_market_estimate')
        if m.get('detail_status') not in (None,'not_required','verified_fields'):return deny('exact_item_details_unverified')
        if m.get('competitor_coupon_unknown'):return deny('uncertain_competitor_coupon')
        from . import market
        ident=market.identity({'title':row.get('title',''),'category':row.get('category')})
        if not ident:return deny('unsupported_exact_identity')
        from . import details
        if details.risky(ident) and m.get('detail_status')!='verified_fields':return deny('exact_item_details_unverified')
        sellers={}
        for o in m.get('sources',[]):
            u=urlsplit(o.get('url',''))
            if u.scheme!='https' or u.hostname not in ('www.ebay.co.uk','www.ebay.com') or not u.path.startswith('/itm/'):continue
            if o.get('country')!='GB' or o.get('currency')!='GBP' or o.get('declared_condition')!='new' or not number(o.get('item_price')):continue
            if isinstance(o.get('shipping'),bool) or not isinstance(o.get('shipping'),(int,float)) or not math.isfinite(o['shipping']) or o['shipping']<0 or not number(o.get('listed_total')) or abs(o['listed_total']-o['item_price']-o['shipping'])>.01:continue
            if not market.matches(o.get('title',''),ident):continue
            seller=str(o.get('seller') or '').casefold()
            if seller and (seller not in sellers or o['listed_total']<sellers[seller]['listed_total']):sellers[seller]=o
        if len(sellers)<3:return deny('fewer_than_three_exact_independent_comparators')
        low=min(o['listed_total'] for o in sellers.values())
        if sum(o['listed_total']<=low*1.1 for o in sellers.values())<2:return deny('low_price_not_supported')
        if m['suggested_listing']>low+.01 or m['estimated_resale']>low:return deny('listing_above_supported_competition')
        return {'ok':True,'title':row.get('title'),'query':m['query'],'kind':'active_ask','listing':m['suggested_listing'],'observed_at':m['observed_at'],'valid_until':(dt.datetime.fromisoformat(m['observed_at'])+dt.timedelta(hours=6)).isoformat(),'sources':[o['url'] for o in sellers.values()],'comparators':[[o[k] for k in ('url','title','listed_total','shipping','item_price','seller')] for o in sellers.values()],'category':row.get('category')}
    sources=row.get('sold_sources',row.get('comp_urls',[]));age=row.get('comp_age_days')
    listing=row.get('publication_listing',(row.get('plan') or {}).get('list'))
    count=row.get('sold_90d',0)
    if row.get('evidence_type')=='sold' and isinstance(age,(int,float)) and 0<=age<=30 and (count or 0)>=5 and sources and number(listing):
        return {'ok':True,'kind':'reviewed_sold','listing':listing,'valid_until':(now+dt.timedelta(minutes=15)).isoformat(),'sources':sources,'category':row.get('category')}
    return deny('no_supported_resale_estimate')

def allowed(row,now=None):return proof(row,now).get('ok') is True

def valid_proof(p,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    try:return p.get('ok') is True and number(p.get('listing')) and len(p.get('sources',[]))>0 and dt.datetime.fromisoformat(p['valid_until'])>now
    except (ValueError,TypeError,AttributeError,KeyError):return False

def metadata(row):return {'_mh_product_card':True,'_mh_price_proof':proof(row)}

def summary(row):
    from . import presentation
    fields=presentation.fields(row,legacy=row)
    return ' · '.join(f"{label}: {str(f['value'])[:140]}" for label,f in zip(('Sell','Net','Decision'),fields))


def condition_blocked(row):
    """The active-ask lane is NEW only; metadata/body cannot override a used label."""
    text=' '.join(str(row.get(k) or '') for k in ('title','condition','condition_text','declared_condition'))
    body=' '.join(str(row.get(k) or '') for k in ('desc','description'))
    return bool(re.search(r'\b(refurb(?:ished)?|renewed|pre[ -]?owned|used|open[ -]?box|warehouse|good as new)\b',text,re.I) or
                re.search(r'\b(refurb(?:ished)?|renewed|pre[ -]?owned|open[ -]?box|good as new|condition\s*[:=-]\s*used)\b',body,re.I))
