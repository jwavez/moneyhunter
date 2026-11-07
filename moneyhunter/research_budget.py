"""Durable conservative app-wide search cap; cache reuse is free.
800/day is below eBay's published default 5,000 Browse calls/day, not a quota grant.
"""
DAILY_LIMIT=800
CATEGORY_ORDER=('trainers','fragrance','tech','lego','gaming','tools')

def reserve(state,when,purpose):
    day=when.date().isoformat()
    usage=state.setdefault('browse_usage',{'date':day,'calls':0,'by_purpose':{}})
    if usage.get('date')!=day:
        usage={'date':day,'calls':0,'by_purpose':{}};state['browse_usage']=usage
    count=usage.get('calls')
    if not isinstance(count,int) or count<0 or count>=DAILY_LIMIT:return False
    usage['calls']+=1
    usage.setdefault('by_purpose',{})[purpose]=usage.get('by_purpose',{}).get(purpose,0)+1
    return True

def fair_order(entries,category,key,cursor=0):
    groups={}
    for x in sorted(entries,key=key):groups.setdefault(category(x),[]).append(x)
    cats=[c for c in CATEGORY_ORDER if c in groups]+sorted(set(groups)-set(CATEGORY_ORDER))
    if not cats:return []
    offset=cursor%len(cats);cats=cats[offset:]+cats[:offset]
    out=[]
    while any(groups.values()):
        for c in cats:
            if groups[c]:out.append(groups[c].pop(0))
    return out
