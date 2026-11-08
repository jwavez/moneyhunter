import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as E from './src/evidence.js';
import app,{_test} from './src/index.js';
import {execFileSync} from 'node:child_process';
import {webcrypto} from 'node:crypto';
if(!globalThis.crypto)globalThis.crypto=webcrypto;
class KV {constructor(){this.map=new Map();this.fail=false;}async get(k,type){const v=this.map.get(k);return v==null?null:type==='json'?JSON.parse(v):v;}async put(k,v){if(this.fail)throw Error('storage unavailable');this.map.set(k,v);}async list({prefix,limit=1000}){const xs=[...this.map.keys()].filter(k=>k.startsWith(prefix));return {keys:xs.slice(0,limit).map(name=>({name})),list_complete:xs.length<=limit};}}
const env=()=>({MH:new KV(),EVIDENCE_GUILD_ID:'fixture-guild'});
const i=(id,user='fixture-owner',permissions='32',guild='fixture-guild')=>({guild_id:guild,channel_id:'fixture-channel',member:{user:{id:user},permissions},data:{custom_id:id}});
const today=new Date().toISOString().slice(0,10);
const identity={match:'Fixture LEGO 99999 sealed',condition:'new',variant:'sealed retail box',attrs:'set_number=99999',source:'https://example.com/sold/fixture-1'};
const sold={amount:'25',shipping:'0',sold:today,listed:today,observed:today};
async function pending(e,source=identity.source,kind='sold'){
 const result=await E.submit(i(`ev:identity:${kind}:lego`),{...identity,source},e),id=result.components[0].components[0].custom_id.split(':')[2];
 await E.submit(i('ev:terms:'+id),kind==='sold'?sold:kind==='cash'?{amount:'20',cost:'1',observed:new Date().toISOString(),cash:'CASH; PHYSICALLY ACCEPTED',conditions:'Exact sealed grade, testing complete, no deductions beyond recorded exit cost'}:kind==='offer'?{amount:'10',shipping:'0',observed:new Date().toISOString(),acquisition:'https://www.hotukdeals.com/deals/fixture-only',confirm:'ONLINE IN STOCK'}:{active:'10',observed:today,scope:'Fixture count'},e);return id;
}
async function decide(e,id,action='approve',user='fixture-owner'){
 const x=await e.MH.get('ev2:record:fixture-guild:'+id,'json');return E.submit(i(`ev:decision:${action}:${id}:${x.revision}`,user),{checks:action==='approve'?'CHECKED':action.toUpperCase(),note:'Fixture human inspected exact public source, actual GBP and dates'},e);
}
test('pending is private, human approval roundtrips through actual evidence.py, revocation changes/removes revision',async()=>{
 const e=env(),id=await pending(e);assert.equal((await E.publicFacts(e)).records.length,0);await decide(e,id);
 let facts=await E.publicFacts(e);assert.equal(facts.records.length,1);assert.equal(facts.counts.approved_sold,1);
 const text=JSON.stringify(facts);assert(!text.includes('fixture-owner'));assert(!text.includes('Fixture human'));assert(!text.includes('reviewer'));
 const py=execFileSync('python3',['-c',`import json,sys;from moneyhunter.review_bridge import validate_payload;from moneyhunter.evidence import load;r,v=validate_payload(json.load(sys.stdin));assert len(load(records=r))==1;print('schema roundtrip OK')`],{cwd:'..',input:text}).toString();assert.match(py,/roundtrip OK/);
 const revision=facts.record_revisions[facts.records[0].id];const second=await pending(e,'https://example.com/sold/fixture-2');await decide(e,second);facts=await E.publicFacts(e);assert.notEqual(facts.record_revisions[facts.records[0].id],revision);
 await decide(e,second,'revoke');facts=await E.publicFacts(e);assert.equal(facts.records[0].observations.length,1);await decide(e,id,'revoke');assert.equal((await E.publicFacts(e)).records.length,0);
 await assert.rejects(()=>decide(e,id),/pending/);
});
test('authority is signed member permissions and home guild, never arbitrary member or DM',async()=>{
 const e=env(),id=await pending(e),x=await e.MH.get('ev2:record:fixture-guild:'+id,'json');
 for(const permissions of ['0','bad',undefined]){const event=i(`ev:decision:approve:${id}:${x.revision}`,'stranger',permissions??'0');await assert.rejects(()=>E.submit(event,{checks:'CHECKED',note:'not authorised'},e),/authority/);}
 await assert.rejects(()=>E.component(i('ev:review:0','fixture-owner','32','other-guild'),e),/server/);
 await assert.rejects(()=>E.component({user:{id:'fixture-owner'},data:{custom_id:'ev:home'}},e),/server/);
 assert(E.reviewer(i('x','x','8')));assert(!E.reviewer({guild_id:'fixture-guild',user:{id:'x'}}));
});
test('first guild binding requires one existing known channel, never arbitrary user guild',async()=>{
 const e={MH:new KV(),SOLDCOMPS_CHANNEL:'known-channel'};await assert.rejects(()=>E.component(i('ev:home'),e),/existing/);const event=i('ev:home');event.channel_id='known-channel';await E.component(event,e);assert.equal(await e.MH.get('ev2:home'),'fixture-guild');await assert.rejects(()=>E.component(i('ev:home','x','32','wrong'),e),/Cross-server/);
});
test('duplicate sale, non GBP, future/invalid dates, exact identity and draft ownership fail closed',async()=>{
 const e=env();await pending(e);await assert.rejects(()=>pending(e),/already pending/);
 for(const v of ['USD 20','£20','-1','NaN','1.111'])assert.throws(()=>E.money(v));
 for(const v of ['2099-01-01T00:00:00Z','2026-02-30T10:00:00Z','2026-11-08T10:00:00'])assert.throws(()=>E.timestamp(v));
 const result=await E.submit(i('ev:identity:sold:lego'),{...identity,source:'https://example.com/fixture-next'},e),id=result.components[0].components[0].custom_id.split(':')[2];
 await assert.rejects(()=>E.component(i('ev:terms:'+id,'stranger'),e),/owner/);
 await assert.rejects(()=>E.submit(i('ev:terms:'+id),{...sold,observed:'2099-01-01'},e),/non-future/);
 await assert.rejects(()=>E.submit(i('ev:identity:sold:trainers'),{...identity,attrs:'sku=IH4316; size=UK 3.5'},e),/every exact/);
});
test('explicit attestation required, stale review and write failure cannot report approval',async()=>{
 const e=env(),id=await pending(e),x=await e.MH.get('ev2:record:fixture-guild:'+id,'json');
 await assert.rejects(()=>E.submit(i(`ev:decision:approve:${id}:${x.revision}`),{checks:'yes',note:'schema only'},e),/attestation/);
 await assert.rejects(()=>E.submit(i(`ev:decision:approve:${id}:old`),{checks:'CHECKED',note:'old'},e),/Stale/);
 e.MH.fail=true;await assert.rejects(()=>decide(e,id),/storage unavailable/);e.MH.fail=false;assert.equal((await E.publicFacts(e)).records.length,0);
});
test('fresh exact cash/offer/count join sold identity; vouchers/uninspected trade-ins blocked and expired cash withheld',async()=>{
 const e=env(),sale=await pending(e);await decide(e,sale);const cash=await pending(e,'https://uk.webuy.com/product-detail?id=fixture-only','cash');await decide(e,cash);const offer=await pending(e,'https://example.com/retailer/fixture-only','offer');await decide(e,offer);const velocity=await pending(e,'https://example.com/count/fixture-only','velocity');await decide(e,velocity);
 let facts=await E.publicFacts(e);assert(facts.records[0].floor);assert(facts.records[0].offers);assert(facts.records[0].velocity);
 execFileSync('python3',['-c',`import json,sys;from moneyhunter.review_bridge import validate_payload;from moneyhunter.evidence import load;r,_=validate_payload(json.load(sys.stdin));c=load(records=r)[0];assert c.floor==19;assert len(c.offers)==1;assert c.sold_90d==1`],{cwd:'..',input:JSON.stringify(facts)});
 const key='ev2:record:fixture-guild:'+cash,x=await e.MH.get(key,'json');x.terms.observed_at=new Date(Date.now()-86400000).toISOString();await e.MH.put(key,JSON.stringify(x));facts=await E.publicFacts(e);assert(!facts.records[0].floor);assert.equal(facts.counts.approved_cash,0);
 const r=await E.submit(i('ev:identity:cash:lego'),{...identity,source:'https://uk.webuy.com/product-detail?id=fixture-uninspected'},e),id=r.components[0].components[0].custom_id.split(':')[2];await assert.rejects(()=>E.submit(i('ev:terms:'+id),{amount:'20',cost:'0',observed:new Date().toISOString(),cash:'VOUCHER',conditions:'uninspected'},e),/cash\/bank/);await E.submit(i('ev:terms:'+id),{amount:'20',cost:'0',observed:new Date().toISOString(),cash:'CASH',conditions:'uninspected theoretical quote'},e);await assert.rejects(()=>decide(e,id),/genuine, exact/);
});
test('private outcomes are scoped to user, excluded from public export and count unsold censoring',async()=>{
 const e=env(),dt=new Date().toISOString();await E.submit(i('ev:outcome:save'),{item:'PRIVATE fixture item',bought:dt,listed:dt,sold:dt,economics:'buy=10; sale=20; costs=2; model_days=4'},e);await E.submit(i('ev:outcome:save'),{item:'PRIVATE unsold',bought:dt,listed:dt,sold:'',economics:'buy=10; costs=2; model_days=4'},e);
 const mine=(await E.component(i('ev:outcomes'),e)).data;assert.match(mine.content,/1 sold \/ 1 unsold/);assert.match(mine.content,/£8.00/);assert(!JSON.stringify(await E.publicFacts(e)).includes('PRIVATE'));
 const stranger=(await E.component(i('ev:outcomes','stranger'),e)).data;assert.match(stranger.content,/0 sold \/ 0 unsold/);assert(!stranger.content.includes('PRIVATE fixture item'));
});
test('public endpoint redacts private data and unsigned submission never reaches handlers',async()=>{
 const e=env();const r=await app.fetch(new Request('https://fixture/api/reviewed-evidence'),e,{});assert.equal(r.status,200);assert.deepEqual((await r.json()).records,[]);
 const unsigned=await app.fetch(new Request('https://fixture/',{method:'POST',body:JSON.stringify(i('ev:home'))}),{...e,DISCORD_PUBLIC_KEY:'0'.repeat(64)},{});assert.equal(unsigned.status,401);
 const response=await _test.handleComponent(i('ev:home'),e);assert.equal((await response.json()).data.flags,64);
});
test('published community evidence is hidden if revision is revoked or cannot be revalidated',async()=>{
 const e=env(),id=await pending(e);await decide(e,id);const facts=await E.publicFacts(e),record=facts.records[0];const old=globalThis.fetch;globalThis.fetch=async()=>new Response(JSON.stringify({generated_utc:new Date().toISOString(),deals:[],review_queue:[],pricing_catalog:[{id:record.id,evidence_revision:facts.record_revisions[record.id],title:'fixture'}]}));
 try{assert.equal((await _test.getDeals(e)).pricing_catalog.length,1);await decide(e,id,'revoke');assert.equal((await _test.getDeals(e)).pricing_catalog.length,0);}finally{globalThis.fetch=old;}
});
test('terminal reject/revoke veto survives an older concurrent approval write',async()=>{
 const e=env(),id=await pending(e);await decide(e,id);const key='ev2:record:fixture-guild:'+id,old=await e.MH.get(key,'json');await decide(e,id,'revoke');await e.MH.put(key,JSON.stringify(old));assert.equal((await E.publicFacts(e)).records.length,0);
 const p=await pending(e,'https://example.com/fixture-reject');const pendingRow=await e.MH.get('ev2:record:fixture-guild:'+p,'json');await decide(e,p,'reject');pendingRow.status='approved';pendingRow.reviewed_at=new Date().toISOString();await e.MH.put('ev2:record:fixture-guild:'+p,JSON.stringify(pendingRow));assert.equal((await E.publicFacts(e)).records.length,0);
});
test('cash acceptance is an explicit field, never inferred from negated prose',async()=>{
 const e=env();const r=await E.submit(i('ev:identity:cash:lego'),{...identity,source:'https://uk.webuy.com/product-detail?id=fixture-negation'},e),id=r.components[0].components[0].custom_id.split(':')[2];
 await E.submit(i('ev:terms:'+id),{amount:'20',cost:'0',observed:new Date().toISOString(),cash:'CASH',conditions:'NOT PHYSICALLY ACCEPTED; testing pending'},e);await assert.rejects(()=>decide(e,id),/genuine, exact/);assert.equal((await E.publicFacts(e)).counts.approved_cash,0);
});
test('unknown forecast is omitted, never fabricated as zero selling days',async()=>{
 const e=env(),dt=new Date().toISOString();await E.submit(i('ev:outcome:save'),{item:'Fixture no forecast',bought:dt,listed:dt,sold:dt,economics:'buy=10; sale=20; costs=2'},e);const view=(await E.component(i('ev:outcomes'),e)).data;assert.match(view.content,/1 sold \/ 0 unsold/);assert.match(view.content,/model error: not measured/);assert.match(view.content,/0 sold records with an actual recorded model/);assert(!JSON.stringify(await E.publicFacts(e)).includes('Fixture no forecast'));
});
