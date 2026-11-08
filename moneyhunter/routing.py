"""Evidence-state presentation, never a replacement for the existing buying gates."""
import re
import hashlib
from . import publication, images
from .policy import current

def opportunity(row):
    m=row.get('ask_estimate') or {}
    return (publication.allowed(row) and images.publishable(row) and
            bool(m.get('estimated_opportunity') or m.get('worth_reviewing')) and
            m.get('transport_validated') is not False and m.get('delivery_known') is True and
            not m.get('above_budget') and isinstance(m.get('net'),(int,float)) and m['net']>0 and
            isinstance(m.get('landed_cost'),(int,float)) and m['landed_cost']<=current()['cap'])

def candidate(row):
    from .hub import resellable
    price=row.get('price',row.get('item_price',row.get('buy')))
    return (publication.allowed(row) and images.publishable(row) and resellable(row) and
        isinstance(price,(float,int)) and price+(row.get('inbound_delivery') or 0)<=current()['watch_ceiling'] and
        not re.search(r'in.?store|pre.?order|tester',row.get('title',''),re.I))

def stages(rows,graded=()):
    supported=[r for r in rows if publication.allowed(r)]
    qualified=[r for r in supported if images.publishable(r)]
    ready=[r for r in qualified if candidate(r)]
    verified={d.url for d,g in graded if g.grade[0] in 'AB' and g.ev_net>0 and g.cost<=current()['cap'] and publication.allowed(vars(d)) and images.publishable(vars(d)) and (not getattr(d,'ask_estimate',None) or opportunity(vars(d)))}
    signals={r['url'] for r in ready if opportunity(r)}|verified
    holds={};bycat={}
    for r in rows:
        cat=r.get('category','other');b=bycat.setdefault(cat,{'offers':0,'supported':0,'publication_qualified':0,'holds':0});b['offers']+=1
        pr=publication.proof(r);image=images.publishable(r)
        if pr['ok']:b['supported']+=1
        if pr['ok'] and image:b['publication_qualified']+=1
        else:
            b['holds']+=1;k=pr.get('reason') if not pr['ok'] else 'verified_product_image_missing';holds[k]=holds.get(k,0)+1
    return {'offers_scanned':len(rows),'research_models_generated':sum(bool(r.get('ask_estimate')) for r in rows),
        'supported_market_estimates':len(supported),'publication_qualified_cards':len(qualified),
        'route_eligible_cards':len(ready),'route_eligibility_scope':'policy/format admission only; live availability, destination, limits and notification deduplication still apply',
        'buying_signals':len(signals),'opportunity_candidates':sum(r['url'] in signals for r in ready),
        'research_watch_candidates':sum(r['url'] not in signals for r in ready),
        'above_budget_priced_watch':sum(bool(r.get('ask_estimate',{}).get('above_budget')) for r in ready),
        'research_holds':len(rows)-len(qualified),'hold_reasons':holds,'by_category':bycat,
        'inbound_known':sum(r.get('inbound_delivery') is not None for r in rows),
        'inbound_unknown':sum(r.get('inbound_delivery') is None for r in rows)}

def counts_text(s):
    return (f"Offers scanned: {s['offers_scanned']} · Research models generated: {s['research_models_generated']} · "
        f"Supported market estimates: {s['supported_market_estimates']} · Publication-qualified cards: {s['publication_qualified_cards']} · "
        f"Route-eligible (policy/format): {s['route_eligible_cards']} · Buying signals: {s['buying_signals']} · "
        f"Above-budget priced watch: {s['above_budget_priced_watch']} ({'none qualified this scan' if not s['above_budget_priced_watch'] else 'qualified this scan'}) · Research holds: {s['research_holds']} · "
        f"Inbound known/unknown: {s['inbound_known']}/{s['inbound_unknown']}. Availability/dedup/destination pending; these are NOT delivered counts.")

def nearest(rows):
    """Only fully publishable, priced/calculable misses; never tease an unpriced name."""
    out=[]
    for r in rows:
        m=r.get('ask_estimate') or {}
        if not candidate(r) or opportunity(r) or m.get('transport_validated') is False:continue
        v=m.get('net') if m.get('delivery_known') else m.get('net_before_unknown_delivery')
        if isinstance(v,(int,float)):out.append((v,r))
    return [{'title':r['title'],'url':r['url'],'summary':publication.summary(r)} for _,r in sorted(out,key=lambda x:-x[0])[:5]]


def policy_key(url):return hashlib.sha256(url.encode()).hexdigest()[:24]
