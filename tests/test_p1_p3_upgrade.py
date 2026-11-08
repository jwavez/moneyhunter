"""Real-source identity fixtures + explicitly synthetic evidence; never production sales."""
import copy,datetime as dt,io,json,unittest
from pathlib import Path
from unittest.mock import patch
from moneyhunter import variants,market,publication,evidence,review_bridge,details
from moneyhunter.scanners import discovery,ebay
import tests.test_value_watchlist as WL
from tests.test_asking_estimates import NOW
class Coverage(unittest.TestCase):
 def test_actual_feed_identities_are_connected_and_distinct(self):
  rows=json.loads(Path('tests/fixtures/p1_actual_hukd.json').read_text())['offers'];ids=[]
  for row in rows:
   with self.subTest(title=row['title']):
    r=variants.attach_source_identity(copy.deepcopy(row));i=market.identity(r);self.assertIsNotNone(i);ids.append(market.cache_key(i))
    self.assertEqual(i.identity['condition'],'new')
  self.assertGreaterEqual(len(set(ids)),9)
 def test_adidas_code_size_department_and_source_bound_roundtrip(self):
  row=json.loads(Path('tests/fixtures/p1_actual_hukd.json').read_text())['offers'][0]
  row=next(r for r in json.loads(Path('tests/fixtures/p1_actual_hukd.json').read_text())['offers'] if 'Streetalk' in r['title'])
  r=variants.attach_source_identity(copy.deepcopy(row));i=market.identity(r);self.assertEqual(i.identity['style_code'],'IH4316');self.assertEqual(i.identity['uk_size'],3.5)
  exported={k:v for k,v in r.items() if k!='desc'};self.assertEqual(market.cache_key(market.identity(exported)),market.cache_key(i))
  for title in ('adidas IH4316 Womens UK4','adidas IH4317 Womens UK3.5','adidas IH4316 Mens UK3.5','adidas IH4316 Junior UK3.5','adidas IH4316 Womens UK3.5/4','adidas IH4316 Womens sizes 3.5 to 6.5','adidas IH4316 Womens US3.5','adidas IH4316 Womens UK3.5 Refurbished'):
   self.assertFalse(market.matches(title,i),title)
  exported['url']='https://example.com/different-source';self.assertIsNone(market.identity(exported))
 def test_r50i_requires_manufacturer_model_and_never_marketing_alias(self):
  base={'category':'tech','title':'Soundcore R50i Black','url':'https://example.com/fixture','desc':'MPN: A3949'}
  r=variants.attach_source_identity(base);i=market.identity(r);self.assertEqual(i.identity['manufacturer_model'],'A3949')
  self.assertIsNotNone(market.identity({k:v for k,v in r.items() if k!='desc'}))
  for title in ('Soundcore R50i Black','Soundcore R50i A3959 Black','Soundcore P20i A3949 Black','Soundcore R50i A3949 Black White','Soundcore R50i A3949 ANC Black','Soundcore R50i A3949 Black Replacement Earbud'):
   self.assertFalse(market.matches(title,i),title)
 def test_audio_and_tools_wrong_colour_grade_kit_suffix_not_aliases(self):
  for title in ('Soundcore P40i Black','Google Pixel Buds 2a Hazel','Bose SoundLink Flex 2nd Gen Black'):
   self.assertIsNotNone(market.identity({'title':title,'category':'tech'}))
  for title in ('Soundcore Q21i','Google Pixel Buds 2a Hazel Black','Bose SoundLink Flex 2nd Gen Black Refurbished','Soundcore P40i Black Charging Case','Soundcore R50i A3949 Black or White'):
   self.assertIsNone(market.identity({'title':title,'category':'tech'}),title)
  for title in ('Makita DTD152ZJ 18V','Makita DTD152Z 18V with battery','Makita DGA452Z 18V with case','DeWalt DCS382N-XJ 54V','DeWalt DCS565N-XJ 18V and DCB184','DeWalt DCF809D2T-GB 18V kit'):
   self.assertIsNone(market.identity({'title':title,'category':'tools'}),title)
class Acquisition(unittest.TestCase):
 def test_target_diagnostics_reveal_cooldown_and_duplicate_contexts(self):
  from moneyhunter import watchlist
  state,i=WL.ValueLed().state();watchlist.build(state,NOW,inspect=False);e=next(iter(state['value_watchlist'].values()));state['value_watchlist']['duplicate']=copy.deepcopy(e)
  with patch.object(ebay,'available',return_value=True),patch.object(ebay,'active_items',return_value={'itemSummaries':[]}) as api:
   discovery.scan([],state,NOW);h=discovery.LAST_DIAGNOSTICS['target_selection'];self.assertEqual(h['contexts_examined'],2);self.assertEqual(h['duplicate_contexts_collapsed'],1);self.assertEqual(h['selected_price_queries'],1);self.assertLessEqual(api.call_args.kwargs['max_item_price'],60)
   discovery.scan([],state,NOW+dt.timedelta(minutes=1));h=discovery.LAST_DIAGNOSTICS['target_selection'];self.assertEqual(h['context_reasons']['query_cooldown'],2);self.assertEqual(h['selected_price_queries'],0);self.assertEqual(api.call_count,1)
