import datetime as dt
from moneyhunter import market,asking

def priced(raw):
 raw=dict(raw);now=dt.datetime.now(dt.timezone.utc);ident=market.identity(raw)
 offers=[{'itemId':f'v1|98765432100{i}|0','itemWebUrl':f'https://www.ebay.co.uk/itm/98765432100{i}','seller':{'username':f'fixture-{i}'},'conditionId':'1000','itemLocation':{'country':'GB'},'title':raw['title']+' NEW SEALED','price':{'value':str(100+i),'currency':'GBP'},'shippingOptions':[{'shippingCostType':'FIXED','shippingCost':{'value':'0','currency':'GBP'}}]} for i in range(6)]
 raw['ask_estimate']=asking.estimate(raw,market.summary({'itemSummaries':offers},ident,now),now)
 return raw
