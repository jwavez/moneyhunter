"""P0 presentation/routing contracts, all offline and synthetic."""
import copy,datetime as dt,io,contextlib,json,os,tempfile,unittest
from unittest.mock import patch
from moneyhunter import hub,routing,publication,asking,images,discord
from tests.test_asking_estimates import RAW,offer,snap,NOW

def ready(cost=60,sale=50):
 r={**RAW,'price':cost,'inbound_delivery':0,'heat':700,'ask_estimate':asking.estimate({**RAW,'price':cost,'inbound_delivery':0},snap([offer(i,sale+i) for i in range(6)]),NOW)}
 return r
class EvidenceRouting(unittest.TestCase):
 def route(self,r,seen=(),status='live',result=204):
  calls=[]
  def send(ch,cards,*a,**kw):
   if any(e.get('_mh_product_card') or e.get('_mh_product_rows') for e in cards):self.assertIsNotNone(discord.build_payload(cards),ch)
   calls.append((ch,cards));return result
  stats={'A':0,'B':0,'R':0,'errors':[],'scanned':1,'priced':0,'unpriced':1,'affordable':0}
  with tempfile.TemporaryDirectory() as td,patch.object(hub,'PRICES',td+'/prices.json'),patch.object(hub,'send',side_effect=send),patch.object(hub,'acquisition_status',return_value=status),patch.object(hub,'read_prices',return_value={}),patch.object(hub,'price_drops',return_value=([(r,{'price':90,'ts':'2026-11-01'})],{})),contextlib.redirect_stdout(io.StringIO()):
   keys=hub.route([r],[],stats,[],set(seen),dry=False)
  return calls,keys
 def test_negative_only_research_not_categories_heat_errors_or_drops(self):
  r=ready();self.assertTrue(publication.allowed(r));self.assertFalse(routing.opportunity(r))
  calls,keys=self.route(r);product=[c for c in calls if any(x.get('_mh_product_card') for x in c[1])]
  self.assertEqual([c[0] for c in product],['research-watch']);self.assertIn('SKIP',str(product));self.assertEqual(len([k for k in keys if r['url'] in k]),1)
  self.assertFalse(any('breakeven' in f['name'].lower() or 'minimum sale' in f['name'].lower() or 'max landed buy' in f['name'].lower() for f in product[0][1][0]['fields']))
 def test_qualified_signal_keeps_opportunity_category_heat_drop_features(self):
  r=ready(5,50);self.assertTrue(routing.opportunity(r));calls,_=self.route(r)
  for ch in ('opportunities','games-consoles','trending','price-errors','price-drops'):self.assertIn(ch,[c[0] for c in calls])
  self.assertNotIn('research-watch',[c[0] for c in calls])
 def test_unpriced_all_paths_held_without_name_policy_or_ack(self):
  r=ready();r.pop('ask_estimate');calls,keys=self.route(r)
  self.assertNotIn(r['url'],str(calls));self.assertFalse(any(r['url'] in k for k in keys));self.assertNotIn('Synthetic exact game',str(calls))
 def test_hold_failed_expired_unknown_and_seen_do_not_gain_delivery_ack(self):
  r=ready()
  for status,result in [('expired',204),('unknown',204),('live',500)]:
   _,keys=self.route(r,status=status,result=result);self.assertFalse(any(r['url'] in k for k in keys))
  old='w:ask-model-v1:'+r['url'];calls,keys=self.route(r,[old]);self.assertNotIn('research-watch',[c[0] for c in calls]);self.assertNotIn(old,keys)
 def test_condition_metadata_body_and_title_cannot_borrow_new_valuation(self):
  for field,value in [('title',RAW['title']+' Refurbished Good As New'),('desc','Refurbished Good As New'),('condition','USED'),('description','Open-box')]:
   r={**ready(),field:value};self.assertFalse(publication.allowed(r));self.assertEqual(publication.proof(r)['reason'],'condition_mismatch_new_comparators');self.assertFalse(routing.opportunity(r))
 def test_counts_keep_models_prices_images_routes_and_signals_distinct(self):
  priced=ready();unknown={**RAW,'url':'https://example.com/unsupported'};stale=copy.deepcopy(priced);stale['url']='https://example.com/stale';stale['ask_estimate']['observed_at']=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=7)).isoformat()
  noimage={**priced,'url':'https://example.com/lego','category':'lego'}
  with patch.object(images,'publishable',side_effect=lambda r:r['url']!='https://example.com/lego'),patch.object(publication,'allowed',side_effect=lambda r:r['url'] in [priced['url'],noimage['url']]),patch.object(publication,'proof',side_effect=lambda r:{'ok':r['url'] in [priced['url'],noimage['url']],'reason':'unsupported'}):
   s=routing.stages([priced,unknown,stale,noimage])
  self.assertEqual([s[k] for k in ('offers_scanned','research_models_generated','supported_market_estimates','publication_qualified_cards','route_eligible_cards','buying_signals','research_holds')],[4,3,2,1,1,0,3]);self.assertEqual(sum(v['offers'] for v in s['by_category'].values()),4)
 def test_destination_fallback_is_explicit_no_research_into_opportunities(self):
  h={'verify':'https://example.com/verify','near-misses':'https://example.com/research','bot-status':'https://example.com/status'}
  with patch.object(hub,'hooks',return_value=h),patch.object(hub.D,'post',return_value=204) as send:
   for ch in ('opportunities','research-watch','diagnostics'):hub.send(ch,[{'title':'Aggregate only'}])
   self.assertEqual([c.kwargs['url'] for c in send.call_args_list],list(h.values()))
   self.assertEqual(hub.destination_roles()['research-watch']['configured_route'],'near-misses')
  with patch.object(hub,'hooks',return_value={'verify':'https://example.com/verify'}),patch.object(hub.D,'post') as send:
   self.assertEqual(hub.send('research-watch',[{'title':'Aggregate only'}]),0);send.assert_not_called()
 def test_delivery_counts_only_successful_actual_product_messages(self):
  with patch.object(hub,'hooks',return_value={'research-watch':'https://example.com/research'}),patch.object(hub.D,'post',side_effect=[204,500,204]):
   hub.DELIVERY_COUNTS.clear();hub.send('research-watch',[{'_mh_product_card':True}]);hub.send('research-watch',[{'_mh_product_card':True}]);hub.send('research-watch',[{'title':'Aggregate only'}]);self.assertEqual(hub.DELIVERY_COUNTS,{'research-watch':1})
 def test_nonowned_webhooks_keep_link_only_components(self):
  self.assertTrue(all(b.get('style')==5 for row in hub.buttons(ready()) for b in row['components']))