class ReviewBridge(unittest.TestCase):
 def sample(self):
  today=dt.date.today().isoformat();ident={'condition':'new','variant':'sealed','set_number':'99999'}
  return {'id':'community_fixture','match':'Fixture LEGO 99999','category':'lego','identity':ident,'reviewed':True,'reviewed_at':today,'observations':[{'url':'https://example.com/fixture-sold','sold_at':today,'observed_at':today,'price':25,'item_price':25,'shipping':0,'currency':'GBP','kind':'sold','identity':ident}]}
 def payload(self):
  r=self.sample();return {'schema_version':1,'kind':'human_reviewed_public_facts','generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'records':[r],'record_revisions':{r['id']:review_bridge.revision(r)}}
 def test_bad_review_schema_revisions_duplicates_and_currency(self):
  d=self.payload();self.assertEqual(len(review_bridge.validate_payload(d)[0]),1)
  for mode in ('pending','currency','future','revision','duplicate'):
   x=copy.deepcopy(d)
   if mode=='pending':x['records'][0]['reviewed']=False
   if mode=='currency':x['records'][0]['observations'][0]['currency']='USD'
   if mode=='future':x['records'][0]['observations'][0]['sold_at']='2099-01-01'
   if mode=='revision':x['record_revisions']={}
   if mode=='duplicate':x['records']*=2
   with self.subTest(mode=mode),self.assertRaises(ValueError):review_bridge.validate_payload(x)
 def test_unavailable_or_revoked_bridge_never_reuses_old_trusted_cache(self):
  class Response(io.BytesIO):url='https://fixture.example/api/reviewed-evidence'
  with patch.dict('os.environ',{'MONEYHUNTER_CAPTURE_URL':'https://fixture.example/api/research-capture'}):
   with patch.object(review_bridge,'urlopen',return_value=Response(json.dumps(self.payload()).encode())):self.assertEqual(len(review_bridge.load()),1)
   with patch.object(review_bridge,'urlopen',side_effect=OSError('fixture unavailable')):self.assertEqual(review_bridge.load(),[]);self.assertEqual(review_bridge.LAST_RECORDS,[])
   empty=self.payload();empty.update(records=[],record_revisions={})
   with patch.object(review_bridge,'urlopen',return_value=Response(json.dumps(empty).encode())):self.assertEqual(review_bridge.load(),[]);self.assertEqual(review_bridge.catalog(),[])
 def test_floor_original_timestamp_expires_after_24_hours_not_review_date(self):
  r=self.sample();clock=dt.datetime.now(dt.timezone.utc);r['floor']={'amount':20,'exit_cost':1,'kind':'cash','currency':'GBP','identity':r['identity'],'url':'https://example.com/fixture-cash','observed_at':(clock-dt.timedelta(hours=23)).isoformat()}
  c=evidence.load(records=[r])[0];self.assertEqual(c.floor,19)
  r['floor']['observed_at']=(clock-dt.timedelta(hours=24,seconds=1)).isoformat();self.assertIsNone(evidence.load(records=[r])[0].floor)
  r['floor']['observed_at']=(clock+dt.timedelta(seconds=60)).isoformat()
  with self.assertRaises(ValueError):evidence.validate(r)
class FullFeedIntake(unittest.TestCase):
 def test_actual_article_after_800_character_prose_limit_reaches_live_identity_path(self):
  import html
  from moneyhunter.scanners import hotukdeals
  row=next(r for r in json.loads(Path('tests/fixtures/p1_actual_hukd.json').read_text())['offers'] if 'Streetalk' in r['title'])
  # Actual title/URL/full source description; merchant-price is a labelled
  # SYNTHETIC parsing fixture, never an acquisition/checkout or sale quotation.
  xml=('<rss xmlns:pepper="https://www.hotukdeals.com/"><channel><item><title>'+html.escape(row['title'])+'</title><link>'+row['url']+'</link><description>'+html.escape(row['desc'])+'</description><pepper:merchant name="Fixture only" price="1.00"/></item></channel></rss>').encode()
  with patch.dict(hotukdeals.C.FEEDS,{'trainers':['tag/adidas']},clear=True),patch.object(hotukdeals.urllib.request,'urlopen',side_effect=lambda *a,**k:io.BytesIO(xml)):
   rows=hotukdeals.scan()
  self.assertEqual(len(rows),1);r=rows[0];self.assertLessEqual(len(r['desc']),800);self.assertNotIn('IH4316',r['desc']);self.assertEqual(r['identity_evidence'][0]['code'],'IH4316');self.assertEqual(market.identity(r).identity['uk_size'],3.5)
