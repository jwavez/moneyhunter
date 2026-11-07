"""Sourced UK fragrance postage SCENARIOS, never a verified parcel quote.
Prices include VAT. No collection/postbox inference for restricted perfume.
"""
import datetime as dt
import math
import re
from . import config as C
from .fees import net_profit

CHECKED='2026-11-07'
RATE=3.75
RATE_URL='https://www.royalmail.com/sending/uk/tracked-48'
RULES_URL='https://www.postoffice.co.uk/mail/what-can-i-send'
RM_RULES_URL='https://personal.help.royalmail.com/app/answers/detail/a_id/96'

def profile(raw, when=None):
    when=when or dt.datetime.now(dt.timezone.utc)
    title=raw.get('title','')
    volumes={int(n) for n in re.findall(r'\b(\d{1,3})\s*ml\b',title,re.I)}
    ml=next(iter(volumes)) if len(volumes)==1 else None
    base={'service':'Royal Mail Tracked 48 online — UK small parcel','checked_at':CHECKED,'rate_source':RATE_URL,
        'rules_source':RULES_URL,'royal_mail_rules_source':RM_RULES_URL,'ml':ml,'postage':None,'status':'unvalidated',
        'actual_parcel_verified':False,'scope':'UK domestic only; no international service',
        'requirements':'One bottle in original retail packaging, cushioned strong outer with leak containment; ID8000 label and sender return address; present at Post Office counter — NOT collection or postbox. Confirm packed weight <=2kg and dimensions <=45 x 35 x 16cm. Published rule allows at most 4 items <=150ml each; this scenario assumes ONE.',
        'liability':'Published cover up to £75 or item value, whichever lower; exclusions/claim conditions apply. Not proof perfume breakage, leakage or full resale value is insured.',
        'packaging_assumption':C.PACKAGING,'packaging_basis':'Configured allowance only, not a verified protective-packaging quote'}
    if ml is None:base['reason']='Bottle volume not uniquely stated: no applicable postage scenario'
    elif ml>150:base['reason']=f'{ml}ml bottle exceeds Royal Mail perfume/aftershave 150ml per-item limit; no standard perfume postage scenario. If lotion is non-flammable, classification and an alternative liquids profile require verification.'
    elif re.search(r'\b(?:gift ?set|bundle|multipack)\b|\d+\s*[x×]\s*\d+',title,re.I):base['reason']='Multipack/contents not resolved: no single-bottle postage scenario'
    elif not 0<=(when.date()-dt.date.fromisoformat(CHECKED)).days<=30:base['reason']='Published tariff review expired; recheck current carrier rate before modeling'
    else:
        base.update(status='conditional_tariff_scenario',postage=RATE,
            reason=f'{ml}ml fits the published bottle-volume limit ONLY. Packaging, formulation/classification, weight, dimensions, destination and counter acceptance remain unverified; tariff scenario is NOT shipping approval.')
        if re.search(r'after[ -]?shave lotion',title,re.I):
            base['reason']+=' Non-flammable lotions are excluded from perfume restrictions; do NOT assume this lotion is non-flammable without product evidence.'
    return base

def scenario(raw, sale=None, when=None):
    p=profile(raw,when)
    result={'profile':p,'status':p['status'],'breakeven':None,'required_resale':None,'net':None,'roi':None,'net_before_unknown_delivery':None}
    if p['postage'] is None:return result
    buy=raw.get('price')
    if not isinstance(buy,(int,float)) or not math.isfinite(buy) or buy<=0:return result
    delivery=raw.get('inbound_delivery')
    known=isinstance(delivery,(int,float)) and not isinstance(delivery,bool) and math.isfinite(delivery) and delivery>=0
    cost=buy+(delivery if known else 0)
    from .hub import sell_needed
    be,target,_=sell_needed(cost,'fragrance',postage=p['postage'])
    result.update(breakeven=be,required_resale=target,inbound_known=known,cost=cost,
        basis='CONDITIONAL scenario; published online tariff + configured packaging allowance, not actual verified parcel costs'+('' if known else '; inbound delivery UNKNOWN: required prices are minimums and profit is an upper bound'))
    if isinstance(sale,(int,float)) and math.isfinite(sale) and sale>0:
        n=net_profit(sale,cost,'ebay_business','fragrance',p['postage'],C.PACKAGING,C.RETURNS_ALLOWANCE)
        result.update(net=n.net if known else None,roi=round(n.net/cost*100,1) if known else None,
            net_before_unknown_delivery=n.net if not known else None,fees=n.platform_fee,returns=n.returns_allowance)
    return result
