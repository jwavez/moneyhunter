"""Clear price/profit/decision headings. Display arithmetic never changes buying gates."""
import datetime as dt
from . import config as C
from .fees import net_profit

def signed(n):return ('+' if n>=0 else '−')+f"£{abs(n):.2f}"

def fields(raw,model=None,legacy=None):
    m=model or raw.get('ask_estimate');when=dt.datetime.now(dt.timezone.utc)
    if m:
        try:fresh=0<=(when-dt.datetime.fromisoformat(m['observed_at'])).total_seconds()<6*3600
        except (TypeError,KeyError,ValueError):fresh=False
        if not fresh:m=None
    if m:
        listing=m['suggested_listing'];known=m.get('delivery_known',False);cost=m.get('landed_cost') if known else raw.get('price',m.get('item_price'))
        conditional=m.get('transport_validated') is False
        net=None if conditional or cost is None else net_profit(listing,cost,'ebay_business',raw.get('category',m.get('category','default')),C.postage_for(raw.get('category',m.get('category','default'))),C.PACKAGING,C.RETURNS_ALLOWANCE).net
        indicative=m.get('confidence')!='moderate' or m.get('seller_count',0)<5 or m.get('detail_status') not in (None,'not_required','verified_fields')
        sell=f"£{listing:.2f} starting listing — {'INDICATIVE ONLY; limited/unverified comparators' if indicative else 'competitor-based, not guaranteed'}. Conservative sale model £{m['estimated_resale']:.2f}."
        profit='UNKNOWN — actual compliant parcel/packaging costs unverified; conditional scenario below is not actual profit.' if conditional else 'UNKNOWN — acquisition cost not supplied.' if net is None else f"{'Estimated' if known else 'At most'} {signed(net)} at £{listing:.2f} sale"+(' after known inbound and configured selling costs.' if known else ' BEFORE UNKNOWN inbound delivery; actual net/ROI UNKNOWN.')
        conservative=m.get('net') if known else m.get('net_before_unknown_delivery')
        if conservative is not None:profit+=f" Conservative £{m['estimated_resale']:.2f} sale: {signed(conservative)}"+(' net.' if known else ' before unknown delivery.')
        if m.get('above_budget'):decision='ABOVE BUDGET — WATCH ONLY; no purchase approval.'+(' SKIP: estimated loss even before delivery.' if (net is not None and net<0) or (conservative is not None and conservative<0) else '')
        elif (net is not None and net<0) or (conservative is not None and conservative<0):decision='SKIP — estimated loss'+(' even before unknown inbound delivery.' if not known else ' after selling costs.')
        elif conditional:decision='RESEARCH ONLY — actual perfume transport and profit unvalidated.'
        elif m.get('estimated_opportunity'):decision='STRONG CHECK — NOT a verified BUY; verify stock, exact item and checkout costs.'
        elif m.get('worth_reviewing'):decision='MANUAL REVIEW — NOT a verified BUY.'
        else:decision='NOT A BUY — small/insufficient modeled margin or evidence/cost gaps. '+('Inbound delivery unknown. ' if not known else '')+(f"{m.get('seller_count',0)} known sellers; {m.get('confidence','unknown')} confidence.")
    elif legacy and legacy.get('evidence_type')=='sold':
        listing=legacy['plan']['list'];known=legacy.get('delivery_known',False);cost=legacy.get('landed_cost',legacy.get('buy'))
        net=net_profit(listing,cost,'ebay_business',raw.get('category','default'),legacy.get('postage',C.postage_for(raw.get('category','default'))),C.PACKAGING,C.RETURNS_ALLOWANCE).net
        sell=f"£{listing:.2f} starting listing from reviewed sold research; not guaranteed."
        profit=f"{signed(net)} at £{listing:.2f} sale"+(' after configured costs.' if known else ' BEFORE unknown inbound delivery; actual net unknown.')
        decision={'A':'BUY — existing verified gates pass; confirm checkout.','B':'VERIFY — existing evidence/offer checks still required.'}.get(legacy.get('grade'),'SKIP — existing buying checks fail.')
    else:
        sell='No reliable resale estimate — Not established: '+str(raw.get('ask_status','exact current comparators unavailable'))+'. Required resale targets are NOT market prices.'
        profit='UNKNOWN — no reliable market sale price; do not treat the policy target as profit.'
        decision='RESEARCH ONLY — NOT A BUY. Obtain exact current comparators and all costs.'
    return [{'name':'1 · Sell / starting listing','value':sell[:1000],'inline':False},{'name':'2 · Profit at that sale price','value':profit[:1000],'inline':False},{'name':'3 · Buy conclusion','value':decision[:1000],'inline':False}]
