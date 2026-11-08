"""Synthetic offline photo publication contract; no real send or credential use."""
import copy,datetime as dt,unittest,tempfile,os,contextlib,io,json
from unittest.mock import patch,MagicMock
from moneyhunter import images,discord,hub,grading as G,embeds
NOW=dt.datetime.now(dt.timezone.utc)
URL='https://i.ebayimg.com/images/g/synthetic/s-l500.jpg'
RAW={'title':'LEGO Synthetic Moon Rover 75402','url':'https://www.ebay.co.uk/itm/123456789000','category':'lego','price':20,'inbound_delivery':0,'heat':700,'merchant':'eBay','thumb':URL}
from tests.publication_fixtures import priced
RAW=priced(RAW)
def ready():
 r=copy.deepcopy(RAW)
 with patch.object(images,'probe',return_value=(True,'http200_image')):images.prepare([r],{},NOW)
 return r
class MandatoryPhotos(unittest.TestCase):
 def test_actual_probe_status_mime_magic_and_bounded_read(self):
  for status,mime,body,expected in [(200,'image/jpeg',b'\xff\xd8\xffxxx',True),(200,'image/jpeg',b'<html>fake',False),(200,'text/html',b'\xff\xd8\xffxxx',False),(302,'image/jpeg',b'\xff\xd8\xffxxx',False)]:
   r=MagicMock();r.__enter__.return_value=r;r.status=status;r.headers={'Content-Type':mime};r.read.return_value=body
   with patch('urllib.request.build_opener') as opener:
    opener.return_value.open.return_value=r
    self.assertEqual(images.probe(URL)[0],expected)
    if status==200 and mime=='image/jpeg':r.read.assert_called_once_with(4096)
  with patch('urllib.request.build_opener') as opener:
   self.assertFalse(images.probe('https://127.0.0.1/private')[0]);opener.assert_not_called()
  self.assertIsNone(images._NoRedirect().redirect_request(None,None,302,'',{},'https://localhost/'))
 def test_broken_own_photo_falls_back_only_to_exact_verified_set(self):
  bad='https://i.ebayimg.com/images/g/synthetic/broken.jpg';a={**RAW,'thumb':bad};b={**RAW,'url':'https://www.hotukdeals.com/deals/synthetic','thumb':URL}
  state={}
  with patch.object(images,'probe',side_effect=lambda u:(u==URL,'http200_image' if u==URL else 'http_404')):
   report=images.prepare([a,b],state,NOW)
  self.assertEqual(report['verified'],2);self.assertEqual(a['thumb'],URL);self.assertIn('Reference',a['image_basis']);self.assertEqual(a['image_source_url'],b['url'])
  payload=discord.build_payload([hub.watch_card(a,{})]);self.assertIn('reference',payload['embeds'][0]['description'].lower())
 def test_missing_photo_is_held_and_later_retries_without_ack(self):
  bad={**RAW,'thumb':''}
  stats={'A':1,'B':0,'errors':[],'scanned':1,'priced':0,'unpriced':1,'affordable':0,'R':0}
  with tempfile.TemporaryDirectory() as td,patch.object(hub,'PRICES',td+'/prices.json'),patch.object(hub,'send',return_value=204) as send,patch.object(hub,'acquisition_status',return_value='live'),patch.object(hub,'read_prices',return_value={}),patch.object(hub,'price_drops',return_value=([],{})),contextlib.redirect_stdout(io.StringIO()):
   keys=hub.route([bad],[],stats,[],set(),dry=False)
   self.assertEqual(keys,set());self.assertFalse(any('lego'==c.args[0] for c in send.call_args_list))
   good=ready();keys=hub.route([good],[],stats,[],set(),dry=False)
   self.assertTrue(any(RAW['url'] in k for k in keys))
 def test_final_webhook_serializer_fails_closed_even_if_router_bypassed(self):
  r=ready();e=hub.watch_card(r,{})
  good=discord.build_payload([e]);self.assertEqual(good['embeds'][0]['image']['url'],URL);self.assertNotIn('_mh_',json.dumps(good))
  for mutate in [lambda x:x.pop('image'),lambda x:x.update(_mh_image_verified_until='2000-01-01T00:00:00+00:00'),lambda x:x.update(image={'url':'https://i.ebayimg.com/other.jpg'})]:
   b=copy.deepcopy(e);mutate(b)
   with patch('urllib.request.urlopen') as call,contextlib.redirect_stdout(io.StringIO()):self.assertEqual(discord.post([b],url='https://discord.invalid/synthetic'),0);call.assert_not_called()
 def test_bounded_cache_and_denied_source_pause(self):
  rows=[{**RAW,'title':RAW['title'].replace('75402',str(75402+i)),'thumb':URL+f'?i={i}'} for i in range(4)];state={}
  with patch.object(images,'MAX_FETCHES',2),patch.object(images,'probe',return_value=(True,'http200_image')) as probe:
   r=images.prepare(rows,state,NOW);self.assertEqual(probe.call_count,2);self.assertEqual(r['pending'],2)
   r=images.prepare(rows,state,NOW+dt.timedelta(seconds=1));self.assertEqual(probe.call_count,4);self.assertEqual(r['pending'],0)
  with patch.object(images,'probe',return_value=(False,'http_403')) as probe:
   state={};images.prepare([{**RAW}],state,NOW);images.prepare([{**RAW}],state,NOW+dt.timedelta(days=1));self.assertEqual(probe.call_count,1)
 def test_all_python_product_routes_have_final_serialized_images(self):
  r=ready();payloads=[]
  def capture(ch,cards,*a,**kw):
   p=discord.build_payload(cards);self.assertIsNotNone(p,ch)
   payloads.append((ch,p));return 204
  stats={'A':1,'B':0,'errors':[],'scanned':1,'priced':0,'unpriced':1,'affordable':0,'R':0}
  with tempfile.TemporaryDirectory() as td,patch.object(hub,'PRICES',td+'/prices.json'),patch.object(hub,'send',side_effect=capture),patch.object(hub,'acquisition_status',return_value='live'),patch.object(hub,'read_prices',return_value={}),patch.object(hub,'price_drops',return_value=([(r,{'price':40,'ts':'2026-11-01'})],{})),contextlib.redirect_stdout(io.StringIO()):
   hub.route([r],[],stats,[],set(),dry=False)
  for ch in ('lego','trending','price-errors','price-drops'):self.assertTrue(any(c==ch for c,p in payloads),ch)
  for ch,p in payloads:
   for e in p['embeds']:
    if 'LEGO' in e.get('title',''):self.assertEqual(e['image']['url'],URL)
  d=G.Deal(RAW['title'],RAW['url'],5,'lego','synthetic',target=50,stretch=60)
  for k,v in r.items():
   if k.startswith('image') or k=='thumb':setattr(d,k,v)
  d.ask_estimate=r['ask_estimate']
  for grade in ('A','B'):
   result=G.grade(d,200);result.grade=grade # routing-only synthetic grade, NOT evidence
   p=discord.build_payload(embeds.deal_card(d,result));self.assertEqual(p['embeds'][0]['image']['url'],URL)
